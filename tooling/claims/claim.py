#!/usr/bin/env python3
"""claim.py — git-ref compare-and-swap for the claim protocol (issue #27).

GitHub labels are last-write-wins: two sessions can both set `status:claimed`
and neither write is rejected. With one shared account there is no conditional
write on labels, assignees, or comments, so the label alone cannot prevent a
race — #26's audit can only detect one after the fact.

`git push` **is** a compare-and-swap on the remote ref: a non-fast-forward
update is rejected. That is what this tool uses.

    claims/<issue>.claim     contents: <run-id> <UTC timestamp>

`claim` writes the file, commits, and pushes. Whichever push lands first wins;
the loser is rejected in seconds, having done no work. One file per issue, so
two *different* claims never touch the same path and cannot conflict.

Exit codes are part of the contract:

    0  won the claim (or the release/status succeeded)
    2  LOST the race — another run-id holds a live claim. Not an error:
       back off and pick different work.
    1  a real error (bad args, git failure, dirty tree)

`2` is deliberately distinct so a caller can branch on "lost" without parsing
output. See docs/MULTI_AGENT_WORKFLOW.md § 4.

Usage:
    python3 tooling/claims/claim.py claim 27 20260919-1004-db83
    python3 tooling/claims/claim.py status 27
    python3 tooling/claims/claim.py release 27 20260919-1004-db83
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAIMS_DIR = "claims"
STALE_AFTER = timedelta(hours=1)
RUN_ID_RE = re.compile(r"^\d{8}-\d{4}-[0-9a-z]{4}$")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_LOST = 2


class ClaimLost(Exception):
    """Another run-id holds a live claim. Expected, not an error."""


class GitError(Exception):
    pass


def run(args: list[str], cwd: Path | None = None, check: bool = True,
        env_extra: dict[str, str] | None = None):
    """Run git with prompts disabled.

    `GIT_TERMINAL_PROMPT=0` matters more than it looks. If the remote URL holds
    a stale credential, git blocks on an interactive password prompt — which, in
    an agent session, means the claim hangs until the harness times out instead
    of reporting a lost race or an error. Observed live while dogfooding this
    tool. Failing fast is the only acceptable behaviour for a lock.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_ASKPASS", "true")      # never launch a prompt helper
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, env=env)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): "
                       f"{proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def parse_claim(text: str) -> tuple[str, datetime] | None:
    """Parse `<run-id> <iso timestamp>`. Returns None if unparseable."""
    parts = (text or "").split()
    if not parts:
        return None
    run_id = parts[0]
    ts = parts[1] if len(parts) > 1 else ""
    try:
        when = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None
    return run_id, when


def is_live(text: str, now: datetime | None = None) -> bool:
    """A claim is live unless it is older than the stale window (§ 1)."""
    parsed = parse_claim(text)
    if parsed is None:
        return False          # unparseable ⇒ cannot block anyone
    _, when = parsed
    now = now or datetime.now(timezone.utc)
    return (now - when) <= STALE_AFTER


def claim_path(issue: int) -> str:
    return f"{CLAIMS_DIR}/{issue}.claim"


def read_remote_claim(repo: Path, branch: str, issue: int) -> str | None:
    """Contents of the claim file on the remote branch, or None."""
    proc = run(["show", f"origin/{branch}:{claim_path(issue)}"],
               cwd=repo, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def dirty(repo: Path) -> bool:
    return bool(run(["status", "--porcelain"], cwd=repo, check=False).stdout.strip())


def cmd_claim(args) -> int:
    repo = Path(args.repo).resolve()
    branch = args.branch
    issue = args.issue
    run_id = args.run_id
    rel = claim_path(issue)

    if not RUN_ID_RE.match(run_id):
        print(f"ERROR: {run_id!r} is not a run-id "
              f"(expected <YYYYMMDD-HHMM>-<4 alnum>)", file=sys.stderr)
        return EXIT_ERROR
    if dirty(repo):
        print("ERROR: working tree is dirty; the claim must be its own commit",
              file=sys.stderr)
        return EXIT_ERROR

    run(["fetch", "origin", branch], cwd=repo)

    for attempt in range(1, args.retries + 1):
        base = run(["rev-parse", "HEAD"], cwd=repo).stdout.strip()

        # --- read the authoritative state from the remote ref -------------
        existing = read_remote_claim(repo, branch, issue)
        if existing and is_live(existing):
            owner = parse_claim(existing)[0]
            if owner != run_id:
                print(f"LOST: #{issue} is claimed by {owner} (live). "
                      f"Back off and pick other work.")
                return EXIT_LOST
            print(f"#{issue} already claimed by me ({run_id}) — nothing to do.")
            return EXIT_OK

        # --- write, commit, push: the push is the compare-and-swap --------
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        path.write_text(f"{run_id} {now}\n", encoding="utf-8")

        run(["add", rel], cwd=repo)
        run(["-c", "user.name=openhands",
             "-c", "user.email=openhands@all-hands.dev",
             "commit", "-q", "-m",
             f"claim #{issue} by run {run_id}"], cwd=repo)

        push = run(["push", "origin", f"HEAD:{branch}"], cwd=repo, check=False)
        if push.returncode == 0:
            print(f"WON: #{issue} claimed by {run_id} (pushed {branch}).")
            return EXIT_OK

        # --- push rejected: someone else moved the ref first --------------
        print(f"  push rejected (attempt {attempt}/{args.retries}) — "
              f"ref moved; re-reading the remote claim")
        run(["fetch", "origin", branch], cwd=repo)
        rival = read_remote_claim(repo, branch, issue)
        if rival and is_live(rival) and parse_claim(rival)[0] != run_id:
            run(["reset", "--hard", base], cwd=repo)
            print(f"LOST: #{issue} is claimed by {parse_claim(rival)[0]} (live). "
                  f"Back off and pick other work.")
            return EXIT_LOST

        # The ref moved for an unrelated reason (a sibling landed other work).
        # Rebase our claim commit and retry the CAS.
        rebase = run(["pull", "--rebase", "origin", branch], cwd=repo, check=False)
        if rebase.returncode != 0:
            run(["rebase", "--abort"], cwd=repo, check=False)
            run(["reset", "--hard", base], cwd=repo)
            print("ERROR: rebase conflicted; could not complete the claim",
                  file=sys.stderr)
            return EXIT_ERROR

    run(["reset", "--hard", base], cwd=repo)
    print(f"ERROR: gave up claiming #{issue} after {args.retries} attempts",
          file=sys.stderr)
    return EXIT_ERROR


def cmd_status(args) -> int:
    repo = Path(args.repo).resolve()
    fetch = run(["fetch", "origin", args.branch], cwd=repo, check=False)
    if fetch.returncode != 0:
        # Fail CLOSED. Reporting "unclaimed" when the remote could not be read
        # would tell a session the item is free when we simply do not know —
        # and a claim taken on that basis is exactly the race this tool exists
        # to prevent. Observed live with a stale credential in the remote URL.
        print(f"ERROR: cannot read origin/{args.branch} "
              f"({fetch.stderr.strip() or 'fetch failed'}) — "
              f"claim state is UNKNOWN, not unclaimed", file=sys.stderr)
        return EXIT_ERROR

    text = read_remote_claim(repo, args.branch, args.issue)
    if not text:
        print(f"#{args.issue}: unclaimed")
        return EXIT_OK
    parsed = parse_claim(text)
    if parsed is None:
        print(f"#{args.issue}: unparseable claim record {text!r} — "
              f"treat as UNKNOWN, not unclaimed")
        return EXIT_ERROR
    owner, when = parsed
    now = datetime.now(timezone.utc)
    age = now - when
    state = "LIVE" if age <= STALE_AFTER else "STALE (reclaimable per § 1)"
    mine = " (mine)" if args.run_id and owner == args.run_id else ""
    print(f"#{args.issue}: {owner}{mine} — {state}, age "
          f"{int(age.total_seconds() // 60)} min")
    return EXIT_OK


def cmd_release(args) -> int:
    repo = Path(args.repo).resolve()
    branch, issue, run_id = args.branch, args.issue, args.run_id
    if dirty(repo):
        print("ERROR: working tree is dirty; the release must be its own commit",
              file=sys.stderr)
        return EXIT_ERROR
    run(["fetch", "origin", branch], cwd=repo)
    text = read_remote_claim(repo, branch, issue)
    if not text:
        print(f"#{issue}: unclaimed; nothing to release")
        return EXIT_OK
    owner = parse_claim(text)[0] if parse_claim(text) else None
    if owner != run_id:
        print(f"ERROR: #{issue} is held by {owner}, not {run_id}; refusing to "
              f"release someone else's claim", file=sys.stderr)
        return EXIT_ERROR

    run(["pull", "--rebase", "origin", branch], cwd=repo)
    path = repo / claim_path(issue)
    if not path.exists():
        print(f"#{issue}: claim file absent after pull; nothing to release")
        return EXIT_OK
    path.unlink()
    run(["add", "-A", claim_path(issue)], cwd=repo)
    run(["-c", "user.name=openhands",
         "-c", "user.email=openhands@all-hands.dev",
         "commit", "-q", "-m", f"release #{issue} by run {run_id}"], cwd=repo)
    push = run(["push", "origin", f"HEAD:{branch}"], cwd=repo, check=False)
    if push.returncode != 0:
        print("ERROR: release push rejected; retry after a pull", file=sys.stderr)
        return EXIT_ERROR
    print(f"RELEASED: #{issue} (was held by {run_id})")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="git-ref claim CAS (issue #27)")
    ap.add_argument("--repo", default=".", help="repository working copy")
    ap.add_argument("--branch", default="dev")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("claim", help="claim an issue (CAS)")
    c.add_argument("issue", type=int)
    c.add_argument("run_id")
    c.add_argument("--retries", type=int, default=5)
    c.set_defaults(func=cmd_claim)

    s = sub.add_parser("status", help="report who holds an issue")
    s.add_argument("issue", type=int)
    s.add_argument("--run-id", default=None)
    s.set_defaults(func=cmd_status)

    r = sub.add_parser("release", help="release your own claim")
    r.add_argument("issue", type=int)
    r.add_argument("run_id")
    r.set_defaults(func=cmd_release)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except GitError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())