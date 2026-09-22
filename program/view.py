#!/usr/bin/env python3
"""Derived views over the program ledger + committed issue-state cache (issue #32).

Every view is **computed**, never stored. A stored view would be a second
source of truth that can silently disagree with the ledger; when a view is
wrong the fix is to fix the record, not the view (PROGRAM_MANAGEMENT_SPEC.md §5).

The five views and the question each answers (spec §5):

  program_state   Per issue kind: counts by outcome class, open/closed, and the
                  rung distribution for claims
  traversal       For one issue: its ledger records, the results they rest on,
                  the findings, the DECs, and the issues it blocked or created
  decision_queue  Every `kind:decision` issue and what it blocks
  health          Gates defined vs wired, findings by rung, and the §7
                  label-hygiene count
  open_gaps       Every `kind:gap` and `kind:defect` with its age in days

Inputs (Tier 0 — ledger + committed cache only, no network):

  program/ledger.jsonl            the records (program/ledger.py reads them)
  tests/fixture_issue_state.json  the committed issue-state cache
  tooling/gates/run_all.py --json gates REGISTERED in the harness (spec §10 Q4)

Usage:
    python3 program/view.py            # the program at a glance
    python3 program/view.py --json     # machine-readable
    python3 program/view.py --issue 24 # one issue's full traversal

Exit codes: 0 ok; 1 the ledger is missing, empty, or malformed. An empty or
malformed ledger fails loudly rather than rendering an empty dashboard.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "program" / "ledger.jsonl"
CACHE_PATH = ROOT / "tests" / "fixture_issue_state.json"
REGISTRY = ROOT / "tooling" / "gates" / "run_all.py"

STATUS_PREFIX = "status:"
KIND_PREFIX = "kind:"


class ViewError(RuntimeError):
    """A view cannot be computed — the input is missing or malformed."""


def _rel(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise (tests use tmp paths)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_ledger_module():
    """Import program/ledger.py so the schema and vocabularies are not copied.

    The outcome classes, the rung range, and the append rules live in exactly
    one module; a view that carried its own copy would be the drift spec §4
    warns about.
    """
    sys.path.insert(0, str(ROOT / "program"))
    import ledger  # type: ignore

    return ledger


def load_records() -> list:
    ledger = _load_ledger_module()
    if not LEDGER_PATH.exists():
        raise ViewError(f"ledger missing: {_rel(LEDGER_PATH)}")
    try:
        records = ledger.read_ledger(LEDGER_PATH)
    except ledger.LedgerError as e:
        raise ViewError(f"malformed ledger: {e}") from e
    if not records:
        raise ViewError(
            "ledger is empty — a dashboard over nothing is not a view "
            "(spec §5); backfill records before rendering (issue #33)"
        )
    return records


def load_cache() -> dict:
    """The committed issue-state cache, keyed by issue number as a string."""
    if not CACHE_PATH.exists():
        raise ViewError(f"issue-state cache missing: {_rel(CACHE_PATH)}")
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ViewError(f"malformed issue-state cache: {e}") from e
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_registry() -> dict:
    """The gates the harness has REGISTERED (spec §10 Q4).

    This is not "gates defined in the spec" — that prose cannot be computed, and
    spec §10 Q4 says to accept that and say so. The registry is the honest,
    machine-readable source of what is wired.
    """
    if not REGISTRY.exists():
        raise ViewError(f"gate registry missing: {_rel(REGISTRY)}")
    proc = subprocess.run(
        [sys.executable, str(REGISTRY), "--json"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    # rc 1 means at least one gate is BROKEN/FAIL — the JSON is still valid and
    # is exactly the state a health view must be able to show.
    if proc.returncode not in (0, 1) or not proc.stdout.strip():
        raise ViewError(
            f"gate registry produced no JSON (rc={proc.returncode}): "
            f"{proc.stderr.strip()[:200]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ViewError(f"malformed gate registry JSON: {e}") from e


def _kind_of(cache: dict, issue: int) -> str:
    entry = cache.get(str(issue), {})
    for label in entry.get("labels", []):
        if label.startswith(KIND_PREFIX):
            return label[len(KIND_PREFIX):]
    return "unknown"


def _status_of(cache: dict, issue: int) -> str | None:
    entry = cache.get(str(issue), {})
    for label in entry.get("labels", []):
        if label.startswith(STATUS_PREFIX):
            return label[len(STATUS_PREFIX):]
    return None


def _is_open(cache: dict, issue: int) -> bool:
    return cache.get(str(issue), {}).get("state") == "OPEN"


# --------------------------------------------------------------- view 1
def view_program_state(records: list, cache: dict) -> dict:
    """Per issue kind: counts by outcome class, open/closed, rung distribution."""
    by_kind: dict[str, dict] = {}
    for rec in records:
        kind = _kind_of(cache, rec.issue)
        bucket = by_kind.setdefault(
            kind, {"open": 0, "closed": 0, "by_outcome": {}, "records": 0}
        )
        bucket["records"] += 1
        if _is_open(cache, rec.issue):
            bucket["open"] += 1
        else:
            bucket["closed"] += 1
        key = rec.outcome if rec.outcome is not None else "in-flight"
        bucket["by_outcome"][key] = bucket["by_outcome"].get(key, 0) + 1

    rung_dist: dict[str, int] = {}
    for rec in records:
        if rec.rung is not None:
            rung_dist[str(rec.rung)] = rung_dist.get(str(rec.rung), 0) + 1

    return {"by_kind": by_kind, "rung_distribution": rung_dist}


# --------------------------------------------------------------- view 2
def view_traversal(records: list, cache: dict, issue: int) -> dict:
    """One issue's full traversal: records, results, findings, DECs, edges."""
    mine = [r for r in records if r.issue == issue]
    results: list[str] = []
    decisions: list[str] = []
    findings: list[int] = []
    blocks: list[int] = []
    emergent: list[int] = []
    for rec in mine:
        results += [r for r in rec.results if r not in results]
        decisions += [d for d in rec.decisions if d not in decisions]
        findings += [f for f in rec.findings if f not in findings]
        blocks += [b for b in rec.blocks if b not in blocks]
        emergent += [e for e in rec.emergent if e not in emergent]

    def edge(n: int) -> dict:
        return {
            "issue": n,
            "known": str(n) in cache,
            "state": cache.get(str(n), {}).get("state"),
            "outcome": next((r.outcome for r in records if r.issue == n), None),
        }

    return {
        "issue": issue,
        "kind": _kind_of(cache, issue),
        "state": cache.get(str(issue), {}).get("state", "UNKNOWN"),
        "records": [r.to_json() for r in mine],
        "results": results,
        "decisions": decisions,
        "findings": findings,
        "blocks": [edge(b) for b in blocks],
        "emergent": [edge(e) for e in emergent],
    }


# --------------------------------------------------------------- view 3
def view_decision_queue(cache: dict) -> list[dict]:
    """Every `kind:decision` issue and what it blocks (the human's inbox)."""
    # Reverse edges: a decision D blocks T when T.blocked_by contains D.
    blocked_by: dict[int, list[int]] = {}
    for key, entry in cache.items():
        try:
            num = int(key)
        except ValueError:
            continue
        for blocker in entry.get("blocked_by", []):
            blocked_by.setdefault(blocker, []).append(num)

    out = []
    for key, entry in cache.items():
        try:
            num = int(key)
        except ValueError:
            continue
        if f"{KIND_PREFIX}decision" not in entry.get("labels", []):
            continue
        out.append({
            "issue": num,
            "state": entry.get("state"),
            "blocks": sorted(blocked_by.get(num, [])),
        })
    return sorted(out, key=lambda d: d["issue"])


# --------------------------------------------------------------- view 4
def view_health(records: list, cache: dict, registry: dict) -> dict:
    """Gates defined vs wired, findings by rung, and the §7 label-hygiene count."""
    gates = registry.get("gates", [])
    wired = [g for g in gates if g.get("status") != "BROKEN"]

    findings_by_rung: dict[str, int] = {}
    for rec in records:
        if rec.findings:
            findings_by_rung[str(rec.rung)] = (
                findings_by_rung.get(str(rec.rung), 0) + len(rec.findings)
            )

    hygiene_violations = []
    for key, entry in cache.items():
        try:
            num = int(key)
        except ValueError:
            continue
        if entry.get("state") != "OPEN":
            continue
        labels = entry.get("labels", [])
        n_status = sum(1 for l in labels if l.startswith(STATUS_PREFIX))
        n_kind = sum(1 for l in labels if l.startswith(KIND_PREFIX))
        if n_status != 1 or n_kind != 1:
            hygiene_violations.append({
                "issue": num,
                "status_labels": n_status,
                "kind_labels": n_kind,
                "labels": sorted(labels),
            })

    return {
        "gates_defined": len(gates),
        "gates_wired": len(wired),
        "gate_status": {g.get("id"): g.get("status") for g in gates},
        "findings_by_rung": findings_by_rung,
        "label_hygiene_violations": sorted(
            hygiene_violations, key=lambda d: d["issue"]
        ),
        "note": (
            "gates_defined counts gates REGISTERED in tooling/gates/run_all.py, "
            "not gates named in the spec prose — 'defined but not wired' cannot "
            "be computed from the registry, and spec §10 Q4 says to say so "
            "rather than fake it"
        ),
    }


# --------------------------------------------------------------- view 5
def view_open_gaps(cache: dict) -> list[dict]:
    """Every `kind:gap` and `kind:defect` with its age in days."""
    out = []
    for key, entry in cache.items():
        try:
            num = int(key)
        except ValueError:
            continue
        labels = entry.get("labels", [])
        if not any(l in (f"{KIND_PREFIX}gap", f"{KIND_PREFIX}defect") for l in labels):
            continue
        if entry.get("state") != "OPEN":
            continue
        # The committed cache deliberately does not carry createdAt (program/
        # ledger.py's coverage-map rule), so age cannot be derived offline.
        # Report the gap honestly instead of inventing a number.
        out.append({
            "issue": num,
            "kind": _kind_of(cache, num),
            "age_days": None,
            "age_unknown": True,
            "age_note": "cache carries no createdAt; age needs a live GitHub read",
        })
    return sorted(out, key=lambda d: d["issue"])


def build_all(records: list, cache: dict, registry: dict) -> dict:
    return {
        "program_state": view_program_state(records, cache),
        "decision_queue": view_decision_queue(cache),
        "health": view_health(records, cache, registry),
        "open_gaps": view_open_gaps(cache),
    }


# --------------------------------------------------------------- rendering
QUESTIONS = {
    "program_state": "Per issue kind: counts by outcome class, open/closed, and "
                     "the rung distribution for claims",
    "traversal": "For one issue: its ledger records, the results they rest on, "
                 "the findings, the DECs, and the issues it blocked or created",
    "decision_queue": "Every kind:decision issue and what it blocks — the human's inbox",
    "health": "Gates defined vs wired, findings by rung, and the §7 label-hygiene count",
    "open_gaps": "Every kind:gap and kind:defect with its age in days",
}


def _render_text(all_views: dict) -> None:
    ps = all_views["program_state"]
    print(f"== Program state — {QUESTIONS['program_state']} ==")
    for kind in sorted(ps["by_kind"]):
        b = ps["by_kind"][kind]
        outcomes = ", ".join(f"{k}={v}" for k, v in sorted(b["by_outcome"].items()))
        print(f"  {kind:10s} open={b['open']} closed={b['closed']} "
              f"records={b['records']}  [{outcomes}]")
    print(f"  rung distribution (claims): "
          f"{ps['rung_distribution'] or '(none)'}")

    print(f"\n== Decision queue — {QUESTIONS['decision_queue']} ==")
    dq = all_views["decision_queue"]
    if not dq:
        print("  (none)")
    for d in dq:
        print(f"  #{d['issue']} ({d['state']}) blocks {d['blocks'] or '(nothing)'}")

    h = all_views["health"]
    print(f"\n== Health — {QUESTIONS['health']} ==")
    print(f"  gates registered={h['gates_defined']} wired={h['gates_wired']}")
    print(f"  findings by rung: {h['findings_by_rung'] or '(none)'}")
    print(f"  open issues violating §7 label hygiene: "
          f"{[v['issue'] for v in h['label_hygiene_violations']] or '(none)'}")
    print(f"  note: {h['note']}")

    print(f"\n== Open gaps — {QUESTIONS['open_gaps']} ==")
    og = all_views["open_gaps"]
    if not og:
        print("  (none)")
    for g in og:
        print(f"  #{g['issue']} {g['kind']} age_days={g['age_days']} "
              f"({g['age_note']})")


def _render_traversal(t: dict) -> None:
    print(f"== Traversal — {QUESTIONS['traversal']} ==")
    print(f"   #{t['issue']} ({t['kind']}, {t['state']})")
    print(f"  records: {[r['id'] for r in t['records']] or '(none)'}")
    print(f"  results: {t['results'] or '(none)'}")
    print(f"  findings: {t['findings'] or '(none)'}")
    print(f"  decisions: {t['decisions'] or '(none)'}")
    print(f"  blocks: "
          f"{[(e['issue'], e['outcome'] or e['state']) for e in t['blocks']] or '(none)'}")
    print(f"  emergent: "
          f"{[(e['issue'], e['outcome'] or e['state']) for e in t['emergent']] or '(none)'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="derived views over the program ledger")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--issue", type=int, help="one issue's full traversal")
    ap.add_argument("--ledger", type=Path, default=None,
                    help="read this ledger instead of program/ledger.jsonl "
                         "(e.g. program/tests/fixture_ledger.jsonl)")
    ap.add_argument("--cache", type=Path, default=None,
                    help="read this issue-state cache instead of "
                         "tests/fixture_issue_state.json")
    args = ap.parse_args(argv)

    global LEDGER_PATH, CACHE_PATH
    if args.ledger is not None:
        LEDGER_PATH = args.ledger
    if args.cache is not None:
        CACHE_PATH = args.cache
    try:
        records = load_records()
        cache = load_cache()
        if args.issue is not None:
            traversal = view_traversal(records, cache, args.issue)
            if args.json:
                print(json.dumps({"traversal": traversal}, indent=2))
            else:
                _render_traversal(traversal)
            return 0
        registry = load_registry()
        all_views = build_all(records, cache, registry)
    except ViewError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(all_views, indent=2))
    else:
        _render_text(all_views)
    return 0


if __name__ == "__main__":
    sys.exit(main())
