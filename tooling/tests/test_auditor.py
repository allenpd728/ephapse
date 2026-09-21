#!/usr/bin/env python3
"""Offline tests for auditor.py — no network, no token.

Run: python3 tooling/tests/test_auditor.py
  or: python3 -m pytest tooling/tests/test_auditor.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()


def find_auditor() -> Path:
    for parent in HERE.parents:
        for sub in ("tooling", "tools"):
            candidate = parent / sub / "auditor.py"
            if candidate.exists():
                return candidate
    raise FileNotFoundError("auditor.py not found relative to " + str(HERE))


AUD = find_auditor()
spec = importlib.util.spec_from_file_location("auditor", AUD)
aud = importlib.util.module_from_spec(spec)
sys.modules["auditor"] = aud
spec.loader.exec_module(aud)


def init_repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "README.md").write_text("# t\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)
    return path


# ---- committed artifacts -------------------------------------------------

def test_tracked_artifact_detected(tmp_path):
    root = init_repo(tmp_path)
    (root / ".DS_Store").write_text("junk")
    subprocess.run(["git", "add", "-f", ".DS_Store"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "add cruft"], cwd=root, check=True)
    findings = aud.check_committed_artifacts(root)
    assert any("DS_Store" in f.title for f in findings), findings


def test_tracked_pycache_detected(tmp_path):
    root = init_repo(tmp_path)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_text("x")
    subprocess.run(["git", "add", "-f", "__pycache__/x.pyc"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "add pyc"], cwd=root, check=True)
    assert aud.check_committed_artifacts(root)


def test_untracked_pycache_is_not_reported(tmp_path):
    """A local test run leaving __pycache__ is normal noise. Reporting it would
    make the check cry wolf and get ignored."""
    root = init_repo(tmp_path)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_text("x")
    assert aud.check_committed_artifacts(root) == []


def test_untracked_ds_store_is_not_reported(tmp_path):
    root = init_repo(tmp_path)
    (root / ".DS_Store").write_text("junk")
    assert aud.check_committed_artifacts(root) == []


def test_clean_tree_has_no_artifact_findings(tmp_path):
    root = init_repo(tmp_path)
    assert aud.check_committed_artifacts(root) == []


# ---- status log contract -------------------------------------------------

def test_status_log_contract_flags_bad_json(tmp_path):
    root = init_repo(tmp_path)
    (root / "status_log.jsonl").write_text('{"timestamp":"x"}\nnot json\n')
    findings = aud.check_status_log_contract(root)
    assert findings and "line 2" in findings[0].body


def test_status_log_contract_flags_missing_timestamp(tmp_path):
    root = init_repo(tmp_path)
    (root / "status_log.jsonl").write_text('{"flow":{}}\n')
    findings = aud.check_status_log_contract(root)
    assert findings and "missing timestamp" in findings[0].body


def test_status_log_contract_flags_non_object_trl(tmp_path):
    root = init_repo(tmp_path)
    (root / "status_log.jsonl").write_text('{"timestamp":"x","trl":5}\n')
    findings = aud.check_status_log_contract(root)
    assert findings and "trl is not an object" in findings[0].body


def test_status_log_contract_accepts_valid(tmp_path):
    root = init_repo(tmp_path)
    (root / "status_log.jsonl").write_text('{"timestamp":"2026-01-01T00:00:00Z","trl":{"a":3}}\n')
    assert aud.check_status_log_contract(root) == []


def test_status_log_absent_is_not_a_finding(tmp_path):
    root = init_repo(tmp_path)
    assert aud.check_status_log_contract(root) == []


# ---- status entry carries trl/flow forward -------------------------------

def test_status_entry_carries_trl_and_flow_forward(tmp_path):
    """The dashboard reads trl from the LAST line. An audit snapshot that dropped
    it would blank the TRL panel for every viewer until the next sweep."""
    root = init_repo(tmp_path)
    (root / "status_log.jsonl").write_text(json.dumps({
        "timestamp": "2026-01-01T00:00:00Z",
        "trl": {"pipeline": 6},
        "flow": {"wip": 1, "open_total": 4},
        "notes": "sweep",
    }) + "\n")
    entry = aud.build_status_entry(root, "2026-01-02T00:00:00Z", "abc1234", 2, 1)
    assert entry["trl"] == {"pipeline": 6}
    assert entry["flow"] == {"wip": 1, "open_total": 4}
    assert "abc1234"[:7] in entry["notes"]
    assert entry["timestamp"] == "2026-01-02T00:00:00Z"


def test_status_entry_on_empty_log_has_no_trl_key(tmp_path):
    root = init_repo(tmp_path)
    entry = aud.build_status_entry(root, "2026-01-02T00:00:00Z", "abc1234", 0, 0)
    assert "trl" not in entry and "flow" not in entry
    assert entry["notes"]


def test_append_status_entry_is_append_only(tmp_path):
    root = init_repo(tmp_path)
    log = root / "status_log.jsonl"
    log.write_text('{"timestamp":"a"}\n')
    aud.append_status_entry(root, {"timestamp": "b", "notes": "audit"})
    lines = [l for l in log.read_text().splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["timestamp"] == "a"
    assert json.loads(lines[1])["timestamp"] == "b"


def test_append_status_entry_handles_missing_newline(tmp_path):
    root = init_repo(tmp_path)
    log = root / "status_log.jsonl"
    log.write_text('{"timestamp":"a"}')          # no trailing newline
    aud.append_status_entry(root, {"timestamp": "b"})
    lines = [l for l in log.read_text().splitlines() if l.strip()]
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


# ---- checkpoint ----------------------------------------------------------

def test_state_round_trip(tmp_path):
    root = init_repo(tmp_path)
    aud.save_state(root, "deadbeef", "2026-01-01T00:00:00Z")
    state = aud.load_state(root)
    assert state["last_audited_sha"] == "deadbeef"
    assert state["last_audited_date"] == "2026-01-01"


def test_state_missing_is_empty_dict(tmp_path):
    root = init_repo(tmp_path)
    assert aud.load_state(root) == {}


def test_state_corrupt_is_empty_dict(tmp_path):
    root = init_repo(tmp_path)
    (root / "status").mkdir()
    (root / "status" / "auditor_state.json").write_text("{not json")
    assert aud.load_state(root) == {}


def test_state_file_lives_under_status_dir(tmp_path):
    """Must not invent a new state location: status/ already exists in this family."""
    root = init_repo(tmp_path)
    aud.save_state(root, "a", "2026-01-01T00:00:00Z")
    assert (root / "status" / "auditor_state.json").exists()
    assert aud.STATE_PATH == "status/auditor_state.json"


# ---- commit range --------------------------------------------------------

def test_commits_between_range(tmp_path):
    root = init_repo(tmp_path)
    first = aud.head_sha(root)
    (root / "a.txt").write_text("a")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "second"], cwd=root, check=True)
    got = aud.commits_between(root, first, aud.head_sha(root))
    assert len(got) == 1 and got[0]["subject"] == "second"


def test_commits_between_no_change_is_empty(tmp_path):
    root = init_repo(tmp_path)
    sha = aud.head_sha(root)
    assert aud.commits_between(root, sha, sha) == []


def test_first_run_range_is_time_bounded_not_unbounded(tmp_path):
    """With no checkpoint the digest must not dump all history into the table."""
    root = init_repo(tmp_path)
    for i in range(5):
        (root / f"f{i}.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", f"c{i}"], cwd=root, check=True)
    got = aud.commits_between(root, "", aud.head_sha(root))
    # All five are within 24h in a test repo, so all appear -- but the call must
    # be a --since query, never an unbounded `-200` dump. Pin the argument shape.
    assert len(got) >= 1
    src = AUD.read_text()
    assert '"--since=24 hours ago"' in src
    assert '"-200"' not in src


def test_head_sha_is_40_hex(tmp_path):
    root = init_repo(tmp_path)
    sha = aud.head_sha(root)
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)


# ---- signature / dedup ---------------------------------------------------

def test_signature_is_stable_and_check_scoped(tmp_path):
    f1 = aud.Finding("gate-health", "Bugs & hygiene", "Gate failed", "body one", "gate-runner:x")
    f2 = aud.Finding("gate-health", "Bugs & hygiene", "DIFFERENT title", "body two", "gate-runner:x")
    assert f1.signature() == f2.signature()      # dedup survives an edit to the body
    f3 = aud.Finding("stale-todo", "Bugs & hygiene", "t", "b", "gate-runner:x")
    assert f3.signature() != f1.signature()      # different check -> different key


def test_find_existing_matches_title_or_body():
    issues = [{"number": 1, "title": "[auditor:gate-health] gate-runner:x", "body": ""},
              {"number": 2, "title": "other", "body": "see [auditor:stale-todo] f.py"}]
    assert aud.find_existing(issues, "[auditor:gate-health] gate-runner:x")["number"] == 1
    assert aud.find_existing(issues, "[auditor:stale-todo] f.py")["number"] == 2
    assert aud.find_existing(issues, "[auditor:committed-artifact] nope") is None


# ---- safety invariants ---------------------------------------------------

def test_claimable_labels_are_never_used():
    """The auditor must never mark work claimable -- only the human does that."""
    joined = " ".join([aud.LABEL_PROPOSED, aud.LABEL_REVISE, aud.LABEL_HOLD])
    for label in aud.CLAIMABLE_LABELS:
        assert label not in joined
    assert aud.LABEL_HOLD == "on-hold"


def test_source_never_adds_claimable_label():
    src = AUD.read_text()
    # A claimable label may be *named* (to document the ban) but never *used* as
    # an issue label in writes.
    for label in aud.CLAIMABLE_LABELS:
        assert f'"{label}"' not in src.replace('CLAIMABLE_LABELS = {"status:available", "status:claimed"}', ""), label


def test_source_never_closes_or_merges():
    src = AUD.read_text()
    for bad in ('"state": "closed"', "merge_pull_request", "pulls/", "DELETE"):
        assert bad not in src, bad


def test_source_never_edits_repo_files_except_state_and_log():
    src = AUD.read_text()
    # Only these two paths may be written.
    assert "STATE_PATH" in src and "STATUS_LOG" in src
    for forbidden in ("unlink(", "shutil.rmtree", "os.remove"):
        assert forbidden not in src, forbidden


def test_gate_entrypoint_detects_known_runners(tmp_path):
    root = init_repo(tmp_path)
    assert aud.gate_entrypoint(root) is None
    (root / "tooling" / "gates").mkdir(parents=True)
    (root / "tooling" / "gates" / "run_all.py").write_text("")
    cmd, label = aud.gate_entrypoint(root)
    assert cmd == ["python3", "tooling/gates/run_all.py", "--json"]
    assert "run_all.py" in label


def test_gate_entrypoint_detects_muse_runner(tmp_path):
    root = init_repo(tmp_path)
    (root / "tools").mkdir()
    (root / "tools" / "run_tests.sh").write_text("#!/bin/bash\n")
    cmd, label = aud.gate_entrypoint(root)
    assert cmd == ["bash", "tools/run_tests.sh"]


def test_gate_health_missing_runner_is_catchall_finding(tmp_path):
    root = init_repo(tmp_path)
    findings = aud.check_gate_health(root)
    assert len(findings) == 1
    assert findings[0].category == aud.CATEGORY_CATCHALL
    assert findings[0].check == "gate-health"


def test_gate_health_passing_runner_is_silent(tmp_path):
    root = init_repo(tmp_path)
    (root / "tools").mkdir()
    (root / "tools" / "run_tests.sh").write_text("#!/bin/bash\nexit 0\n")
    assert aud.check_gate_health(root) == []


def test_gate_health_failing_runner_is_bugs_finding(tmp_path):
    root = init_repo(tmp_path)
    (root / "tools").mkdir()
    (root / "tools" / "run_tests.sh").write_text("#!/bin/bash\necho boom >&2\nexit 3\n")
    findings = aud.check_gate_health(root)
    assert len(findings) == 1
    assert findings[0].category == aud.CATEGORY_BUGS
    assert "boom" in findings[0].body


def test_gate_health_does_not_report_passing_gate_findings(tmp_path):
    """A gate that PASSes while listing findings is the planted-fixture shape.
    Those are proof the gate can fire -- NOT repo problems."""
    root = init_repo(tmp_path)
    (root / "tools").mkdir()
    (root / "tools" / "run_tests.sh").write_text(
        "#!/bin/bash\necho 'G-P2 PASS: 1 shared token id — planted fixture'\nexit 0\n")
    assert aud.check_gate_health(root) == []


# ---- crash isolation -----------------------------------------------------

def test_a_crashing_check_does_not_abort_the_run(tmp_path, monkeypatch=None):
    root = init_repo(tmp_path)
    def boom(_root):
        raise RuntimeError("kaboom")
    original = aud.REGISTRY[:]
    try:
        aud.REGISTRY[:] = [boom, aud.check_status_log_contract]
        findings = aud.run_checks(root)
    finally:
        aud.REGISTRY[:] = original
    assert any(f.check == "check-crashed" for f in findings)
    assert any("kaboom" in f.body for f in findings)


# ---- digest --------------------------------------------------------------

def test_digest_body_lists_findings_and_buckets():
    f = aud.Finding("stale-todo", aud.CATEGORY_BUGS, "Stale TODO", "old marker", "a.py")
    body = aud.build_digest_body("2026-01-01T00:00:00Z", "abc1234", [], [f], [], [])
    assert aud.CATEGORY_BUGS in body
    assert "Stale TODO" in body
    assert "on-hold" in body


def test_digest_body_says_nothing_when_clean():
    body = aud.build_digest_body("2026-01-01T00:00:00Z", "abc1234", [], [], [], [])
    assert "Nothing flagged" in body


def test_digest_title_is_date_scoped():
    assert aud.digest_title("2026-01-01T00:00:00Z") == "Auditor digest — 2026-01-01"


# ---- doc refs ------------------------------------------------------------

def test_doc_relative_ref_resolves(tmp_path):
    """A bare filename in docs/reference/ means the sibling file, not a root file."""
    root = init_repo(tmp_path)
    (root / "docs" / "reference").mkdir(parents=True)
    (root / "docs" / "reference" / "SIBLING.md").write_text("hi\n")
    (root / "docs" / "reference" / "x.md").write_text("see `SIBLING.md`\n")
    assert aud.check_dangling_doc_refs(root) == []


def test_docs_root_relative_ref_resolves(tmp_path):
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "GUIDE.md").write_text("hi\n")
    (root / "docs" / "reference").mkdir()
    (root / "docs" / "reference" / "x.md").write_text("see `GUIDE.md`\n")
    assert aud.check_dangling_doc_refs(root) == []


def test_cross_repo_citation_is_not_reported(tmp_path):
    """`Maith \`EXPERIMENT_MEASUREMENT.md\`` names a sibling repo's file."""
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text("| Maith `EXPERIMENT_MEASUREMENT.md` | ref |\n")
    assert aud.check_dangling_doc_refs(root) == []


def test_cross_repo_citation_multiline_window(tmp_path):
    """A heading naming the sibling repo, then bare filenames on following lines."""
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text(
        "- **`lean/PleaNP/Circuits/` on `dev`** contains:\n"
        "  - `Basic.lean` — gates\n"
        "  - `AC0.lean` — parity\n"
        "  - `Monotone.lean` — monotonicity\n")
    assert aud.check_dangling_doc_refs(root) == []


def test_genuine_dangling_lean_ref_still_reported(tmp_path):
    """The cross-repo suppression must not swallow real drift."""
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text("nothing else mentioned\nsee `Gone.lean` here\n")
    findings = aud.check_dangling_doc_refs(root)
    assert findings and "Gone.lean" in findings[0].body


def test_dangling_refs_are_aggregated_into_one_finding(tmp_path):
    """One issue listing N dead paths, not N issues -- otherwise the digest is noise."""
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text(
        "see `Gone1.lean` and `Gone2.lean` and `Gone3.lean`\n")
    findings = aud.check_dangling_doc_refs(root)
    assert len(findings) == 1
    assert "3 " in findings[0].title
    assert findings[0].signature() == "[auditor:dangling-doc-ref] docs"


def test_numbered_vendored_path_is_not_reported(tmp_path):
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text("see `02_server/10_script.py`\n")
    assert aud.check_dangling_doc_refs(root) == []


def test_dangling_doc_ref_detected(tmp_path):
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text("see `docs/missing_file.md` for details\n")
    findings = aud.check_dangling_doc_refs(root)
    assert findings and "missing_file.md" in findings[0].body


def test_resolving_doc_ref_is_clean(tmp_path):
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "there.md").write_text("hi\n")
    (root / "docs" / "x.md").write_text("see `docs/there.md`\n")
    assert aud.check_dangling_doc_refs(root) == []


def test_placeholder_refs_ignored(tmp_path):
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text("see `<name>.md` and `docs/*.md`\n")
    assert aud.check_dangling_doc_refs(root) == []


# ---- stale owner slug (contradiction) ------------------------------------

def test_retired_slug_outside_frozen_record_is_reported(tmp_path):
    root = init_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "GUIDE.md").write_text("clone https://github.com/allenpd728/x.git\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=root, check=True)
    findings = aud.check_stale_owner_refs(root)
    assert findings and "GUIDE.md" in findings[0].body
    assert findings[0].category == aud.CATEGORY_ARCH


def test_retired_slug_in_frozen_record_is_not_reported(tmp_path):
    """docs/decisions records the slug as it was; rewriting it would make it false."""
    root = init_repo(tmp_path)
    (root / "docs" / "decisions").mkdir(parents=True)
    (root / "docs" / "decisions" / "LOG.md").write_text("login allenpd728, id 26507447\n")
    assert aud.check_stale_owner_refs(root) == []


def test_auditor_source_never_flags_itself(tmp_path):
    """The slug list and the ban's explanation live in auditor.py."""
    root = init_repo(tmp_path)
    (root / "tooling").mkdir()
    (root / "tooling" / "auditor.py").write_text('RETIRED = ("allenpd728",)\n')
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=root, check=True)
    assert aud.check_stale_owner_refs(root) == []


def test_no_retired_slug_is_clean(tmp_path):
    root = init_repo(tmp_path)
    (root / "README.md").write_text("owner is philipdallen\n")
    assert aud.check_stale_owner_refs(root) == []


# ---- committed secrets ---------------------------------------------------

def test_private_key_block_is_reported(tmp_path):
    root = init_repo(tmp_path)
    (root / "k.pem").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=root, check=True)
    findings = aud.check_committed_secrets(root)
    assert findings and findings[0].category == aud.CATEGORY_SECURITY
    assert "private-key" in findings[0].title


def test_aws_key_id_is_reported(tmp_path):
    root = init_repo(tmp_path)
    (root / "conf.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n')
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=root, check=True)
    assert any("aws" in f.title for f in aud.check_committed_secrets(root))


def test_secret_value_is_never_echoed_into_the_finding(tmp_path):
    """The issue is public. Reproducing the value would complete the leak."""
    root = init_repo(tmp_path)
    secret = "AKIAIOSFODNN7EXAMPLE"
    (root / "conf.py").write_text(f'KEY = "{secret}"\n')
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=root, check=True)
    findings = aud.check_committed_secrets(root)
    assert findings
    for f in findings:
        assert secret not in f.body and secret not in f.title


def test_untracked_secret_is_not_reported(tmp_path):
    root = init_repo(tmp_path)
    (root / ".env").write_text("AWS=AKIAIOSFODNN7EXAMPLE\n")
    assert aud.check_committed_secrets(root) == []


def test_clean_repo_has_no_secret_findings(tmp_path):
    root = init_repo(tmp_path)
    assert aud.check_committed_secrets(root) == []


def test_secret_findings_are_capped(tmp_path):
    root = init_repo(tmp_path)
    for i in range(aud.MAX_SECRET_FINDINGS + 4):
        (root / f"k{i}.pem").write_text("-----BEGIN PRIVATE KEY-----\nx\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=root, check=True)
    assert len(aud.check_committed_secrets(root)) == aud.MAX_SECRET_FINDINGS


# ---- workflow hardening --------------------------------------------------

def _wf(root, name, text):
    d = root / ".github" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text)


def test_workflow_without_permissions_is_reported(tmp_path):
    root = init_repo(tmp_path)
    _wf(root, "ci.yml", "name: ci\non:\n  push:\njobs:\n  a:\n    runs-on: ubuntu-latest\n")
    findings = aud.check_workflow_hardening(root)
    assert any("no top-level" in f.title for f in findings)


def test_workflow_with_permissions_is_silent(tmp_path):
    root = init_repo(tmp_path)
    _wf(root, "ci.yml", "name: ci\non:\n  push:\npermissions:\n  contents: read\n"
                        "jobs:\n  a:\n    runs-on: ubuntu-latest\n")
    assert aud.check_workflow_hardening(root) == []


def test_untrusted_interpolation_is_reported(tmp_path):
    root = init_repo(tmp_path)
    _wf(root, "p.yml",
        "name: p\non:\n  pull_request_target:\npermissions:\n  contents: read\n"
        "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo ${{ github.event.pull_request.title }}\n")
    findings = aud.check_workflow_hardening(root)
    assert any("interpolated" in f.title for f in findings)


def test_step_scoped_permissions_does_not_count_as_top_level(tmp_path):
    """A step-scoped permissions does not set the job default."""
    root = init_repo(tmp_path)
    _wf(root, "ci.yml", "name: ci\non:\n  push:\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
                        "    steps:\n      - run: echo hi\n        permissions:\n          contents: read\n")
    findings = aud.check_workflow_hardening(root)
    assert any("no top-level" in f.title for f in findings)


def test_pr_head_checkout_is_reported(tmp_path):
    root = init_repo(tmp_path)
    _wf(root, "t.yml",
        "name: t\non:\n  pull_request_target:\npermissions:\n  contents: read\n"
        "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha }}\n"
        "      - run: echo ${{ github.event.pull_request.title }}\n")
    findings = aud.check_workflow_hardening(root)
    assert any("PR head ref" in f.title for f in findings)


def test_env_pattern_is_not_flagged_as_injection(tmp_path):
    """Passing the value through `env:` is the FIX. Flagging it would punish the
    correct pattern and bury the real finding."""
    root = init_repo(tmp_path)
    _wf(root, "p.yml",
        "name: p\non:\n  issue_comment:\npermissions:\n  issues: write\n"
        "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo \"$BODY\"\n        env:\n"
        "          BODY: ${{ github.event.comment.body }}\n")
    findings = aud.check_workflow_hardening(root)
    assert not any("interpolated" in f.title for f in findings), findings


def test_no_workflows_dir_is_clean(tmp_path):
    root = init_repo(tmp_path)
    assert aud.check_workflow_hardening(root) == []


# ---- dependency advisories (network injected, stays offline) -------------

def test_advisory_hit_is_reported(tmp_path):
    root = init_repo(tmp_path)
    (root / "requirements.txt").write_text("torch==2.14.0\n")
    def fake(_pkgs):
        return {"results": [{"vulns": [{"id": "CVE-2026-1", "summary": "bad"}]}]}
    findings = aud.check_dependency_advisories(root, query=fake)
    assert findings and "CVE-2026-1" in findings[0].body
    assert findings[0].category == aud.CATEGORY_SECURITY


def test_advisory_clean_result_is_silent(tmp_path):
    root = init_repo(tmp_path)
    (root / "requirements.txt").write_text("torch==2.14.0\n")
    assert aud.check_dependency_advisories(root, query=lambda p: {"results": [{}]}) == []


def test_advisory_lookup_failure_is_reported_not_swallowed(tmp_path):
    """An unavailable check and a clean result must not look the same."""
    root = init_repo(tmp_path)
    (root / "requirements.txt").write_text("torch==2.14.0\n")
    def boom(_pkgs):
        raise OSError("network down")
    findings = aud.check_dependency_advisories(root, query=boom)
    assert findings and findings[0].category == aud.CATEGORY_CATCHALL
    assert "did not run" in findings[0].title


def test_unpinned_requirement_is_skipped(tmp_path):
    root = init_repo(tmp_path)
    (root / "requirements.txt").write_text("numpy\n# comment\ntorch==2.14.0\n")
    assert aud.parse_requirements(root) == [("torch", "2.14.0")]


def test_no_requirements_file_is_silent(tmp_path):
    root = init_repo(tmp_path)
    assert aud.check_dependency_advisories(root, query=lambda p: {"results": []}) == []


def test_requirements_extras_and_comments_parse(tmp_path):
    root = init_repo(tmp_path)
    (root / "requirements.txt").write_text("torch[cpu]==2.14.0+cpu  # pinned\n")
    assert aud.parse_requirements(root) == [("torch", "2.14.0+cpu")]


# ---- security category is wired into the digest --------------------------

def test_security_category_appears_in_digest():
    f = aud.Finding("workflow-hardening", aud.CATEGORY_SECURITY, "No perms", "b", "ci.yml")
    body = aud.build_digest_body("2026-01-01T00:00:00Z", "abc1234", [], [f], [], [])
    assert aud.CATEGORY_SECURITY in body
    assert "No perms" in body


def test_new_checks_are_registered():
    for fn in (aud.check_stale_owner_refs, aud.check_committed_secrets,
               aud.check_workflow_hardening, aud.check_dependency_advisories):
        assert fn in aud.REGISTRY, fn.__name__


# ---- json output mode ----------------------------------------------------

def test_json_mode_writes_nothing_and_is_parseable(tmp_path):
    """--json is read-only inspection: it must not write a status line or checkpoint."""
    root = init_repo(tmp_path)
    (root / "extra.txt").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=root, check=True)
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = aud.main(["--repo", "o/r", "--root", str(root), "--json"])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert "findings" in payload and "sha" in payload
    assert payload["finding_count"] == len(payload["findings"])
    assert not (root / "status_log.jsonl").exists()
    assert not (root / "status").exists()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        code = fn.__code__.co_argcount
        try:
            if code == 0:
                fn()
            else:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            print(f"PASS {name}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            print(f"FAIL {name}: {exc!r}")
    print()
    print("ok" if not fails else f"{fails} failed")
    raise SystemExit(1 if fails else 0)