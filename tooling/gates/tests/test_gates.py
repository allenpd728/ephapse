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


def test_findings_header_declares_every_extension_key():
    """Every key in KNOWN_EXTENSIONS must be documented in the findings header.

    Issue #25: the gate accepted `input_disjointness` (declared in
    KNOWN_EXTENSIONS) while the header prose documented none of its extension
    keys. That is a silent divergence in the schema of record — the gate knows
    a key the header does not. This test makes the drift loud: adding a key to
    KNOWN_EXTENSIONS without documenting it in the header fails here.
    """
    import validate_findings as V
    header = "\n".join(
        line for line in (REPO / "findings.jsonl").read_text(
            encoding="utf-8").splitlines() if line.startswith("#")
    )
    undeclared = [k for k in V.KNOWN_EXTENSIONS if k not in header]
    assert not undeclared, (
        f"KNOWN_EXTENSIONS key(s) {undeclared} are not documented in the "
        f"findings.jsonl header — document them or the schema of record "
        f"diverges from the gate"
    )


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


def test_infrastructure_declaration_no_longer_grants_the_exemption():
    """Issue #24 hole 2: prose alone must not excuse a file.

    The old `_is_infra` returned True on this exact declaration for any name, so
    a hypothesis-test file could drop `Null`/`Correction` with a docstring edit.
    The exemption is now name-only; the declaration is ignored.
    """
    import validate_experiments as V
    text = "*Infrastructure/baseline file: no hypothesis under test.*"
    assert not V._is_infra("2026-09-19-whatever.py", text)
    assert not V._is_infra("2026-09-19-cross-domain-probe.py", text)
    # A genuinely exempt name is still exempt, declaration or not.
    assert V._is_infra("2026-09-19-latency-fixture.py", "")
    # `gen_*` is NOT an enumerated exemption: it was only ever exempt via the
    # prose route this hole closes, and the README does not list it. Its real
    # repair is a header (#24 leaves it red; #16 owns whether it joins the set).
    assert not V._is_infra("gen_cross_domain.py", "")


def test_g_r1_fires_when_a_hypothesis_file_self_declares_infrastructure():
    """The failing fixture now self-declares, so this fails for the right reason.

    Before the fix `_is_infra` excused this file; the assertion below would then
    have found no findings and the fixture would have been green — the exact
    hole. It must be reported as a hypothesis-test missing `Inputs`/`Null`/
    `Correction`.
    """
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r1_invalid_exemption"
    findings = V.gate_r1(d)
    assert findings, "G-R1 excused a self-declared 'infrastructure' file"
    assert any("2026-09-19-claims-exemption.py" in f for f in findings), findings
    assert any("full header" in f for f in findings), findings


def test_header_rule_three_cases_full_exempted_and_claimed():
    """The G-R1 fixture set proves the three cases issue #16 names.

    Full header (clean), the enumerable exemption (latency-*), and a
    hypothesis-test file that *claims* the exemption and must be rejected.
    """
    import validate_experiments as V

    clean = R.FIXTURES / "experiments_clean"
    assert V.gate_r1(clean) == [], "G-R1 fired on the clean fixture set"

    claimed = R.FIXTURES / "experiments_r1_invalid_exemption"
    findings = V.gate_r1(claimed)
    assert any("2026-09-19-claims-exemption.py" in f and "full header" in f
               for f in findings), findings
    # The genuinely exempt `latency-*` file in the same directory must not fire.
    assert not any("latency-fixture" in f for f in findings), findings

    missing = R.FIXTURES / "experiments_r1_missing_field"
    findings = V.gate_r1(missing)
    assert any("2026-09-19-missing-correction.py" in f and "Correction" in f
               for f in findings), findings


def test_header_near_miss_is_reported_not_only_an_empty_file():
    """A header that looks complete but omits one field must be caught.

    A gate that only fires on an empty or obviously-malformed file satisfies the
    letter of the fixture rule and none of its purpose.
    """
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r1_missing_field"
    findings = V.gate_r1(d)
    assert any("G-R1 full header missing" in f for f in findings), findings


def test_readme_header_exemption_matches_the_gate():
    """The README's exemption patterns must be the gate's, not a drifting copy.

    Issue #16 method constraint: one source of truth. The failure mode is a rule
    that drifts from its checker (the Maith G2-5 docs-vs-scanner divergence).
    This test fails if the README names a pattern `_is_infra` does not implement,
    or omits one it does.
    """
    import validate_experiments as V

    readme = (REPO / "experiments" / "README.md").read_text(encoding="utf-8")
    for pattern in V.INFRA_PATTERNS:
        assert pattern in readme, (
            f"README does not name the gate's exemption pattern {pattern!r} — "
            f"the rule has drifted from its checker")
    for required in ("Model", "Inputs", "Question", "Null", "Correction", "Issue"):
        assert required in readme, f"README template omits the {required} field"
    assert "validate_experiments.py" in readme, (
        "README does not point at the gate that enforces the header rule")


def test_g_r2_fails_closed_when_no_model_can_be_determined():
    """Silence is not acceptance: an unidentifiable model is flagged."""
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r2_no_model"
    findings = V.gate_r2(d)
    assert findings, "G-R2 did not fail closed on a file with no model id"
    assert any("cannot determine" in f for f in findings)


def test_g_r2_accepts_a_correctly_attributed_superseded_model():
    """Issue #24 hole 1: a `Supersedes:` naming the model decision is an escape.

    Without it #15 must falsify or delete the superseded 160M measurements to
    turn the gate green, which is dishonest. The fixture names DEC-014 (the
    model decision), so G-R2 must be silent.
    """
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r2_superseded_model"
    findings = V.gate_r2(d)
    assert findings == [], f"a valid supersession must be accepted: {findings}"


def test_g_r2_fires_on_a_superseded_model_with_an_unrelated_decision():
    """The escape must not degrade into "any DEC mention silences the gate".

    `**Supersedes: DEC-011**` is not the model decision, so citing it cannot
    authorize the 160M. This is the failing fixture G-R2 is registered with.
    """
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r2_unrelated_decision"
    findings = V.gate_r2(d)
    assert any("pythia-160m" in f for f in findings), findings
    assert all("Supersedes" in f for f in findings), findings


def test_g_r2_escape_is_not_reachable_by_a_bare_dec_mention():
    """A DEC in prose (no `Supersedes:`) must not authorize a non-target id."""
    import validate_experiments as V
    d = R.FIXTURES / "experiments_r2_unrelated_decision"
    text = (d / "2026-09-19-unrelated-decision.py").read_text()
    assert "DEC-014" not in text, "fixture must not accidentally cite the decision"
    findings = V.gate_r2(d)
    assert findings, "a bare DEC mention must not silence G-R2"


def test_model_decision_policy_is_machine_readable():
    """The escape's policy lives with the target, not in prose or in the gate."""
    import validate_experiments as V
    assert V.load_model_decisions() == ["DEC-014"], V.load_model_decisions()
    # The policy line must not be mistaken for a model id.
    assert "model-decision: DEC-014" not in V.load_target_models()


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


# -------------------------------------------------------------- G-R3 gates
def test_g_r3_is_silent_on_the_pinned_fixture():
    import validate_deps as V
    assert V.check_deps(R.FIXTURES / "requirements" / "pinned.txt") == []


def test_g_r3_fires_on_the_unpinned_fixture():
    import validate_deps as V
    findings = V.check_deps(R.FIXTURES / "requirements" / "unpinned.txt")
    assert findings, "G-R3 did not fire on an unpinned requirement"
    assert any("pandas" in f for f in findings), findings


def test_g_r3_ignores_pip_options_and_inline_comments():
    """`--extra-index-url` and inline `#` comments must not be false positives.

    Issue #12's DoD names both explicitly. A gate that flagged either would push
    an author to mangle a correct line to appease it.
    """
    import validate_deps as V
    clean = R.FIXTURES / "requirements" / "pinned.txt"
    findings = V.check_deps(clean)
    assert not any("extra-index-url" in f for f in findings), findings
    assert not any("transformer-lens" in f for f in findings), findings


def test_g_r3_allows_a_direct_reference_requirement():
    """`pkg @ https://...#egg=pkg` carries its version in the URL, and the `#`
    is a fragment, not a comment."""
    import validate_deps as V
    clean = R.FIXTURES / "requirements" / "pinned.txt"
    assert not any("pkg" in f for f in V.check_deps(clean))


def test_g_r3_exemption_requires_a_rationale():
    """An empty `# unpinned-by-policy:` must NOT exempt.

    Without this the marker becomes a blanket silence — the guard that makes the
    exemption a check rather than an escape hatch.
    """
    import validate_deps as V
    findings = V.check_deps(R.FIXTURES / "requirements" / "empty_rationale.txt")
    assert findings, "G-R3 exempted a marker with no rationale"
    assert any("no rationale" in f for f in findings), findings


def test_g_r3_is_silent_when_the_only_unpinned_line_is_exempt_with_reason():
    import validate_deps as V
    clean = R.FIXTURES / "requirements" / "pinned.txt"
    text = clean.read_text()
    assert "unpinned-by-policy:" in text, "fixture must exercise the exemption"
    assert V.check_deps(clean) == []


def test_g_r3_extra_index_url_alone_does_not_satisfy_a_pin():
    """A stray `--extra-index-url` must not mask the requirements around it."""
    import validate_deps as V
    findings = V.check_deps(R.FIXTURES / "requirements" / "unpinned.txt")
    assert len(findings) == 1, f"expected exactly one finding, got {findings}"


def test_real_requirements_is_red_until_21_reconciles_numpy():
    """G-R3 MUST fire on the real requirements.txt until #21 settles `numpy`.

    Mirrors `test_experiment_gates_fail_on_the_real_tree_at_this_issue`: if this
    ever passes, either #21 landed (and `numpy` is pinned or marked inline) or a
    gate stopped firing. Both are events worth surfacing rather than silently
    accepting. #21's method constraint is explicit that the gate must not force
    the pin, so this test asserts the *disagreement* is still visible, not that
    it is permanent.
    """
    import validate_deps as V
    findings = V.check_deps(V.REQUIREMENTS)
    assert findings, (
        "G-R3 is green on the real requirements.txt. At issue #12 that means "
        "either #21 landed or the gate stopped firing — re-check both.")
    assert any("numpy" in f for f in findings), findings


def test_g_r3_exemption_marker_is_inline_by_design():
    """The exemption is an *inline* marker, deliberately not a preceding comment.

    A preceding comment would attach to a line the parser cannot associate
    reliably across blank lines and reordering. Requiring the marker on the
    requirement's own line keeps `requirements.txt` and the gate stating one rule
    in one place (#21's "make the prose and the gate agree").
    """
    import validate_deps as V
    clean = R.FIXTURES / "requirements" / "pinned.txt"
    assert "unpinned-by-policy:" in clean.read_text()
    assert V.check_deps(clean) == []



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


# -------------------------------------------------------- G-P2 / G-P4 gates
PROMPT_SETS = R.FIXTURES / "prompt_sets"


def _prompt_pair(name):
    import check_prompt_disjointness as C
    base = PROMPT_SETS / name
    a, b = C.load_prompt_sets(base / "a.txt", base / "b.txt")
    ids_a = set(json.loads((base / "ids_a.json").read_text()))
    ids_b = set(json.loads((base / "ids_b.json").read_text()))
    return C, a, b, ids_a, ids_b


def test_g_p2_is_silent_on_the_disjoint_fixture():
    C, a, b, ia, ib = _prompt_pair("disjoint")
    r = C.check_disjointness(a, b, ia, ib)
    assert r["findings"] == [], r["findings"]
    assert r["token_ids"]["n_shared"] == 0


def test_g_p2_fires_on_the_shared_token_fixture():
    """The near miss: sets are otherwise disjoint, one token id leaks."""
    C, a, b, ia, ib = _prompt_pair("shared_token")
    r = C.check_disjointness(a, b, ia, ib)
    assert r["findings"], "G-P2 did not fire on a shared token id"
    assert any("G-P2" in f for f in r["findings"]), r["findings"]
    assert r["token_ids"]["n_shared"] == 1, r["token_ids"]


def test_g_p4_fires_on_a_prompt_present_in_both_sets():
    C, a, b, ia, ib = _prompt_pair("shared_prompt")
    r = C.check_disjointness(a, b, ia, ib)
    assert any("G-P4" in f for f in r["findings"]), r["findings"]


def test_g_p2_reports_contents_not_just_a_count():
    """The issue's DoD requires the intersection *contents*, not only its size."""
    C, a, b, ia, ib = _prompt_pair("shared_token")
    r = C.check_disjointness(a, b, ia, ib)
    assert r["token_ids"]["shared_ids"] == [42256], r["token_ids"]


def test_g_p2_is_right_in_both_directions_on_strings_vs_ids():
    """The whole reason the check is on ids.

    `unhappy`/`happy` are not substrings of each other yet share id 42256, so an
    id test catches what a string test cannot. `seven` IS a substring of
    `seventeen` and they share no id, so the id test stays silent where a naive
    substring test would fire. Both fixtures are drawn from the real tokenizer;
    `token_ids_for` is the only path that downloads, and it is used here rather
    than on the gate path.

    **Tier 1, not tier 0.** This is the one test in the suite that downloads a
    tokenizer, so it cannot run in the tier-0 CI job (issue #13's method
    constraint: no torch, no model, no network). `importorskip` makes that
    explicit and skips cleanly rather than failing the job.

    Recorded as a known gap rather than hidden: this test is therefore NOT
    enforced in CI. Spec §10 Q2 raises the fix — commit the token-id sets as
    evidence and re-verify only when they change — which would make it tier 0.
    That is a design decision for a follow-up, not something to fake here.
    """
    C = pytest.importorskip(
        "check_prompt_disjointness",
        reason="tier-1 test: needs the transformers tokenizer (no network in tier 0)",
    )
    pytest.importorskip(
        "transformers",
        reason="tier-1 test: the real tokenizer is a download; tier 0 forbids network",
    )
    unhappy, happy = C.token_ids_for(["unhappy"]), C.token_ids_for(["happy"])
    assert unhappy & happy, "expected a shared subword id for unhappy/happy"

    seven, seventeen = C.token_ids_for(["seven"]), C.token_ids_for(["seventeen"])
    assert not (seven & seventeen), "expected no shared id for seven/seventeen"
    assert "seven" in "seventeen", "the substring relation must hold for the point"

    r = C.check_disjointness(["seven"], ["seventeen"], seven, seventeen)
    assert r["findings"] == [], r["findings"]


def test_g_p2_library_path_is_a_pure_function():
    """Tier-0 property: pre-computed ids mean no network, no model, no download.

    This is what makes the gate registerable in run_all.py. The check must be a
    pure function of its arguments whenever both id sets are supplied.
    """
    C, a, b, ia, ib = _prompt_pair("disjoint")
    r = C.check_disjointness(a, b, ia, ib)
    assert r["ok"]


def test_g_p2_reports_missing_ids_rather_than_passing_silently():
    """With no id sets the gate must not claim a pass — it cannot know.

    A silent pass here would be the 'check that cannot fail' failure mode: a
    caller that forgot the ids would read a green result.
    """
    C, a, b, _ia, _ib = _prompt_pair("disjoint")
    r = C.check_disjointness(a, b, None, None)
    assert r["ok"] is False
    assert r["token_ids"] is None
    assert "tokenizer" in r["reason"]


def test_g_p2_allows_a_documented_token_exception():
    """A configured exception must be honoured, and the count surfaced."""
    C, a, b, ia, ib = _prompt_pair("shared_token")
    r = C.check_disjointness(a, b, ia, ib, allow_token_ids={42256})
    assert r["findings"] == [], r["findings"]
    assert r["token_ids"]["n_allowed_exceptions"] == 1


def test_check_prefixed_gate_modules_are_discovered():
    """The runner must load `check_*.py` gates, not only `validate_*.py`.

    Spec §6 names gate modules under both prefixes. Globbing one of them
    silently omitted every `check_*` gate — `--gate G-P2` reported "no gate
    registered" while the module sat right there. Regression guard for that.
    """
    ids = {g.id for g in R.REGISTRY}
    assert "G-P2" in ids, (
        "G-P2 not registered — run_all._load_gate_modules is not discovering "
        "check_*.py modules")
# -------------------------------------------------------------- G-M gates
def test_g_m1_fires_on_two_status_labels():
    """The exact illegal state created while filing #29-#34."""
    import validate_program as V
    status, findings = V.check_label_cardinality(
        R.FIXTURES / "program_r1_two_status.json")
    assert status == "FAIL", f"expected FAIL, got {status}"
    assert any("2 status label" in f for f in findings), findings


def test_g_m1_fires_on_a_missing_kind():
    import validate_program as V
    status, findings = V.check_label_cardinality(
        R.FIXTURES / "program_r1_no_kind.json")
    assert status == "FAIL"
    assert any("0 kind label" in f for f in findings), findings


def test_g_m1_fires_on_a_misspelled_label():
    """Cardinality reads 1; only the vocabulary check catches a typo.

    A typo'd label silently divides the queue, which is the failure mode a
    count cannot see.
    """
    import validate_program as V
    status, findings = V.check_label_cardinality(
        R.FIXTURES / "program_r1_typo_status.json")
    assert status == "FAIL", f"expected FAIL, got {status}"
    assert any("outside the vocabulary" in f or "not a known" in f
               for f in findings), findings


def test_g_m2_fires_on_available_with_an_open_blocker():
    """The defect G-M1 cannot see: correct cardinality, illegal combination."""
    import validate_program as V
    status, findings = V.check_dependency_coherence(
        R.FIXTURES / "program_r2_available_blocked.json")
    assert status == "FAIL", f"expected FAIL, got {status}"
    assert any("must not be claimable" in f for f in findings), findings


def test_g_m2_skips_rather_than_passing_when_no_edges_are_recorded():
    """The vacancy guard.

    The first version returned PASS with an empty dependency graph — a green
    result computed from data it never had. It must SKIP with the reason.
    """
    import json
    import tempfile
    from pathlib import Path
    import validate_program as V
    d = json.loads((R.FIXTURES / "program_clean.json").read_text())
    for k, v in d.items():
        if not k.startswith("_"):
            v["blocked_by"] = []
    tmp = Path(tempfile.mkdtemp()) / "no_edges.json"
    tmp.write_text(json.dumps(d))
    status, findings = V.check_dependency_coherence(tmp)
    assert status == "SKIP", f"expected SKIP, got {status}"
    assert findings and "no `blocked_by` edges" in findings[0]


def test_g_m1_and_g_m2_pass_on_the_clean_fixture():
    import validate_program as V
    clean = R.FIXTURES / "program_clean.json"
    assert V.check_label_cardinality(clean) == ("PASS", [])
    assert V.check_dependency_coherence(clean) == ("PASS", [])


def test_real_cache_dependency_graph_is_not_vacuous():
    """The committed cache must carry real edges, or G-M2 is green for nothing.

    This is the regression guard for the vacuous-PASS defect: if a refresh stops
    reading dependencies, this fails rather than silently hollowing out G-M2.
    """
    import json
    import validate_program as V
    d = json.loads(V.ISSUE_CACHE.read_text())
    edges = sum(len(v.get("blocked_by") or []) for k, v in d.items()
                if not k.startswith("_"))
    assert edges > 0, ("the committed cache records no dependency edges — "
                       "refresh with tooling/program/issue_state.py, or G-M2 is "
                       "checking an empty graph")
    status, _ = V.check_dependency_coherence(V.ISSUE_CACHE)
    assert status in ("PASS", "FAIL"), f"expected PASS/FAIL, got {status}"


def test_real_cache_open_issues_carry_labels():
    """G-M1's input must be real: a refresh that drops labels hollows it out."""
    import json
    import validate_program as V
    d = json.loads(V.ISSUE_CACHE.read_text())
    open_with_labels = [
        k for k, v in d.items()
        if not k.startswith("_") and v.get("state") == "OPEN" and v.get("labels")
    ]
    assert open_with_labels, ("no OPEN cached issue carries labels — the cache "
                              "predates label capture; refresh it")


def test_label_delta_never_adds_and_removes_the_same_label():
    """The bug that stripped #30's status.

    `_apply_label_delta` must not put a label in both `to_add` and `to_remove`:
    `gh` applies the removal, leaving zero labels in the family while reporting
    success. Found by running set-status with the status already present.
    """
    import importlib
    sys.path.insert(0, str(REPO / "tooling" / "program"))
    import issue_state as S
    importlib.reload(S)

    current = ["status:claimed", "kind:gate"]
    to_add, to_remove = S._apply_label_delta(30, "status", "status:claimed", current)
    assert to_add == [], f"already-present label must not be re-added: {to_add}"
    assert to_remove == [], f"the target must not be removed: {to_remove}"

    # Changing status removes the sibling and adds the target, never overlapping.
    to_add, to_remove = S._apply_label_delta(
        30, "status", "status:done", ["status:claimed", "kind:gate"])
    assert to_add == ["status:done"], to_add
    assert to_remove == ["status:claimed"], to_remove
    assert not (set(to_add) & set(to_remove)), "add/remove must not overlap"


def test_set_status_refuses_an_out_of_vocabulary_value():
    """A refusal must happen before mutation, so nothing is written."""
    import importlib
    sys.path.insert(0, str(REPO / "tooling" / "program"))
    import issue_state as S
    importlib.reload(S)
    try:
        S.set_status(999999, "status:bogus")
    except S.InvariantViolation:
        return
    raise AssertionError("set_status accepted an out-of-vocabulary status")


def test_validate_target_flags_two_status_labels():
    import importlib
    sys.path.insert(0, str(REPO / "tooling" / "program"))
    import issue_state as S
    importlib.reload(S)
    problems = S.validate_target(
        30, ["status:available", "status:claimed", "kind:gate"])
    assert problems, "two status labels must be flagged before mutation"
    assert any("2 status labels" in p for p in problems), problems


# ------------------------------------------------- DEC-035: kind vocabulary
def test_kind_vocabulary_is_single_sourced():
    """G-M1 and the setter must read the same list, or they can disagree.

    Before DEC-035 the vocabulary lived in two Python files plus the spec prose.
    A session editing one would have produced a setter that refuses a label the
    gate accepts — the same class as the coverage-map and gate-count drifts.
    """
    import importlib
    sys.path.insert(0, str(REPO / "tooling" / "program"))
    import validate_program as V
    import issue_state as S
    importlib.reload(S)
    assert V.load_kind_vocabulary() == S.load_kind_vocabulary()
    assert V.KIND_VOCABULARY_FILE.name == "kind_vocabulary.txt"


def test_kind_vocabulary_includes_spec():
    """DEC-035 added kind:spec; both readers must see it."""
    import validate_program as V
    assert "kind:spec" in V.load_kind_vocabulary()


def test_g_m1_skips_rather_than_passing_without_a_vocabulary(monkeypatch):
    """A gate validating against no vocabulary would accept every label.

    It must SKIP with a reason — never PASS, never crash.
    """
    import json
    import tempfile
    from pathlib import Path
    import validate_program as V
    d = json.loads((R.FIXTURES / "program_clean.json").read_text())
    tmp = Path(tempfile.mkdtemp()) / "c.json"
    tmp.write_text(json.dumps(d))
    monkeypatch.setattr(V, "KIND_VOCABULARY_FILE", Path("/nonexistent.txt"))
    status, findings = V.check_label_cardinality(tmp)
    assert status == "SKIP", f"expected SKIP, got {status}"
    assert findings and "vocabulary unavailable" in findings[0], findings


def test_setter_refuses_kind_without_a_vocabulary(monkeypatch):
    """The mutator raises instead of writing an unvalidatable label."""
    import importlib
    sys.path.insert(0, str(REPO / "tooling" / "program"))
    import issue_state as S
    importlib.reload(S)
    monkeypatch.setattr(S, "KIND_VOCABULARY_FILE", type(S.KIND_VOCABULARY_FILE)("/nope.txt"))
    try:
        S.load_kind_vocabulary()
    except S.InvariantViolation:
        return
    raise AssertionError("setter loaded an empty vocabulary without raising")


def test_g_m1_fires_on_an_out_of_vocabulary_kind():
    """The behaviour that caught the misfiling: kind:methodology is not a kind.

    Note the fixture choice: G-M1 only checks OPEN issues, so the mutation must
    land on one (#29-#31 are open; #28 is closed and will be skipped). The first
    version of this test patched whichever entry came first — #28, closed — and
    failed for the wrong reason.
    """
    import json
    import tempfile
    from pathlib import Path
    import validate_program as V
    d = json.loads((R.FIXTURES / "program_clean.json").read_text())
    target = next(k for k, v in d.items()
                  if not k.startswith("_") and v.get("state") == "OPEN")
    d[target]["labels"] = [l for l in d[target]["labels"]
                           if not l.startswith("kind:")] + ["kind:notavocabvalue"]
    tmp = Path(tempfile.mkdtemp()) / "c.json"
    tmp.write_text(json.dumps(d))
    status, findings = V.check_label_cardinality(tmp)
    assert status == "FAIL", f"expected FAIL, got {status}"
    assert any("not a known kind" in f for f in findings), findings
