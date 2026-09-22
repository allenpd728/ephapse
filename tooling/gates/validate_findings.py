#!/usr/bin/env python3
"""G-E1, G-E2, G-E6, G-E7 — findings.jsonl schema and evidence gates (issue #10).

The checks that decide whether a record is *well-formed evidence at all*. The
claim-consistency rules (G-E3/E4/E5/E8) are separate — issue #19 adds them here.

| ID   | Check |
|------|-------|
| G-E1 | Schema — parses, required keys present, no unknown keys |
| G-E2 | `null_model`, `correction`, `n` non-empty — issue #4's evidence bar, mechanically |
| G-E6 | Append-only — line count >= a committed high-water mark |
| G-E7 | `issue` names a real closed-done issue; `run_id` matches the format |

Two spec §10 questions had to be resolved to build this; both resolutions are
recorded in the module and in the done comment:

**Q3 — schema vs header prose, which is authoritative?** The *gate* is, per the
spec's suggestion, but with a deliberate deviation: G-E1 does **not** reject
unknown keys. The three committed records carry `kind`, `injection`, `result`,
and `note`, which the header prose never listed. Rejecting them would fail
evidence that was written in good faith and is currently the project's only
recorded result. Instead:
  * a fixed set of REQUIRED keys (from the header prose) must be present;
  * keys may not be *silently* added — every extra key must appear in
    KNOWN_EXTENSIONS below, so an unknown key still fails.
This keeps the gate strict about the schema being *declared* while not
retroactively invalidating real records. The header's required-key list and the
gate's REQUIRED set are identical, and the header's "Extension keys" section
documents the KNOWN_EXTENSIONS list, so the prose and the gate agree on both
sets. `test_findings_header_declares_every_extension_key` fails if a key is
added to KNOWN_EXTENSIONS without a matching header line (issue #25).

**Q4 — does G-E6 need history?** No: a committed high-water mark. The clone is
shallow, so git history is unavailable; the gate reads
`findings.highwater` (a committed integer) and requires the current record count
to be >= it. Raising the mark is a separate, reviewable commit.

**G-E7 degrades to SKIP, not failure.** It needs GitHub issue state, which tier 0
must not fetch. It reads a committed cache (`tests/fixture_issue_state.json` at
the repo root: `{"<issue>": {"state": "CLOSED", "done": true}}`). When the cache
is absent or lacks the issue, the gate returns SKIP with the reason — never a
pass, never a silent success. This follows Maith's G2-5 precedent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from run_all import Gate, register           # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
FINDINGS = REPO / "findings.jsonl"
HIGHWATER = REPO / "findings.highwater"
ISSUE_CACHE = REPO / "tests" / "fixture_issue_state.json"

# From the findings.jsonl header prose. The gate's REQUIRED set and the prose
# list are identical; keep them in sync in one place.
REQUIRED = (
    "ts", "issue", "run_id", "model", "revision", "dtype", "sae", "layer",
    "feature_id", "hook", "inputs_a", "inputs_b", "activation_a", "activation_b",
    "null_model", "correction", "n", "statistic", "p_corrected",
    "confounds_checked", "confounds_fired", "paraphrase_controls",
    "paraphrase_survived", "intervention", "causal_claim", "verdict",
)

# Extensions the committed records actually use. An extra key not listed here
# fails G-E1 — the point is to make additions explicit, not to freeze the schema.
#
# `input_disjointness` was added when CI first ran this suite (issue #13): the
# real log's issue-3 record carries it as the G-P2 evidence (the shared-tokenizer
# id count), so G-E1 was firing on the repo's own committed record. Nothing had
# ever run the suite, so the drift was invisible. Adding it here is the sanctioned
# path — the gate's message names this list precisely so an addition is a
# reviewable edit rather than a silent schema change.
KNOWN_EXTENSIONS = ("kind", "injection", "result", "note", "input_disjointness")

# G-E2: the evidence bar from issue #4 and the header. Non-empty means: present,
# not None, not "", not an empty list/dict.
EVIDENCE_KEYS = ("null_model", "correction", "n")

RUN_ID_RE = re.compile(r"^\d{8}-\d{4}-[A-Za-z0-9]{4}$")


def _read_records(path: Path) -> tuple[list[dict], list[str]]:
    """Parse the JSONL. Returns (records, parse_errors)."""
    records: list[dict] = []
    errors: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {lineno}: not valid JSON ({e.msg})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"line {lineno}: record is {type(obj).__name__}, not an object")
            continue
        records.append(obj)
    return records, errors


def _empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple)):
        return len(value) == 0
    return False


# ------------------------------------------------------------------- G-E1
def check_schema(path: Path) -> list[str]:
    """G-E1: parses, required keys present, no unknown keys."""
    findings: list[str] = []
    records, errors = _read_records(path)
    findings.extend(f"G-E1 {e}" for e in errors)
    for i, rec in enumerate(records, 1):
        missing = [k for k in REQUIRED if k not in rec]
        if missing:
            findings.append(f"G-E1 record {i}: missing required key(s) "
                            f"{', '.join(missing)}")
        unknown = [k for k in rec if k not in REQUIRED and k not in KNOWN_EXTENSIONS]
        if unknown:
            findings.append(f"G-E1 record {i}: unknown key(s) {', '.join(unknown)} "
                            f"— add to KNOWN_EXTENSIONS if intentional")
    return findings


# ------------------------------------------------------------------- G-E2
def check_evidence(path: Path) -> list[str]:
    """G-E2: null_model, correction, n must be non-empty. Issue #4's bar."""
    findings: list[str] = []
    records, _ = _read_records(path)
    for i, rec in enumerate(records, 1):
        for k in EVIDENCE_KEYS:
            if k not in rec:
                findings.append(f"G-E2 record {i}: '{k}' absent (see G-E1)")
            elif _empty(rec[k]):
                findings.append(f"G-E2 record {i}: '{k}' is empty — a record "
                                f"without it is not evidence (issue #4)")
    return findings


# ------------------------------------------------------------------- G-E6
def check_append_only(path: Path) -> list[str]:
    """G-E6: record count >= committed high-water mark.

    Deliberately count-based, not content-based: the clone is shallow so prior
    revisions are unavailable (spec §10 Q4). Deleting a line lowers the count and
    fires; editing a line in place does not — that limitation is real and is the
    reason the mark is a committed, reviewable number rather than a guess.
    """
    findings: list[str] = []
    records, _ = _read_records(path)
    n = len(records)

    mark_path = path.parent / HIGHWATER.name
    if not mark_path.exists():
        return [f"G-E6 high-water mark missing: {HIGHWATER.name} — cannot "
                f"demonstrate the log has not shrunk"]
    try:
        mark = int(mark_path.read_text(encoding="utf-8").strip())
    except ValueError:
        return [f"G-E6 high-water mark is not an integer: {mark_path.name}"]

    if n < mark:
        findings.append(f"G-E6 append-only violated: {n} record(s) present but "
                        f"the committed mark is {mark} — records appear to have "
                        f"been removed")
    if n > mark:
        findings.append(f"G-E6 high-water mark stale: {n} record(s) present, "
                        f"mark is {mark} — raise {HIGHWATER.name} to {n} in the "
                        f"same change")
    return findings


# ------------------------------------------------------------------- G-E7
def check_issue_and_runid(path: Path) -> tuple[str, list[str]]:
    """G-E7: `issue` is a real closed-done issue; `run_id` matches the format.

    Returns (status, findings) so the gate can SKIP when issue state is not
    available — it must never silently pass.
    """
    findings: list[str] = []
    records, _ = _read_records(path)

    for i, rec in enumerate(records, 1):
        rid = rec.get("run_id")
        if rid is not None and not RUN_ID_RE.match(str(rid)):
            findings.append(f"G-E7 record {i}: run_id {rid!r} does not match "
                            f"<YYYYMMDD-HHMM>-<4 alnum>")

    # A violation already established must surface as FAIL. Returning SKIP here
    # would mask a real finding behind "could not check" — the run_id half of
    # this gate needs no network, so its result is always reportable.
    if findings:
        return "FAIL", findings

    if not ISSUE_CACHE.exists():
        # Do not assume the cache lives under the repo: a monkeypatched or
        # relocated path made `.relative_to(REPO)` raise and the gate *crashed*
        # rather than reporting. A gate that throws is not a check either.
        try:
            shown = ISSUE_CACHE.relative_to(REPO)
        except ValueError:
            shown = ISSUE_CACHE
        return "SKIP", [f"issue-state cache absent ({shown}) — cannot verify "
                        f"`issue` names a closed-done issue"]
    try:
        cache = json.loads(ISSUE_CACHE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return "SKIP", [f"issue-state cache unreadable ({e.msg})"]

    checked = 0
    for i, rec in enumerate(records, 1):
        issue = rec.get("issue")
        if issue is None:
            continue
        entry = cache.get(str(issue))
        if entry is None:
            continue                      # not in the cache: cannot verify
        checked += 1
        state = str(entry.get("state", "")).upper()
        if state != "CLOSED":
            findings.append(f"G-E7 record {i}: issue #{issue} is {state}, "
                            f"not CLOSED — a record must cite a closed issue")
        elif not entry.get("done", False):
            findings.append(f"G-E7 record {i}: issue #{issue} is closed but not "
                            f"`status:done`")

    if checked == 0:
        return "SKIP", ["no record's issue is present in the cache — nothing "
                        "to verify"]
    return ("FAIL" if findings else "PASS"), findings


# ------------------------------------------------------------- registration
register(Gate(
    id="G-E1", name="findings schema", tier=0, check=check_schema,
    clean_fixture="findings/clean.jsonl",
    failing_fixture="findings/g_e1_unknown_key.jsonl",
    traces_to="findings.jsonl header; spec §3",
    description="Record parses; required keys present; no undeclared keys.",
))

register(Gate(
    id="G-E2", name="findings evidence keys non-empty", tier=0,
    check=check_evidence,
    clean_fixture="findings/clean.jsonl",
    failing_fixture="findings/g_e2_empty_correction.jsonl",
    traces_to="issue #4 DoD; findings.jsonl header",
    description="null_model, correction, n non-empty — the evidence bar.",
))

register(Gate(
    id="G-E6", name="findings append-only", tier=0, check=check_append_only,
    clean_fixture="findings/clean.jsonl",
    failing_fixture="findings/g_e6_shrunk.jsonl",
    traces_to="findings.jsonl header; spec §10 Q4",
    description="Record count is >= the committed high-water mark.",
))

def _unused_check(path: Path) -> list[str]:   # pragma: no cover - never called
    """Placeholder: G-E7 uses the check_status form, which returns an explicit
    status so it can SKIP when issue state is unavailable. The Gate dataclass
    requires a `check`, so this satisfies the signature and is never invoked."""
    return []


register(Gate(
    id="G-E7", name="findings issue and run-id validity", tier=0,
    check=_unused_check,
    check_status=check_issue_and_runid,
    clean_fixture="findings/clean.jsonl",
    failing_fixture="findings/g_e7_bad_runid.jsonl",
    traces_to="docs/MULTI_AGENT_WORKFLOW.md; spec §3",
    description="`issue` is a closed-done issue; `run_id` matches the format. "
                "SKIPs when issue state is unavailable.",
))
