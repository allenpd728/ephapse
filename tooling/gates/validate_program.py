#!/usr/bin/env python3
"""G-M1, G-M2 — program label-state gates (issue #30).

Tier 0. Reads the committed issue-state cache only; never the network.

| ID   | Check |
|------|-------|
| G-M1 | Exactly one `status:` and exactly one `kind:` label per OPEN issue |
| G-M2 | Dependency coherence — an `status:available` issue has no OPEN blocker |

WHY TWO GATES AND NOT ONE. G-M1 alone would not have caught the failure that
motivated this work. Three label-state defects appeared in a single session:

  1. **Invalid mutation.** Filing #29-#34 set *both* `status:available` and
     `status:blocked-needs-input` on the same issue. G-M1 catches this.
  2. **Dependency violation.** #32 and #33 were marked `status:available` while
     their declared blocker #31 was OPEN. Their label *cardinality* was correct —
     one status each — so G-M1 is silent. Only a check that reads the dependency
     graph sees it. That is G-M2.
  3. **Omission.** The #31 dependency link was never created at all, so #32/#33
     had no `blocked_by` edge and nothing to violate. **No gate catches this**,
     because absence of an edge is indistinguishable from a task with no
     dependencies. It is a filing-protocol defect, addressed by the setter in
     `tooling/program/issue_state.py` and by the spec's task map being the
     authority for what edges should exist.

So a gate is *detection*, and detection is partial. The same session produced a
defect no gate can see, which is why this issue also lands a *preventer*.

THE CACHE. `tests/fixture_issue_state.json`, extended with two fields per issue:

    {"28": {"state": "CLOSED", "done": true,
            "labels": ["status:done", "kind:protocol"],
            "blocked_by": []}}

Entries whose key starts with `_` are metadata and ignored. The `state`/`done`
fields are G-E7's and must not change; `labels` and `blocked_by` are additive.

Both gates return SKIP — never pass — when the cache is absent or lacks issues,
following the G-E7 precedent exactly.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from run_all import Gate, register           # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
ISSUE_CACHE = REPO / "tests" / "fixture_issue_state.json"

STATUS_LABEL_RE = re.compile(r"^status:")
KIND_LABEL_RE = re.compile(r"^kind:")

# The registered vocabularies. A value outside these is its own defect class:
# a typo'd label is invisible to a cardinality check and silently divides the
# queue. Kept here rather than parsed from the spec, for the same reason
# target_model.txt exists — prose is brittle to derive from.
VALID_STATUS = (
    "status:available", "status:claimed", "status:done",
    "status:blocked-needs-input",
)
VALID_KIND = (
    "kind:experiment", "kind:gate", "kind:repair", "kind:defect",
    "kind:gap", "kind:decision", "kind:protocol",
)


def _load_cache(path: Path) -> tuple[dict | None, list[str]]:
    """Return (issues, errors). `issues` excludes metadata keys."""
    if not path.exists():
        return None, [f"issue-state cache absent ({path.name})"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, [f"issue-state cache unreadable ({e.msg})"]
    if not isinstance(raw, dict):
        return None, ["issue-state cache is not a JSON object"]
    issues = {k: v for k, v in raw.items()
              if not k.startswith("_") and isinstance(v, dict)}
    return issues, []


def _open_issues(issues: dict) -> dict:
    return {k: v for k, v in issues.items()
            if str(v.get("state", "")).upper() == "OPEN"}


def _labels(entry: dict) -> list[str]:
    labels = entry.get("labels")
    return list(labels) if isinstance(labels, list) else []


# ------------------------------------------------------------------- G-M1
def check_label_cardinality(path: Path) -> tuple[str, list[str]]:
    """G-M1: exactly one status: and one kind: per OPEN issue."""
    issues, errors = _load_cache(path)
    if issues is None:
        return "SKIP", errors

    open_issues = _open_issues(issues)
    if not open_issues:
        return "SKIP", ["no OPEN issues in the cache — nothing to check"]

    findings: list[str] = []
    for num, entry in sorted(open_issues.items(), key=lambda kv: int(kv[0])
                             if kv[0].isdigit() else 0):
        labels = _labels(entry)
        if not labels:
            # A label-less entry may simply mean the cache predates labels.
            # Skipping the whole check would hide real violations, so it is
            # reported as a finding: an unlabeled cached issue cannot be
            # verified and must be refreshed.
            findings.append(f"G-M1 #{num}: cache entry carries no `labels` "
                            f"list — refresh the cache (tooling/program/"
                            f"issue_state.py)")
            continue
        statuses = [l for l in labels if STATUS_LABEL_RE.match(l)]
        kinds = [l for l in labels if KIND_LABEL_RE.match(l)]
        if len(statuses) != 1:
            findings.append(f"G-M1 #{num}: {len(statuses)} status label(s) "
                            f"({', '.join(statuses) or 'none'}) — exactly one "
                            f"required")
        if len(kinds) != 1:
            findings.append(f"G-M1 #{num}: {len(kinds)} kind label(s) "
                            f"({', '.join(kinds) or 'none'}) — exactly one "
                            f"required")
        # Vocabulary, not just cardinality. A typo'd label reads as one label
        # and silently divides the queue — the failure mode a count cannot see.
        for label in statuses:
            if label not in VALID_STATUS:
                findings.append(f"G-M1 #{num}: {label!r} is not a known status "
                                f"label — expected one of "
                                f"{', '.join(VALID_STATUS)}")
        for label in kinds:
            if label not in VALID_KIND:
                findings.append(f"G-M1 #{num}: {label!r} is not a known kind "
                                f"label — expected one of "
                                f"{', '.join(VALID_KIND)}")
    if not findings:
        return "PASS", []
    return "FAIL", findings


# ------------------------------------------------------------------- G-M2
def check_dependency_coherence(path: Path) -> tuple[str, list[str]]:
    """G-M2: an `available` issue must have no OPEN blocker.

    This is the check G-M1 cannot do. A forbidden-state combination, not a
    cardinality error: #32 with `status:available` and an OPEN `blocked_by`
    entry is invalid even though it carries exactly one status label.

    **Vacancy guard.** The first version of this gate reported PASS while
    checking nothing, because `blocked_by` was empty for every cached issue —
    `gh issue list` cannot read dependencies, so a refresh leaves the field
    empty and the gate finds no violations in a graph it never saw. A green
    result that cannot come out red is not a result (DEC-019, DEC-020). So when
    no cached issue carries any `blocked_by` entry, the gate returns SKIP with
    the reason rather than PASS: it cannot distinguish "no violations" from
    "no dependency data".
    """
    issues, errors = _load_cache(path)
    if issues is None:
        return "SKIP", errors
    if not issues:
        return "SKIP", ["issue-state cache is empty — nothing to check"]

    # Vacancy guard: without any recorded edges there is nothing to contradict.
    if not any((v.get("blocked_by") or []) for v in issues.values()):
        return "SKIP", [
            "no `blocked_by` edges recorded in the cache — cannot check "
            "dependency coherence. `gh issue list` cannot read dependencies; "
            "populate them with `tooling/program/issue_state.py block` or a "
            "GraphQL refresh."]

    findings: list[str] = []
    for num, entry in sorted(issues.items(), key=lambda kv: int(kv[0])
                             if kv[0].isdigit() else 0):
        labels = _labels(entry)
        blocked_by = entry.get("blocked_by") or []
        if not isinstance(blocked_by, list):
            findings.append(f"G-M2 #{num}: `blocked_by` is not a list")
            continue
        if not blocked_by:
            continue
        open_blockers = [
            b for b in blocked_by
            if str(issues.get(str(b), {}).get("state", "")).upper() != "CLOSED"
        ]
        if open_blockers and "status:available" in labels:
            findings.append(
                f"G-M2 #{num}: status:available but blocker(s) "
                f"{', '.join('#' + str(b) for b in open_blockers)} not CLOSED "
                f"— a blocked task must not be claimable")
    if not findings:
        return "PASS", []
    return "FAIL", findings


register(Gate(
    id="G-M1", name="label cardinality", tier=0,
    check=lambda p: [],                      # check_status form is authoritative
    check_status=check_label_cardinality,
    clean_fixture="program_clean.json",
    failing_fixture="program_r1_two_status.json",
    traces_to="PROGRAM_MANAGEMENT_SPEC.md section 7",
    description="Exactly one status: and exactly one kind: per OPEN issue.",
))

register(Gate(
    id="G-M2", name="dependency coherence", tier=0,
    check=lambda p: [],
    check_status=check_dependency_coherence,
    clean_fixture="program_clean.json",
    failing_fixture="program_r2_available_blocked.json",
    traces_to="PROGRAM_MANAGEMENT_SPEC.md section 4; MULTI_AGENT_WORKFLOW.md section 1a",
    description="An available issue has no open blocker.",
))
