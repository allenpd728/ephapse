#!/usr/bin/env python3
"""Atomic issue-state setter — the *preventer* to the gates' *detector*.

WHY THIS EXISTS. A gate detects a bad state after it exists. Three label-state
defects appeared in one session:

  1. Both `status:available` and `status:blocked-needs-input` set on one issue
     while filing #29-#34. G-M1 detects this.
  2. #32/#33 marked available while their blocker #31 was OPEN. G-M2 detects
     this.
  3. The #31 dependency edge was never created. **No gate can detect this** —
     an absent edge is indistinguishable from a task with no dependencies.

Defect 1 happened because `gh issue edit --add-label X --remove-label Y` is not
atomic in the sense that matters: it applies independent mutations, and a run
that *adds* a status without first removing the old one produces two statuses
and never errors. Nothing in the toolchain objects.

So the fix is not another gate. It is to make the illegal state
**unreachable**, by routing every status change through one function that
computes the target label set, validates it, and applies the whole set in one
`gh issue edit` — with the invariant checked *before* the mutation, not after.

WHY A SCRIPT AND NOT A GATE. `TEST_VALIDATION_SPEC.md` §8 makes gates
deterministic file inspection that must not touch the network, and says "a
non-deterministic gate is not a gate". This is not a gate: it is the mutation
path. It may call `gh`; the gate that reads its *result* may not.

USAGE

    python3 tooling/program/issue_state.py set-status 30 status:claimed
    python3 tooling/program/issue_state.py set-kind   30 kind:gate
    python3 tooling/program/issue_state.py block      32 31   # 32 blocked by 31
    python3 tooling/program/issue_state.py refresh            # rewrite the cache
    python3 tooling/program/issue_state.py audit              # run both gates

`set-status` fixes defect 1: it removes *every* status label and adds exactly
the requested one in one invocation, so the two-status state cannot be produced.
`block` mitigates defect 3: it is the only sanctioned way to add a dependency
edge, and it also refuses to leave a task `available` while its new blocker is
open — the defect-2 invariant, enforced at edge-creation time rather than only
detected later.

Exit codes: 0 on success; 1 on an invariant violation (nothing mutated);
2 on a usage or transport error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "allenpd728/ephapse"
ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "tests" / "fixture_issue_state.json"

VALID_STATUS = (
    "status:available", "status:claimed", "status:done",
    "status:blocked-needs-input",
)
VALID_KIND = (
    "kind:experiment", "kind:gate", "kind:repair", "kind:defect",
    "kind:gap", "kind:decision", "kind:protocol",
)
STATUS_RE = re.compile(r"^status:")
KIND_RE = re.compile(r"^kind:")


class InvariantViolation(RuntimeError):
    """Raised before any mutation when the requested state is illegal."""


def gh(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def fetch_issue(num: int) -> dict:
    return json.loads(gh("issue", "view", str(num), "--repo", REPO, "--json",
                         "number,title,state,labels"))


def current_labels(num: int) -> list[str]:
    return [l["name"] for l in fetch_issue(num).get("labels", [])]


# --------------------------------------------------------------- invariants
def validate_target(num: int, labels: list[str]) -> list[str]:
    """Return violations for a PROPOSED label set. Empty means legal.

    Checked before the mutation, which is the whole point: the previous path
    checked nothing and produced the illegal state directly.
    """
    problems: list[str] = []
    statuses = [l for l in labels if STATUS_RE.match(l)]
    kinds = [l for l in labels if KIND_RE.match(l)]
    if len(statuses) > 1:
        problems.append(f"#{num} would carry {len(statuses)} status labels: "
                        f"{', '.join(statuses)}")
    for l in statuses:
        if l not in VALID_STATUS:
            problems.append(f"#{num} status {l!r} is outside the vocabulary")
    for l in kinds:
        if l not in VALID_KIND:
            problems.append(f"#{num} kind {l!r} is outside the vocabulary")
    return problems


def assert_legal(num: int, labels: list[str]) -> None:
    problems = validate_target(num, labels)
    if problems:
        raise InvariantViolation("; ".join(problems) + " — no mutation applied")


# --------------------------------------------------------------- mutators
def _apply_label_delta(num: int, kind: str, target: str,
                       current: list[str]) -> tuple[list[str], list[str]]:
    """Compute (to_add, to_remove) so the result is exactly `target`.

    The bug this replaces: passing the same label as both `--add-label` and
    `--remove-label` makes `gh` apply the *removal*, leaving zero status labels.
    Found by running `set-status 30 status:claimed` on an issue that already had
    it — the tool silently stripped the status and reported success.

    So a label already present is neither added nor removed, and every sibling
    label of the same family is removed. Neither list ever overlaps.
    """
    pattern = STATUS_RE if kind == "status" else KIND_RE
    siblings = [l for l in current if pattern.match(l)]
    to_remove = [l for l in siblings if l != target]
    to_add = [] if target in current else [target]
    return to_add, to_remove


def set_status(num: int, status: str) -> None:
    """Set exactly one status label, atomically. Fix for defect 1."""
    if status not in VALID_STATUS:
        raise InvariantViolation(f"{status!r} is not a known status label; "
                                 f"expected one of {', '.join(VALID_STATUS)}")
    existing = current_labels(num)
    target_set = [l for l in existing if not STATUS_RE.match(l)] + [status]
    assert_legal(num, target_set)

    to_add, to_remove = _apply_label_delta(num, "status", status, existing)
    if not to_add and not to_remove:
        print(f"#{num}: status already {status}; nothing to change")
        return

    args = ["issue", "edit", str(num), "--repo", REPO]
    if to_add:
        args += ["--add-label", to_add[0]]
    for l in to_remove:
        args += ["--remove-label", l]
    gh(*args)
    print(f"#{num}: status -> {status} "
          f"(removed: {', '.join(to_remove) or 'none'})")


def set_kind(num: int, kind: str) -> None:
    """Set exactly one kind label, atomically. Mirrors set_status."""
    if kind not in VALID_KIND:
        raise InvariantViolation(f"{kind!r} is not a known kind label; "
                                 f"expected one of {', '.join(VALID_KIND)}")
    existing = current_labels(num)
    target_set = [l for l in existing if not KIND_RE.match(l)] + [kind]
    assert_legal(num, target_set)

    to_add, to_remove = _apply_label_delta(num, "kind", kind, existing)
    if not to_add and not to_remove:
        print(f"#{num}: kind already {kind}; nothing to change")
        return

    args = ["issue", "edit", str(num), "--repo", REPO]
    if to_add:
        args += ["--add-label", to_add[0]]
    for l in to_remove:
        args += ["--remove-label", l]
    gh(*args)
    print(f"#{num}: kind -> {kind} "
          f"(removed: {', '.join(to_remove) or 'none'})")


def block(task: int, blocker: int) -> None:
    """Create a `task blocked_by blocker` edge. Mitigation for defect 3.

    The sanctioned way to add a dependency, so the edge is not forgotten. It
    also enforces the defect-2 invariant at creation time rather than only
    detecting it later: if `task` is currently `available` and the new blocker
    is OPEN, `task` is moved to `blocked-needs-input`.
    """
    task_id = json.loads(gh("issue", "view", str(task), "--repo", REPO,
                            "--json", "id"))["id"]
    blocker_meta = json.loads(gh("issue", "view", str(blocker), "--repo", REPO,
                                 "--json", "id,state"))
    gh("api", "graphql", "-f",
       f'mutation {{ addBlockedBy(input: {{issueId: {task_id}, '
       f'blockingIssueId: {blocker_meta["id"]}}}) {{ issue {{ number }} }} }}')
    print(f"#{task}: blocked_by #{blocker} linked "
          f"(#{blocker} is {blocker_meta['state']})")

    if blocker_meta["state"] == "OPEN" and "status:available" in current_labels(task):
        print(f"  invariant: #{task} was status:available while #{blocker} is "
              f"OPEN — moving it to status:blocked-needs-input")
        set_status(task, "status:blocked-needs-input")


# --------------------------------------------------------------- cache
def fetch_blocked_by() -> dict[str, list[int]]:
    """Read every issue's `blocked_by` edges via GraphQL.

    `gh issue list --json` cannot return dependencies, which is why a naive
    refresh leaves `blocked_by` empty and G-M2 vacuously green. This is what
    makes the cache's dependency data real.
    """
    query = """
    { repository(owner: "%s", name: "%s") {
        issues(first: 100, states: [OPEN, CLOSED]) {
          nodes { number blockedBy(first: 50) { nodes { number } } } } } }
    """ % (REPO.split("/")[0], REPO.split("/")[1])
    raw = gh("api", "graphql", "-f", f"query={query}")
    nodes = json.loads(raw)["data"]["repository"]["issues"]["nodes"]
    return {str(n["number"]): sorted(b["number"] for b in n["blockedBy"]["nodes"])
            for n in nodes}


def refresh() -> None:
    """Rewrite the committed cache from live GitHub state.

    The cache is G-E7/G-M1/G-M2's input and tier 0 cannot fetch it, so it must
    be refreshed deliberately and reviewed as a diff. Both `labels` and
    `blocked_by` are read live — the first version of this helper preserved
    `blocked_by` from the previous cache, which left the dependency graph empty
    and made G-M2 report a vacuous PASS.
    """
    listing = json.loads(gh("issue", "list", "--repo", REPO, "--state", "all",
                            "--limit", "200", "--json",
                            "number,state,labels"))
    edges = fetch_blocked_by()
    old = {}
    if CACHE.exists():
        old = json.loads(CACHE.read_text(encoding="utf-8"))

    out = {k: v for k, v in old.items() if k.startswith("_")}
    out["_comment"] = (
        "Committed cache of GitHub issue state for G-E7 and G-M1/G-M2. Tier 0 "
        "must not touch the network, so the gates read this file. Regenerate "
        "with `python3 tooling/program/issue_state.py refresh` (reads labels AND "
        "blocked_by via GraphQL), then review the diff as part of the change.")
    out["_generated"] = "refresh"
    for issue in listing:
        num = str(issue["number"])
        labels = [l["name"] for l in issue["labels"]]
        out[num] = {
            "state": issue["state"],
            # G-E7's field: closed AND carries status:done.
            "done": bool(issue["state"] == "CLOSED" and "status:done" in labels),
            "labels": sorted(labels),
            "blocked_by": edges.get(num, []),
        }
    CACHE.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    n_edges = sum(len(v["blocked_by"]) for k, v in out.items()
                  if not k.startswith("_"))
    print(f"wrote {CACHE.relative_to(ROOT)} ({len(listing)} issue(s), "
          f"{n_edges} dependency edge(s))")


# --------------------------------------------------------------- audit
def audit() -> int:
    """Run G-M1 and G-M2 against the committed cache, without the runner.

    Convenience only — the authoritative invocation is
    `python3 tooling/gates/run_all.py --gate G-M1`. This exists so a session can
    check its own work before committing, which is the cheapest place to catch
    a violation.
    """
    sys.path.insert(0, str(ROOT / "tooling" / "gates"))
    import validate_program as V

    bad = 0
    for gate_id, fn in (("G-M1", V.check_label_cardinality),
                        ("G-M2", V.check_dependency_coherence)):
        status, findings = fn(CACHE)
        print(f"[{status}] {gate_id} ({len(findings)} finding(s))")
        for f in findings:
            print(f"        - {f}")
            bad += 1
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="atomic issue-state setter")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("set-status", help="set exactly one status label")
    p.add_argument("issue", type=int)
    p.add_argument("status")

    p = sub.add_parser("set-kind", help="set exactly one kind label")
    p.add_argument("issue", type=int)
    p.add_argument("kind")

    p = sub.add_parser("block", help="link TASK blocked_by BLOCKER")
    p.add_argument("task", type=int)
    p.add_argument("blocker", type=int)

    sub.add_parser("refresh", help="rewrite the committed issue-state cache")
    sub.add_parser("audit", help="run G-M1/G-M2 against the committed cache")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "set-status":
            set_status(args.issue, args.status)
        elif args.cmd == "set-kind":
            set_kind(args.issue, args.kind)
        elif args.cmd == "block":
            block(args.task, args.blocker)
        elif args.cmd == "refresh":
            refresh()
        elif args.cmd == "audit":
            return audit()
    except InvariantViolation as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
