#!/usr/bin/env python3
"""hub_sweep.py — append one status snapshot to status_log.jsonl for HuB.

HuB is a read-only dashboard that fetches `status_log.jsonl` from this repo's
branch and renders it (see HuB/PM_STATUS_FRAMEWORK.md for the record schema).
This script is the *writer* side: it derives a snapshot from this repo's
GitHub issues at run time and appends exactly one JSONL line. Nothing is
hardcoded — every number is computed from the tracker, so the file cannot
drift from reality the way a hand-maintained table does.

Design rules (do not violate):

  * Append only. Existing lines are never rewritten or removed; `git diff`
    shows one added line per sweep.
  * Honest numbers only. If a metric cannot be computed from real data, it is
    omitted rather than defaulted — an absent field is a true statement, a
    zero is often a false one. The one exception is a count of things that
    were actually enumerated (e.g. `wip: 0` when no issue is claimed), which
    is a measurement, not a guess.
  * No duplicate snapshots. If the computed snapshot is identical to the last
    line, nothing is appended (`--force` overrides). A daily cron on an idle
    repo should not grow the log.

Flow metrics follow this repo's own multi-agent protocol (see
docs/MULTI_AGENT_WORKFLOW.md §"Sweep stale claims"): a claim is stale when its
newest claim comment is older than `CLAIM_STALE_AFTER` with no activity since.

Every published field's definition is owned by
`portfolio-ops/METRIC_CONTRACT.md` (private). It wins over this file: if the
two disagree, this script is the bug. Do not change a field's meaning here
without a contract version bump and a decision-log entry.

Usage:
    python3 tooling/hub_sweep.py --repo philipdallen/Maith
    python3 tooling/hub_sweep.py --repo philipdallen/Maith --dry-run
    python3 tooling/hub_sweep.py --repo philipdallen/Maith --file /tmp/out.jsonl

Exit codes: 0 wrote (or dry-run printed) a snapshot; 1 a real error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
LOG_NAME = "status_log.jsonl"
TRL_PATH = "status/trl.json"
CLAIM_STALE_AFTER = dt.timedelta(hours=1)
CYCLE_LOOKBACK = dt.timedelta(days=30)
TRL_MAX = 9

CLAIM_RE = re.compile(
    r"claimed by\s+(?P<who>\S+)\s+run=(?P<run>\d{8}-\d{4}-[0-9a-z]{4})\s+at\s+(?P<when>\S+)"
)
STATUS_PREFIX = "status:"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_utc(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# --------------------------------------------------------------------------
# GitHub access
# --------------------------------------------------------------------------

def _request(url: str, token: str | None) -> tuple[object, dict]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "hub-sweep",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode()), dict(resp.headers)


def fetch_pages(path: str, token: str | None, params: str = "") -> list[dict]:
    """Follow GitHub's Link-header pagination and return every item."""
    items: list[dict] = []
    url = f"{API}{path}?per_page=100{params}"
    while url:
        data, headers = _request(url, token)
        if not isinstance(data, list):
            raise RuntimeError(f"expected a list from {url}, got {type(data).__name__}")
        items.extend(data)
        url = _next_link(headers.get("Link", ""))
    return items


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        if 'rel="next"' in segments[1]:
            return segments[0].strip().strip("<>")
    return None


def fetch_issues(repo: str, token: str | None, state: str, extra: str = "") -> list[dict]:
    raw = fetch_pages(f"/repos/{repo}/issues", token, f"&state={state}{extra}")
    return [i for i in raw if "pull_request" not in i]  # issues only, no PRs


def fetch_comments(repo: str, number: int, token: str | None) -> list[dict]:
    return fetch_pages(f"/repos/{repo}/issues/{number}/comments", token)


# --------------------------------------------------------------------------
# Snapshot computation (pure; unit-testable without network)
# --------------------------------------------------------------------------

def label_names(issue: dict) -> list[str]:
    return [l["name"] for l in issue.get("labels", [])]


def count_stale(claimants: list[dict], now: dt.datetime) -> int:
    """Claims stale per this repo's protocol: claim comment older than
    CLAIM_STALE_AFTER with no activity since. A claim younger than the
    threshold is live regardless of `updated_at`."""
    stale = 0
    for claim in claimants:
        claimed_at = claim.get("claimed_at")
        if claimed_at is None:
            continue
        if now - claimed_at <= CLAIM_STALE_AFTER:
            continue
        updated = claim.get("updated_at")
        if updated is None or updated <= claimed_at:
            stale += 1
    return stale


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 2)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 2)


def build_flow(open_issues: list[dict], closed_issues: list[dict],
               claimants: list[dict], now: dt.datetime) -> dict:
    open_total = len(open_issues)
    labels = [label_names(i) for i in open_issues]

    wip = sum(1 for ls in labels if "status:claimed" in ls)
    available = sum(1 for ls in labels if "status:available" in ls)
    review = sum(
        1 for ls in labels
        if "needs-review" in ls or any(l.startswith("review:") for l in ls)
    )

    # Not every `status:blocked-needs-input` issue is program blockage. Parked
    # (`on-hold`) and auditor-generated (`auditor:*`) issues are the audit queue,
    # which is already tracked elsewhere. Counting them lets a relabelling move
    # the published blocked_ratio. See portfolio-ops/METRIC_CONTRACT.md v1.
    def is_janitorial(ls: list[str]) -> bool:
        return "on-hold" in ls or any(l.startswith("auditor:") for l in ls)

    status_blocked = [ls for ls in labels if "status:blocked-needs-input" in ls]
    blocked = sum(1 for ls in status_blocked if not is_janitorial(ls))
    janitorial = len(status_blocked) - blocked

    flow: dict = {
        "open_total": open_total,
        "wip": wip,
        "blocked": blocked,
        "janitorial": janitorial,
        "available": available,
        "needs_review": review,
        "blocked_ratio": round(blocked / open_total, 4) if open_total else 0.0,
        "stale_reversions_since_last": count_stale(claimants, now),
    }

    cutoff = now - CYCLE_LOOKBACK
    durations = []
    for issue in closed_issues:
        closed_at = parse_utc(issue.get("closed_at") or "")
        created_at = parse_utc(issue.get("created_at") or "")
        if not closed_at or not created_at or closed_at < cutoff:
            continue
        durations.append((closed_at - created_at).total_seconds() / 3600)
    cycle = median(durations)
    if cycle is not None:
        flow["cycle_time_median_hours"] = cycle
        flow["closed_last_30d"] = len(durations)
    return flow


def build_trl(repo_root: Path) -> dict | None:
    """Optional, explicit TRL source. TRL is a human judgement about a
    project's own components and cannot be derived from issue counts, so it
    lives in a committed file (`status/trl.json`) rather than being guessed.
    Absent file -> field omitted -> HuB shows its "no TRL entries" message."""
    path = repo_root / TRL_PATH
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: ignoring {TRL_PATH}: {exc}", file=sys.stderr)
        return None
    components = data.get("components", data) if isinstance(data, dict) else {}
    trl = {}
    for name, value in components.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if 0 <= value <= TRL_MAX:
            trl[str(name)] = int(value)
    return trl or None


def build_notes(open_issues: list[dict], flow: dict, claimants: list[dict],
                now: dt.datetime) -> str:
    parts = [
        f"sweep: {flow['open_total']} open, {flow['wip']} claimed, "
        f"{flow['blocked']} blocked, {flow['available']} available"
    ]
    if flow["janitorial"]:
        parts.append(f"{flow['janitorial']} janitorial/on-hold")
    if flow["stale_reversions_since_last"]:
        parts.append(f"{flow['stale_reversions_since_last']} stale claim(s) reclaimed")
    if "cycle_time_median_hours" in flow:
        parts.append(f"median cycle {flow['cycle_time_median_hours']}h")
    if flow["needs_review"]:
        parts.append(f"{flow['needs_review']} awaiting review")
    if claimants:
        holders = sorted({c["run"] for c in claimants if c.get("run")})
        parts.append("claim run-ids: " + ", ".join(holders) if holders else "")
    return " | ".join(p for p in parts if p)


def build_snapshot(open_issues: list[dict], closed_issues: list[dict],
                   claimants: list[dict], repo_root: Path,
                   now: dt.datetime | None = None) -> dict:
    now = now or utcnow()
    flow = build_flow(open_issues, closed_issues, claimants, now)
    snapshot: dict = {
        "timestamp": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "flow": flow,
    }
    trl = build_trl(repo_root)
    if trl:
        snapshot["trl"] = trl
    snapshot["notes"] = build_notes(open_issues, flow, claimants, now)
    return snapshot


def collect_claimants(open_issues: list[dict], token: str | None, repo: str) -> list[dict]:
    """For each claimed issue, the newest claim comment's run-id and time, plus
    the issue's last-updated time for the 'no activity since' check."""
    out = []
    for issue in open_issues:
        if "status:claimed" not in label_names(issue):
            continue
        comments = fetch_comments(repo, issue["number"], token)
        claims = []
        for c in comments:
            m = CLAIM_RE.search(c.get("body") or "")
            if m:
                claims.append((c.get("created_at") or "", m))
        if not claims:
            out.append({"run": None, "claimed_at": None,
                        "updated_at": parse_utc(issue.get("updated_at") or "")})
            continue
        created, match = max(claims, key=lambda pair: pair[0])
        out.append({
            "run": match.group("run"),
            "who": match.group("who"),
            "claimed_at": parse_utc(created),
            "updated_at": parse_utc(issue.get("updated_at") or ""),
        })
    return out


# --------------------------------------------------------------------------
# Appending
# --------------------------------------------------------------------------

def read_last_snapshot(path: Path) -> dict | None:
    if not path.exists():
        return None
    last = None
    for line in path.read_text().splitlines():
        if line.strip():
            last = line
    if not last:
        return None
    try:
        return json.loads(last)
    except json.JSONDecodeError:
        return None


def should_append(snapshot: dict, previous: dict | None, force: bool) -> bool:
    if force or previous is None:
        return True
    return (snapshot.get("flow") != previous.get("flow")
            or snapshot.get("trl") != previous.get("trl"))


def append(path: Path, snapshot: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text() if path.exists() else ""
    separator = "" if (not existing or existing.endswith("\n")) else "\n"
    with path.open("a") as fh:
        fh.write(separator + json.dumps(snapshot, sort_keys=True) + "\n")


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append a status snapshot for HuB.")
    parser.add_argument("--repo", required=True,
                        help="owner/name, e.g. philipdallen/Maith")
    parser.add_argument("--file", default=None,
                        help=f"log path (default: repo root / {LOG_NAME})")
    parser.add_argument("--token-env", default="GITHUB_TOKEN",
                        help="env var holding a token (optional for public repos)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the snapshot; write nothing")
    parser.add_argument("--force", action="store_true",
                        help="append even if identical to the last snapshot")
    args = parser.parse_args(argv)

    repo_root = Path(os.environ.get("HUB_REPO_ROOT", ".")).resolve()
    log_path = Path(args.file) if args.file else repo_root / LOG_NAME
    token = os.environ.get(args.token_env) or None

    try:
        open_issues = fetch_issues(args.repo, token, "open")
        closed_issues = fetch_issues(args.repo, token, "closed",
                                     f"&since={(utcnow() - CYCLE_LOOKBACK).isoformat()}")
        claimants = collect_claimants(open_issues, token, args.repo)
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"error: could not read issues for {args.repo}: {exc}", file=sys.stderr)
        return 1

    snapshot = build_snapshot(open_issues, closed_issues, claimants, repo_root)
    previous = read_last_snapshot(log_path)

    if args.dry_run:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        print(f"(dry-run: would {'append' if should_append(snapshot, previous, args.force) else 'skip (unchanged)'} to {log_path})")
        return 0

    if not should_append(snapshot, previous, args.force):
        print(f"unchanged since last snapshot; nothing appended to {log_path}")
        return 0

    append(log_path, snapshot)
    print(f"appended to {log_path}: {snapshot['notes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())