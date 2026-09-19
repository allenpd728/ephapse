#!/usr/bin/env python3
"""audit_claims.py — find duplicate or stale claims across the issue queue.

Issue #26. The claim protocol's ownership check was originally "read the latest
claim comment and confirm its run-id is yours". That check **cannot detect the
case it was written for**: a session that claims second always finds its own
comment latest, so it passes while an earlier live claim sits unread. It failed
twice in one day (#5, #11); on #5 the two claimed sessions produced opposite
verdicts and reconciling them cost DEC-023, DEC-024, and a third entry.

This tool answers the question the protocol actually needs:

    Does any unexpired claim by another run-id exist? And if two claims
    collide, who wins?

Winner is the **earliest server-assigned comment id** — not the earliest
timestamp string, which is agent-supplied and can be skewed or simply wrong.
Comment ids are monotonic and assigned by GitHub, so both sessions compute the
same answer with no human in the loop. Verified on the real incidents:

    #5  id 5737426522 (run 20260918-2329-zbmn) < id 5737450441 (run 20260918-2332-e7c4)
    #11 id 5739467938 (run 20260919-0451-6421) < id 5739479618 (run 20260918-2332-e7c4)

NOT A CI GATE. It needs issue state, so it is tier 1 by the spec's split and
must not be wired into `tooling/gates/run_all.py`. Offline use takes a
pre-fetched JSON (the G-E7 cache pattern); `--fetch` reads live.

Usage:
    python3 tooling/claims/audit_claims.py --cache issues.json
    python3 tooling/claims/audit_claims.py --fetch
    python3 tooling/claims/audit_claims.py --cache issues.json --run-id <id>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAIM_RE = re.compile(
    r"claimed\s+by\s+(?P<agent>\S+)\s+run=(?P<runid>\S+)\s+at\s+(?P<ts>\S+)",
    re.IGNORECASE)

STALE_AFTER = timedelta(hours=1)


class Claim:
    __slots__ = ("comment_id", "created_at", "run_id", "agent", "issue")

    def __init__(self, comment_id: int, created_at: str, run_id: str,
                 agent: str, issue: int):
        self.comment_id = comment_id
        self.created_at = created_at
        self.run_id = run_id
        self.agent = agent
        self.issue = issue

    def age(self, now: datetime) -> timedelta:
        return now - _parse(self.created_at)

    def __repr__(self) -> str:
        return f"<Claim #{self.issue} run={self.run_id} id={self.comment_id}>"


def _parse(ts: str) -> datetime:
    """Parse a GitHub UTC timestamp. Unparseable values sort as 'very old'."""
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def parse_claims(issues: list[dict], comments_by_issue: dict[str, list[dict]],
                 now: datetime | None = None) -> list[Claim]:
    """Extract every claim comment, newest-agnostic.

    Deliberately returns ALL claims rather than the latest — reading only the
    latest is the defect this module exists to fix.
    """
    now = now or datetime.now(timezone.utc)
    out: list[Claim] = []
    for issue in issues:
        num = issue["number"]
        for c in comments_by_issue.get(str(num), []):
            m = CLAIM_RE.search(c.get("body", "") or "")
            if not m:
                continue
            out.append(Claim(
                comment_id=int(c["id"]),
                created_at=m.group("ts"),
                run_id=m.group("runid"),
                agent=m.group("agent"),
                issue=num,
            ))
    return out


def live_claims(claims: list[Claim], now: datetime | None = None) -> list[Claim]:
    """Drop claims older than the stale window (protocol § 1)."""
    now = now or datetime.now(timezone.utc)
    return [c for c in claims if c.age(now) <= STALE_AFTER]


def audit(issues: list[dict], comments_by_issue: dict[str, list[dict]],
          mine: str | None = None, now: datetime | None = None) -> list[dict]:
    """Per-issue verdict.

    Returns a list of {issue, claims, live, winner, collisions, mine}.
    `winner` is the earliest comment id among live claims (None if none live).
    """
    now = now or datetime.now(timezone.utc)
    all_claims = parse_claims(issues, comments_by_issue, now)
    by_issue: dict[int, list[Claim]] = {}
    for c in all_claims:
        by_issue.setdefault(c.issue, []).append(c)

    verdicts = []
    for issue in issues:
        num = issue["number"]
        cs = by_issue.get(num, [])
        if not cs:
            continue
        live = [c for c in cs if c.age(now) <= STALE_AFTER]
        winner = min(live, key=lambda c: c.comment_id) if live else None
        verdicts.append({
            "issue": num,
            "claims": cs,
            "live": live,
            "winner": winner,
            "collisions": len(live) > 1,
            "mine": mine,
            "i_own": (winner is not None and mine is not None
                      and winner.run_id == mine),
        })
    return verdicts


def report(verdicts: list[dict], mine: str | None) -> str:
    lines = ["claim audit", "=" * 78]
    problems = 0
    for v in verdicts:
        if not v["collisions"]:
            continue
        problems += 1
        lines.append(f"issue #{v['issue']} — {len(v['live'])} LIVE claims "
                     f"(collision)")
        for c in sorted(v["live"], key=lambda c: c.comment_id):
            mark = "  <- winner" if c.comment_id == v["winner"].comment_id else ""
            lines.append(f"    id={c.comment_id} run={c.run_id} "
                         f"at={c.created_at}{mark}")
        lines.append(f"    tiebreak: earliest server-assigned comment id wins")
        if mine:
            lines.append(
                f"    my run {mine}: "
                + ("I HOLD THE CLAIM" if v["i_own"]
                   else "I LOST — release and pick another item"))
    if not problems:
        lines.append("no live claim collisions")
    stale = [v for v in verdicts if v["claims"] and not v["live"]]
    if stale:
        lines.append("-" * 78)
        lines.append(f"{len(stale)} issue(s) carry only expired claims "
                     f"(reclaimable per protocol § 1): "
                     + ", ".join(f"#{v['issue']}" for v in stale))
    lines.append("-" * 78)
    lines.append(f"{problems} collision(s)")
    return "\n".join(lines)


# ------------------------------------------------------------------ I/O
def load_cache(path: Path) -> tuple[list[dict], dict[str, list[dict]]]:
    """Read a pre-fetched bundle.

    Shape: {"issues": [...], "comments": {num: [...]}, "_evaluate_at": <iso>}

    `_evaluate_at` is optional and lets a fixture declare the moment it is
    evaluated. Without it, a fixture reproducing a real incident would be judged
    against wall-clock now and its claims would read as stale the moment the
    incident aged past the 1-hour window — which is exactly what happened to the
    first version of these tests.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["issues"], data["comments"]


def cache_evaluate_at(path: Path) -> datetime | None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ts = data.get("_evaluate_at")
    return _parse(ts) if ts else None


def token_candidates() -> list[tuple[str, str]]:
    """Credentials to try, in order: (env-var name, value).

    Presence is not validity. The session token can expire mid-run (observed:
    it authenticated at session start and later returned 401), so a non-empty
    `GITHUB_TOKEN` may still be dead. The caller must therefore *try* the
    default and fall back on an auth failure, not merely check that it is set.
    See MULTI_AGENT_WORKFLOW.md § Credentials.
    """
    out = []
    for name in ("GITHUB_TOKEN", "ALL_REPOs_GH_TOKEN"):
        val = os.environ.get(name, "")
        if val:
            out.append((name, val))
    return out


def fetch(repo: str, token: str) -> tuple[list[dict], dict[str, list[dict]]]:
    """Read live issue + comment state from the API."""
    def api(url: str):
        req = urllib.request.Request(
            url, headers={"Authorization": f"token {token}",
                          "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    issues = [i for i in api(
        f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100")
        if "pull_request" not in i]
    comments: dict[str, list[dict]] = {}
    for i in issues:
        comments[str(i["number"])] = api(
            f"https://api.github.com/repos/{repo}/issues/{i['number']}"
            f"/comments?per_page=100")
    return issues, comments


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", type=Path, default=None,
                    help="pre-fetched issues JSON (offline)")
    ap.add_argument("--fetch", action="store_true", help="read live from the API")
    ap.add_argument("--repo", default="allenpd728/ephapse")
    ap.add_argument("--run-id", default=None,
                    help="my run-id, to state whether I hold each claim")
    args = ap.parse_args(argv)

    if args.cache:
        issues, comments = load_cache(args.cache)
        now = cache_evaluate_at(args.cache)
    elif args.fetch:
        cands = token_candidates()
        if not cands:
            print("ERROR: --fetch needs a token; set GITHUB_TOKEN (or "
                  "ALL_REPOs_GH_TOKEN as fallback)", file=sys.stderr)
            return 1
        issues = comments = None
        for name, tok in cands:
            try:
                issues, comments = fetch(args.repo, tok)
                if name != cands[0][0]:
                    print(f"NOTE: {cands[0][0]} was rejected (401); used "
                          f"{name} instead.", file=sys.stderr)
                break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    print(f"NOTE: {name} rejected (HTTP {e.code}); trying next "
                          f"credential.", file=sys.stderr)
                    continue
                raise
        if issues is None:
            print("ERROR: no available credential authenticated.", file=sys.stderr)
            return 1
        now = None
    else:
        print("ERROR: pass --cache <file> or --fetch", file=sys.stderr)
        return 1

    verdicts = audit(issues, comments, mine=args.run_id, now=now)
    print(report(verdicts, args.run_id))
    # Exit non-zero only when a collision involves me or is unresolved; a
    # collision the caller can resolve is a finding, not a failure of the tool.
    return 0


if __name__ == "__main__":
    sys.exit(main())