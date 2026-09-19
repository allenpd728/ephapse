#!/usr/bin/env python3
"""pytest suite for the tier-0 gate harness and its gates.

Run:  python3 -m pytest tooling/gates/tests/ -k findings   # G-E gates only
      python3 -m pytest tooling/gates/tests/               # everything

Two kinds of assertion, both required by spec §4:

  * **Per-gate, both directions** — every registered gate fires on its failing
    fixture and is silent on its clean one.
  * **Harness behaviour** — BROKEN is reachable in each of its three ways, FAIL
    is distinct from PASS, and SKIP is never a pass.

The second group is the one that proves the harness itself can fail. Maith's own
first exit-code verification was vacuous because nothing asserted the check
could fire; these tests exist so that failure cannot recur here silently.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
GATES = HERE.parent
REPO = GATES.parent.parent
sys.path.insert(0, str(GATES))

import run_all as R  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_registry():
    R.REGISTRY.clear()
    R._load_gate_modules()
    yield
    R.REGISTRY.clear()


@pytest.fixture(autouse=True)
def _clean_probe_fixtures():
    """Remove the harness-probe scratch directory before and after every test.

    The probe tests write fixture fragments under fixtures/harness_probe/. They
    are inputs to a test, not committed evidence, so they must not survive a run
    (a stray probe file would appear in the fixture tree and confuse a later
    gate author).
    """
    probe = R.FIXTURES / "harness_probe"

    def _clear():
        if probe.exists():
            for f in probe.iterdir():
                f.unlink()
            probe.rmdir()

    _clear()
    yield
    _clear()


# ------------------------------------------------------------- registration
def test_registry_is_not_empty():
    assert R.REGISTRY, "no gates registered — the harness has nothing to run"


def test_every_gate_declares_a_failing_fixture():
    missing = [g.id for g in R.REGISTRY if g.failing_fixture is None]
    assert not missing, f"gates with no failing fixture: {missing}"


def test_every_gate_declares_a_traces_to():
    """Spec §3: every gate maps to a documented concern."""
    missing = [g.id for g in R.REGISTRY if not g.traces_to]
    assert not missing, f"gates not traced to a concern: {missing}"


def test_all_gates_are_tier_0():
    bad = [g.id for g in R.REGISTRY if g.tier != 0]
    assert not bad, f"tier-1 gates must not be wired in yet: {bad}"


def test_every_gate_satisfies_the_two_part_contract():
    """The contract, asserted for every registered gate at once."""
    bad = []
    for gate in R.REGISTRY:
        res = R.run_gate(gate)
        if res.status != "PASS":
            bad.append(f"{gate.id}: {res.status} — {res.detail}")
    assert not bad, "gates not satisfying the contract:\n" + "\n".join(bad)


# ------------------------------------------------------------------ G-E gates
FINDINGS_GATES = ("G-E1", "G-E2", "G-E6", "G-E7")


@pytest.mark.parametrize("gate_id", FINDINGS_GATES)
def test_findings_gate_is_registered(gate_id):
    assert any(g.id == gate_id for g in R.REGISTRY), f"{gate_id} not registered"


@pytest.mark.parametrize("gate_id", FINDINGS_GATES)
def test_findings_gate_passes_with_its_fixtures(gate_id):
    gate = next(g for g in R.REGISTRY if g.id == gate_id)
    res = R.run_gate(gate)
    assert res.status == "PASS", f"{gate_id}: {res.status} — {res.detail}"


def test_findings_clean_fixture_is_silent_for_every_reads_gate():
    """The clean fixture must pass G-E1, G-E2, and G-E6 (the pure-file gates)."""
    clean = R.FIXTURES / "findings" / "clean.jsonl"
    import validate_findings as V
    for fn in (V.check_schema, V.check_evidence, V.check_append_only):
        assert fn(clean) == [], f"{fn.__name__} fired on the clean fixture"


def test_findings_clean_fixture_passes_g_e7_with_the_cache():
    import validate_findings as V
    clean = R.FIXTURES / "findings" / "clean.jsonl"
    status, findings = V.check_issue_and_runid(clean)
    assert status == "PASS", f"G-E7 on clean: {status} {findings}"


def test_g_e7_skips_when_issue_state_is_unavailable(monkeypatch, tmp_path):
    """G-E7 must SKIP, never pass, when it cannot see issue state."""
    import validate_findings as V
    monkeypatch.setattr(V, "ISSUE_CACHE", tmp_path / "absent.json")
    clean = R.FIXTURES / "findings" / "clean.jsonl"
    status, findings = V.check_issue_and_runid(clean)
    assert status == "SKIP", f"expected SKIP, got {status}"
    assert findings, "a SKIP must carry its reason"


def test_g_e7_runid_violation_is_fail_not_skip(monkeypatch, tmp_path):
    """A malformed run_id is reportable offline, so it must FAIL not SKIP.

    Without this the issue-state half could mask a real format violation behind
    'could not verify'.
    """
    import validate_findings as V
    monkeypatch.setattr(V, "ISSUE_CACHE", tmp_path / "absent.json")
    bad = R.FIXTURES / "findings" / "g_e7_bad_runid.jsonl"
    status, findings = V.check_issue_and_runid(bad)
    assert status == "FAIL", f"expected FAIL, got {status}"
    assert any("run_id" in f for f in findings)


def test_g_e1_accepts_declared_extension_keys():
    """`note` is a KNOWN_EXTENSION, so the clean fixture must not trip G-E1."""
    import validate_findings as V
    clean = R.FIXTURES / "findings" / "clean.jsonl"
    recs = [json.loads(l) for l in clean.read_text().splitlines()
            if l.strip() and not l.startswith("#")]
    assert any("note" in r for r in recs), "fixture must exercise an extension key"
    assert V.check_schema(clean) == []


def test_g_e6_fires_when_record_count_drops_below_the_mark():
    import validate_findings as V
    shrunk = R.FIXTURES / "findings" / "g_e6_shrunk.jsonl"
    findings = V.check_append_only(shrunk)
    assert findings, "G-E6 did not fire on a shrunk log"
    assert any("append-only violated" in f for f in findings)


def test_g_e6_fires_when_the_mark_is_stale():
    """A log that grew past its mark means the mark was not raised."""
    import validate_findings as V
    clean = R.FIXTURES / "findings" / "clean.jsonl"
    mark = clean.parent / "findings.highwater"
    original = mark.read_text()
    try:
        mark.write_text("1\n")            # stale: 2 records present
        findings = V.check_append_only(clean)
        assert any("stale" in f for f in findings), findings
    finally:
        mark.write_text(original)


# --------------------------------------------------------- harness behaviour
SENTINEL = "ZZQTRIGGERZZQ"


def _dummy_check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return ["contains the sentinel"] if SENTINEL in text else []


def _fixture(name: str, body: str) -> str:
    p = R.FIXTURES / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return name


def test_broken_when_no_failing_fixture_registered():
    clean = _fixture("harness_probe/clean.txt", "nothing here\n")
    gate = R.Gate(id="X-NOFIX", name="probe", tier=0, check=_dummy_check,
                  clean_fixture=clean, failing_fixture=None)
    res = R.run_gate(gate)
    assert res.status == "BROKEN" and "no failing fixture" in res.detail


def test_broken_when_failing_fixture_missing():
    clean = _fixture("harness_probe/clean.txt", "nothing here\n")
    gate = R.Gate(id="X-MISS", name="probe", tier=0, check=_dummy_check,
                  clean_fixture=clean,
                  failing_fixture="harness_probe/does_not_exist.txt")
    res = R.run_gate(gate)
    assert res.status == "BROKEN" and "failing fixture missing" in res.detail


def test_broken_when_gate_silent_on_failing_fixture():
    """The exact shape of Maith's incident: a check whose anchor missed."""
    clean = _fixture("harness_probe/clean.txt", "nothing here\n")
    failing = _fixture("harness_probe/silent.txt", "nothing either\n")
    gate = R.Gate(id="X-SILENT", name="probe", tier=0, check=_dummy_check,
                  clean_fixture=clean, failing_fixture=failing)
    res = R.run_gate(gate)
    assert res.status == "BROKEN" and "silent on its FAILING fixture" in res.detail


def test_broken_when_clean_fixture_missing():
    gate = R.Gate(id="X-NOCLEAN", name="probe", tier=0, check=_dummy_check,
                  clean_fixture="harness_probe/absent_clean.txt",
                  failing_fixture="harness_probe/absent_fail.txt")
    res = R.run_gate(gate)
    assert res.status == "BROKEN" and "clean fixture missing" in res.detail


def test_fail_when_gate_fires_on_clean_fixture():
    clean = _fixture("harness_probe/dirty_clean.txt", f"has {SENTINEL}\n")
    failing = _fixture("harness_probe/dirty_fail.txt", f"has {SENTINEL}\n")
    gate = R.Gate(id="X-DIRTY", name="probe", tier=0, check=_dummy_check,
                  clean_fixture=clean, failing_fixture=failing)
    res = R.run_gate(gate)
    assert res.status == "FAIL" and "CLEAN fixture" in res.detail


def test_skip_is_reachable_and_is_not_a_pass():
    """A gate that fires on its failing fixture but skips the clean one is SKIP."""
    clean = _fixture("harness_probe/skip_clean.txt", "nothing here\n")
    failing = _fixture("harness_probe/skip_fail.txt", f"has {SENTINEL}\n")

    def check_status(path: Path):
        text = path.read_text(encoding="utf-8")
        if SENTINEL in text:
            return "FAIL", ["contains the sentinel"]
        if path.name == "skip_clean.txt":
            return "SKIP", ["input unavailable in this environment"]
        return "PASS", []

    gate = R.Gate(id="X-SKIP", name="probe", tier=0, check=_dummy_check,
                  check_status=check_status,
                  clean_fixture=clean, failing_fixture=failing)
    res = R.run_gate(gate)
    assert res.status == "SKIP", f"expected SKIP, got {res.status}"
    assert "partially verified" in res.detail


def test_skip_on_the_failing_fixture_is_broken():
    """Skipping the fixture that must fire means the gate cannot be trusted."""
    clean = _fixture("harness_probe/sk2_clean.txt", "nothing here\n")
    failing = _fixture("harness_probe/sk2_fail.txt", "nothing either\n")

    def check_status(path: Path):
        return "SKIP", ["always unavailable"]

    gate = R.Gate(id="X-SK2", name="probe", tier=0, check=_dummy_check,
                  check_status=check_status,
                  clean_fixture=clean, failing_fixture=failing)
    res = R.run_gate(gate)
    assert res.status == "BROKEN", f"expected BROKEN, got {res.status}"


def test_a_gate_that_raises_is_broken_not_a_crash():
    """An exception in a gate must be reported, not propagate.

    Learned building G-E7: `.relative_to(REPO)` raised on a relocated cache path
    and took the whole suite down instead of reporting. A gate that crashes is
    not a check, so it is BROKEN.
    """
    clean = _fixture("harness_probe/raise_clean.txt", "nothing here\n")
    failing = _fixture("harness_probe/raise_fail.txt", "nothing either\n")

    def exploding(path: Path) -> list[str]:
        raise ValueError("boom")

    gate = R.Gate(id="X-RAISE", name="probe", tier=0, check=exploding,
                  clean_fixture=clean, failing_fixture=failing)
    res = R.run_gate(gate)          # must not raise
    assert res.status == "BROKEN", f"expected BROKEN, got {res.status}"
    assert "ValueError" in res.detail and "boom" in res.detail


def test_run_all_exit_is_nonzero_when_any_gate_is_not_pass():
    clean = _fixture("harness_probe/clean.txt", "nothing here\n")
    R.REGISTRY.append(R.Gate(id="X-BAD", name="probe", tier=0,
                             check=_dummy_check, clean_fixture=clean,
                             failing_fixture=None))
    assert not all(r.status == "PASS" for r in R.run_all())


def test_real_findings_file_passes_the_registered_findings_gates():
    """The repo's own findings.jsonl must satisfy G-E1, G-E2, G-E6, G-E7.

    This is the check that would have caught a schema drift in the real log.
    """
    import validate_findings as V
    real = REPO / "findings.jsonl"
    assert real.exists(), "findings.jsonl missing"
    assert V.check_schema(real) == [], "G-E1 fired on the real findings.jsonl"
    assert V.check_evidence(real) == [], "G-E2 fired on the real findings.jsonl"
    assert V.check_append_only(real) == [], "G-E6 fired on the real findings.jsonl"
    status, findings = V.check_issue_and_runid(real)
    assert status in ("PASS", "SKIP"), f"G-E7 on real log: {status} {findings}"


# -------------------------------------------------------------- G-R gates
def test_infrastructure_exemption_matches_dated_filenames():
    """The README's patterns must match the repo's `<date>-<slug>.py` names.

    The naming convention date-prefixes every file, so a raw `startswith` on
    `latency-*` never matched. Found by running G-R1 over the real tree.
    """
    import validate_experiments as V
    assert V._is_infra("2026-09-18-latency-vs-batch.py", "")
    assert V._is_infra("2026-09-18-sandbox-baseline-hooked.py", "")
    assert not V._is_infra("2026-09-18-detector-positive-control.py", "")


def test_infrastructure_exemption_via_explicit_declaration():
    import validate_experiments as V
    text = "*Infrastructure/baseline file: no hypothesis under test.*"
    assert V._is_infra("2026-09-19-whatever.py", text)


def test_g_r2_fails_closed_when_no_model_can_be_determined():
    """Silence is not acceptance: an unidentifiable model is flagged."""
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r2_no_model"
    findings = V.gate_r2(d)
    assert findings, "G-R2 did not fail closed on a file with no model id"
    assert any("cannot determine" in f for f in findings)


def test_g_r2_fires_on_a_superseded_model():
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r2_superseded_model"
    findings = V.gate_r2(d)
    assert any("pythia-160m" in f for f in findings), findings


def test_g_r1_fires_on_a_claimed_but_invalid_exemption():
    """A hypothesis-test file claiming the exemption must not be excused.

    Three fields would satisfy the reduced set, so this only fails if the file
    is correctly judged NOT to be infrastructure — which is the point.
    """
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r1_invalid_exemption"
    findings = V.gate_r1(d)
    assert findings, "G-R1 excused a file that claimed the exemption"
    assert any("full header" in f for f in findings), findings


def test_g_r5_fires_on_an_unlogged_file():
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r5_missing_log_row"
    findings = V.gate_r5(d)
    assert any("no row" in f for f in findings), findings


def test_g_r5_is_silent_when_every_file_is_logged():
    import validate_experiments as V
    assert V.gate_r5(R.FIXTURES / "experiments_clean") == []


def test_model_target_source_is_machine_readable():
    """G-R2 and #12 share one target source; it must be parseable, not prose."""
    import validate_experiments as V
    targets = V.load_target_models()
    assert targets, "no authorized target models parsed"
    assert "pythia-70m-deduped" in targets


def test_experiment_gates_fail_on_the_real_tree_at_this_issue():
    """Issue #11's DoD: these gates MUST be red on the real tree until #15.

    If this test ever passes, either the artifacts were repaired (#15) or a gate
    stopped firing — both are events worth surfacing rather than silently
    accepting.
    """
    import validate_experiments as V
    total = (len(V.gate_r1(V.EXPERIMENTS)) + len(V.gate_r2(V.EXPERIMENTS))
             + len(V.gate_r5(V.EXPERIMENTS)))
    assert total > 0, ("G-R1/R2/R5 are all green on the real tree. At issue #11 "
                       "that means a gate stopped firing. Re-check against #15.")
