#!/usr/bin/env python3
"""Tier-0 gate runner (issue #9).

Discovers every registered gate, runs each against the committed fixture tree,
aggregates the exit code, and prints a report carrying the gate id.

**Tier 0 only.** No torch, no model, no network, no LLM. Deterministic file
inspection. See docs/reference/TEST_VALIDATION_SPEC.md §3, §4, §6.

THE ONE NON-OBVIOUS RULE (spec §4, Maith's lesson)

    A gate with no registered failing fixture is reported BROKEN and fails
    the run.

This is the whole point of the harness. Maith's first exit-code verification
was itself vacuous — a string anchor silently missed and the "test" passed
against a broken scanner. The fix is to make the fixture rule *mechanical*: a
gate cannot be trusted unless the harness can prove the gate fires.

So `run_all.py` asserts two things per gate:

  1. it PASSES on the clean fixture, and
  2. it FIRES on its failing fixture.

If (2) cannot be demonstrated — because no failing fixture is registered, or the
fixture is missing, or the gate stays silent on it — the gate is BROKEN. A gate
that cannot fail is not a check.

Exit codes: 0 when every gate is PASS; 1 when any gate is BROKEN or FAIL.

Usage:
    python3 tooling/gates/run_all.py               # run everything, print report
    python3 tooling/gates/run_all.py --json        # machine-readable
    python3 tooling/gates/run_all.py --gate G-R1   # one gate
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FIXTURES = HERE / "tests" / "fixtures"


@dataclass
class Gate:
    """A registered gate.

    `check` is a callable taking a path and returning a list of finding strings
    (empty = pass). It must be deterministic and must not touch the network.

    `clean_fixture` and `failing_fixture` are paths relative to
    `tooling/gates/tests/fixtures/`. The failing fixture is MANDATORY: if it is
    None the gate is BROKEN by construction.

    A gate may instead implement `check_status(path) -> tuple[str, list[str]]`
    returning an explicit status, which is how a gate reports **SKIP** — used
    when its input is legitimately unavailable (e.g. G-E7 needs GitHub issue
    state and must degrade cleanly offline, per spec §10 Q4). SKIP is never a
    pass: it is reported and the run's exit code is non-zero unless
    `--allow-skip` is given.
    """
    id: str
    name: str
    tier: int
    check: Callable[[Path], list[str]]
    clean_fixture: str
    failing_fixture: Optional[str] = None
    traces_to: str = ""
    description: str = ""
    check_status: Optional[Callable[[Path], tuple[str, list[str]]]] = None


REGISTRY: list[Gate] = []


def register(gate: Gate) -> Gate:
    REGISTRY.append(gate)
    return gate


# ---------------------------------------------------------------- the runner
@dataclass
class GateResult:
    gate: Gate
    status: str            # PASS | FAIL | BROKEN
    detail: str = ""
    findings: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.gate.id


def _resolve(rel: str) -> Path:
    return FIXTURES / rel


def _apply(gate: Gate, path: Path) -> tuple[str, list[str]]:
    """Run the gate's check, honouring the optional explicit-status form.

    A gate that raises is caught and reported as BROKEN rather than crashing the
    runner: an exception means the gate cannot be shown to work, which is exactly
    what BROKEN says. The exception type and message are carried so the report is
    diagnostic. (Learned by building G-E7, whose `.relative_to(REPO)` raised on a
    relocated cache path and took the whole suite down instead of reporting.)
    """
    try:
        if gate.check_status is not None:
            return gate.check_status(path)
        findings = gate.check(path)
        return ("FAIL" if findings else "PASS"), findings
    except Exception as e:  # noqa: BLE001 - deliberate: surface, do not crash
        raise _GateRaised(f"{type(e).__name__}: {e}") from e


class _GateRaised(RuntimeError):
    """Raised when a gate's check throws; converted to BROKEN by run_gate."""


def run_gate(gate: Gate) -> GateResult:
    """Apply the two-part contract. BROKEN when the gate cannot be shown to fire.

    Statuses, and why the order matters:

    * `FAIL` — the gate fired on the **clean** fixture. The gate is wrong or the
      fixture is dirty; either way it is not trustworthy.
    * `BROKEN` — the gate's ability to fire could not be demonstrated: no failing
      fixture registered, fixture missing, or the gate stayed silent/skipped on
      it. A gate that cannot fail is not a check (spec §4).
    * `SKIP` — the gate fires on its failing fixture (so it *is* a check) but
      reported SKIP on the clean one because part of its input was unavailable
      (G-E7 needs issue state). The clean side is therefore only partially
      verified. **SKIP is never a pass**: the exit code stays non-zero unless
      `--allow-skip` is given.
    * `PASS` — silent on clean, fires on its failing fixture.
    """
    clean = _resolve(gate.clean_fixture)
    if not clean.exists():
        return GateResult(gate, "BROKEN",
                          f"clean fixture missing: {gate.clean_fixture}")

    try:
        clean_status, clean_findings = _apply(gate, clean)
    except _GateRaised as e:
        return GateResult(gate, "BROKEN",
                          f"raised on the clean fixture — a gate that crashes is "
                          f"not a check: {e}")
    if clean_status == "FAIL":
        return GateResult(gate, "FAIL",
                          f"fired on the CLEAN fixture {gate.clean_fixture} "
                          f"({len(clean_findings)} finding(s)) — a gate must be "
                          f"silent on the clean case",
                          clean_findings)

    # The mandatory half: prove the gate can fail. This runs regardless of
    # whether the clean side passed or skipped, because "can it fire at all?" is
    # the question the fixture rule exists to answer.
    if gate.failing_fixture is None:
        return GateResult(gate, "BROKEN",
                          "no failing fixture registered — a gate that cannot "
                          "fail is not a check (spec §4)")
    failing = _resolve(gate.failing_fixture)
    if not failing.exists():
        return GateResult(gate, "BROKEN",
                          f"failing fixture missing: {gate.failing_fixture} — "
                          f"the gate's ability to fire cannot be demonstrated")

    try:
        f_status, f_findings = _apply(gate, failing)
    except _GateRaised as e:
        return GateResult(gate, "BROKEN",
                          f"raised on its FAILING fixture — cannot be shown to "
                          f"fire: {e}")
    if f_status != "FAIL" or not f_findings:
        return GateResult(gate, "BROKEN",
                          f"{'skipped' if f_status == 'SKIP' else 'silent'} on "
                          f"its FAILING fixture {gate.failing_fixture} — the gate "
                          f"does not detect the violation it ships a fixture for")

    if clean_status == "SKIP":
        return GateResult(gate, "SKIP",
                          f"fires on its failing fixture (so it is a check), but "
                          f"the clean side was only partially verified: "
                          f"{clean_findings[0] if clean_findings else 'unavailable'}",
                          clean_findings)
    return GateResult(gate, "PASS", "", f_findings)


def run_all(only: Optional[str] = None) -> list[GateResult]:
    gates = [g for g in REGISTRY if only is None or g.id == only]
    if only is not None and not gates:
        print(f"ERROR: no gate registered with id {only}", file=sys.stderr)
        return []
    return [run_gate(g) for g in gates]


def report(results: list[GateResult]) -> str:
    lines = [
        "tier-0 gate report",
        "=" * 78,
        f"{'gate':<8} {'tier':>4}  {'status':<7} detail",
        "-" * 78,
    ]
    for r in results:
        lines.append(f"{r.id:<8} {r.gate.tier:>4}  {r.status:<7} {r.gate.name}")
        if r.detail:
            lines.append(f"{'':>21}{r.detail}")
        for f in r.findings[:3]:
            lines.append(f"{'':>23}- {f}")
        if len(r.findings) > 3:
            lines.append(f"{'':>23}- ... and {len(r.findings)-3} more")
    lines.append("-" * 78)
    n_pass = sum(1 for r in results if r.status == "PASS")
    n_skip = sum(1 for r in results if r.status == "SKIP")
    n_bad = len(results) - n_pass - n_skip
    summary = f"{n_pass}/{len(results)} gates PASS"
    if n_skip:
        summary += f"; {n_skip} SKIPPED (not a pass)"
    if n_bad:
        summary += f"; {n_bad} not passing"
    lines.append(summary)
    if n_bad:
        broken = [r.id for r in results if r.status == "BROKEN"]
        if broken:
            lines.append(f"BROKEN (cannot be shown to fire): {', '.join(broken)}")
    if n_bad or n_skip:
        lines.append("NOT 'gate passed' — see docs/reference/"
                     "TEST_VALIDATION_SPEC.md §4 (two tiers, never merged).")
    return "\n".join(lines)


def _load_gate_modules() -> None:
    """Import every gate module beside this file so they self-register.

    Spec §6 names gate modules under *two* prefixes — `validate_*.py` for the
    artifact checks and `check_*.py` for the cross-reference / tokenizer /
    code-inspection ones (`check_prompt_disjointness.py`,
    `check_docs_coherence.py`, `check_experiment_code.py`). Globbing only
    `validate_*` silently omitted every `check_*` gate: it registered nothing,
    so `run_all.py --gate G-P2` reported "no gate registered" and the module's
    own tests could not exercise the harness contract. Found by wiring G-P2
    (issue #14); it would have hit #20 and #22 the same way.

    Both patterns are matched, and a module is imported once even if it somehow
    matches twice.
    """
    seen: set[Path] = set()
    for mod in sorted(list(HERE.glob("validate_*.py")) + list(HERE.glob("check_*.py"))):
        if mod in seen:
            continue
        seen.add(mod)
        spec = importlib.util.spec_from_file_location(mod.stem, mod)
        m = importlib.util.module_from_spec(spec)
        # Make `from run_all import register, Gate` work inside the module.
        sys.modules.setdefault("run_all", sys.modules[__name__])
        spec.loader.exec_module(m)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="tier-0 gate runner (issue #9)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gate", default=None, help="run a single gate by id")
    ap.add_argument("--allow-skip", action="store_true",
                    help="treat SKIP as acceptable (exit 0). SKIP is never a "
                         "pass; this only relaxes the exit code for environments "
                         "where a gate's input is legitimately unavailable.")
    args = ap.parse_args(argv)

    _load_gate_modules()
    results = run_all(args.gate)
    if not results:
        return 1

    if args.json:
        print(json.dumps({
            "gates": [{"id": r.id, "name": r.gate.name, "tier": r.gate.tier,
                       "status": r.status, "detail": r.detail,
                       "findings": r.findings} for r in results],
            "n_pass": sum(1 for r in results if r.status == "PASS"),
            "n_skip": sum(1 for r in results if r.status == "SKIP"),
            "n_total": len(results),
        }, indent=2))
    else:
        print(report(results))

    ok = all(r.status == "PASS" or (args.allow_skip and r.status == "SKIP")
             for r in results)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
