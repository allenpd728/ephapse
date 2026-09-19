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
    """
    id: str
    name: str
    tier: int
    check: Callable[[Path], list[str]]
    clean_fixture: str
    failing_fixture: Optional[str] = None
    traces_to: str = ""
    description: str = ""


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


def run_gate(gate: Gate) -> GateResult:
    """Apply the two-part contract. BROKEN when the gate cannot be shown to fire."""
    clean = _resolve(gate.clean_fixture)
    if not clean.exists():
        return GateResult(gate, "BROKEN",
                          f"clean fixture missing: {gate.clean_fixture}")

    findings = gate.check(clean)
    if findings:
        return GateResult(gate, "FAIL",
                          f"fired on the CLEAN fixture {gate.clean_fixture} "
                          f"({len(findings)} finding(s)) — a gate must be silent "
                          f"on the clean case",
                          findings)

    # The mandatory half: prove the gate can fail.
    if gate.failing_fixture is None:
        return GateResult(gate, "BROKEN",
                          "no failing fixture registered — a gate that cannot "
                          "fail is not a check (spec §4)")
    failing = _resolve(gate.failing_fixture)
    if not failing.exists():
        return GateResult(gate, "BROKEN",
                          f"failing fixture missing: {gate.failing_fixture} — "
                          f"the gate's ability to fire cannot be demonstrated")

    findings = gate.check(failing)
    if not findings:
        return GateResult(gate, "BROKEN",
                          f"silent on its FAILING fixture {gate.failing_fixture} "
                          f"— the gate does not detect the violation it ships a "
                          f"fixture for")
    return GateResult(gate, "PASS", "", findings)


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
    n_bad = len(results) - n_pass
    lines.append(f"{n_pass}/{len(results)} gates PASS"
                 + (f"; {n_bad} not passing" if n_bad else ""))
    if n_bad:
        broken = [r.id for r in results if r.status == "BROKEN"]
        if broken:
            lines.append(f"BROKEN (cannot be shown to fire): {', '.join(broken)}")
        lines.append("NOT 'gate passed' — see docs/reference/"
                     "TEST_VALIDATION_SPEC.md §4 (two tiers, never merged).")
    return "\n".join(lines)


def _load_gate_modules() -> None:
    """Import every validate_*.py beside this file so they self-register."""
    for mod in sorted(HERE.glob("validate_*.py")):
        spec = importlib.util.spec_from_file_location(mod.stem, mod)
        m = importlib.util.module_from_spec(spec)
        # Make `from run_all import register, Gate` work inside the module.
        sys.modules.setdefault("run_all", sys.modules[__name__])
        spec.loader.exec_module(m)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="tier-0 gate runner (issue #9)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gate", default=None, help="run a single gate by id")
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
            "n_total": len(results),
        }, indent=2))
    else:
        print(report(results))

    return 0 if all(r.status == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
