#!/usr/bin/env python3
"""Tests for the tier-0 gate harness (issue #9).

Run:  python3 tooling/gates/tests/test_gates.py

Two kinds of assertion, both required:

  * **Per-gate, both directions** — every registered gate fires on its failing
    fixture and is silent on its clean one. A gate with only the positive
    direction is incomplete (spec §4).
  * **Harness behaviour** — the runner reports BROKEN when a gate cannot be
    shown to fire, in each of the three ways that can happen: no failing
    fixture registered, fixture file missing, gate silent on its fixture. These
    are the tests that prove the harness itself can fail.

The last group matters most. Maith's own first exit-code verification was
vacuous because nothing asserted the check could fire; these tests exist so that
failure cannot recur here silently.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATES = HERE.parent
sys.path.insert(0, str(GATES))

import run_all as R  # noqa: E402


def load_gates() -> None:
    R.REGISTRY.clear()
    R._load_gate_modules()


# ------------------------------------------------------------------ per-gate
def test_registry_is_not_empty():
    load_gates()
    assert R.REGISTRY, "no gates registered — the harness has nothing to run"


def test_every_gate_fires_on_failing_fixture_and_is_silent_on_clean():
    """The contract, asserted for every registered gate."""
    load_gates()
    for gate in R.REGISTRY:
        res = R.run_gate(gate)
        assert res.status == "PASS", (
            f"{gate.id} did not satisfy the two-part contract: {res.status} — "
            f"{res.detail}")


def test_every_gate_declares_a_failing_fixture():
    load_gates()
    missing = [g.id for g in R.REGISTRY if g.failing_fixture is None]
    assert not missing, f"gates with no failing fixture: {missing}"


def test_every_gate_declares_a_traces_to():
    """Spec §3: every gate maps to a documented concern."""
    load_gates()
    missing = [g.id for g in R.REGISTRY if not g.traces_to]
    assert not missing, f"gates not traced to a concern: {missing}"


def test_all_gates_are_tier_0():
    load_gates()
    bad = [g.id for g in R.REGISTRY if g.tier != 0]
    assert not bad, f"tier-1 gates must not be wired into this runner yet: {bad}"


# --------------------------------------------------------- harness behaviour
# A sentinel that appears only in probe-fragment *content*, never in this file's
# prose. (The first version used a readable word that the "silent" fixture then
# mentioned in its own description, so the probe fired on text saying the token
# was absent — the same class of bug as the INFRA_RE over-match in G-R1.)
SENTINEL = "ZZQTRIGGERZZQ"


def _dummy_check(path: Path) -> list[str]:
    """Fires only on a file containing the sentinel token."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return ["fixture contains the sentinel"] if SENTINEL in text else []


def _make_fixture(name: str, body: str) -> str:
    p = R.FIXTURES / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return name


def test_broken_when_no_failing_fixture_registered():
    """A gate with failing_fixture=None is BROKEN, not PASS."""
    load_gates()
    clean = _make_fixture("harness_probe/clean.txt", "nothing here\n")
    gate = R.Gate(id="X-NOFIX", name="probe", tier=0, check=_dummy_check,
                  clean_fixture=clean, failing_fixture=None)
    res = R.run_gate(gate)
    assert res.status == "BROKEN", f"expected BROKEN, got {res.status}"
    assert "no failing fixture" in res.detail


def test_broken_when_failing_fixture_missing():
    """A registered but absent failing fixture is BROKEN."""
    load_gates()
    clean = _make_fixture("harness_probe/clean.txt", "nothing here\n")
    gate = R.Gate(id="X-MISS", name="probe", tier=0, check=_dummy_check,
                  clean_fixture=clean,
                  failing_fixture="harness_probe/does_not_exist.txt")
    res = R.run_gate(gate)
    assert res.status == "BROKEN", f"expected BROKEN, got {res.status}"
    assert "failing fixture missing" in res.detail


def test_broken_when_gate_silent_on_failing_fixture():
    """A fixture that does not trigger the gate means the gate is BROKEN.

    This is the exact shape of Maith's incident: a check whose anchor silently
    missed, so it passed against a file that should have failed it.
    """
    load_gates()
    clean = _make_fixture("harness_probe/clean.txt", "nothing here\n")
    failing = _make_fixture("harness_probe/silent.txt",
                            "this file does not contain the token\n")
    gate = R.Gate(id="X-SILENT", name="probe", tier=0, check=_dummy_check,
                  clean_fixture=clean, failing_fixture=failing)
    res = R.run_gate(gate)
    assert res.status == "BROKEN", f"expected BROKEN, got {res.status}"
    assert "silent on its FAILING fixture" in res.detail


def test_fail_when_gate_fires_on_clean_fixture():
    """A gate that fires on the clean case is FAIL, not PASS."""
    load_gates()
    clean = _make_fixture("harness_probe/dirty_clean.txt",
                          f"this has {SENTINEL} in it\n")
    failing = _make_fixture("harness_probe/dirty_fail.txt",
                            f"this also has {SENTINEL}\n")
    gate = R.Gate(id="X-DIRTY", name="probe", tier=0, check=_dummy_check,
                  clean_fixture=clean, failing_fixture=failing)
    res = R.run_gate(gate)
    assert res.status == "FAIL", f"expected FAIL, got {res.status}"
    assert "CLEAN fixture" in res.detail


def test_run_all_exit_code_is_nonzero_when_any_gate_is_not_pass():
    """The exit contract: 0 only when every gate is PASS."""
    load_gates()
    clean = _make_fixture("harness_probe/clean.txt", "nothing here\n")
    R.REGISTRY.append(R.Gate(id="X-BAD", name="probe", tier=0,
                             check=_dummy_check, clean_fixture=clean,
                             failing_fixture=None))
    results = R.run_all()
    ok = all(r.status == "PASS" for r in results)
    assert not ok, "run_all should report a non-PASS gate as failing"


def test_clean_fixture_missing_is_broken():
    """An absent clean fixture is a harness defect, not a gate failure."""
    load_gates()
    gate = R.Gate(id="X-NOCLEAN", name="probe", tier=0, check=_dummy_check,
                  clean_fixture="harness_probe/absent_clean.txt",
                  failing_fixture="harness_probe/absent_fail.txt")
    res = R.run_gate(gate)
    assert res.status == "BROKEN", f"expected BROKEN, got {res.status}"
    assert "clean fixture missing" in res.detail


def _cleanup_probes():
    p = R.FIXTURES / "harness_probe"
    if p.exists():
        for f in p.iterdir():
            f.unlink()
        p.rmdir()


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {name}\n          {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}\n          {type(e).__name__}: {e}")
    _cleanup_probes()
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
