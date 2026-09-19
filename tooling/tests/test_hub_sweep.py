#!/usr/bin/env python3
"""Offline tests for hub_sweep.py — no network, no token.

Run: python3 -m pytest tooling/tests/test_hub_sweep.py
  or: python3 tooling/tests/test_hub_sweep.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()


def find_sweep() -> Path:
    """Locate hub_sweep.py from this test file, wherever it is installed.
    Maith/PleaNP/ephapse use tooling/, muse uses tools/."""
    for parent in HERE.parents:
        for sub in ("tooling", "tools"):
            candidate = parent / sub / "hub_sweep.py"
            if candidate.exists():
                return candidate
    raise FileNotFoundError("hub_sweep.py not found relative to " + str(HERE))


SWEEP = find_sweep()
ROOT = SWEEP.parent.parent

spec = importlib.util.spec_from_file_location("hub_sweep", SWEEP)
hub = importlib.util.module_from_spec(spec)
sys.modules["hub_sweep"] = hub
spec.loader.exec_module(hub)

NOW = dt.datetime(2026, 9, 19, 12, 0, 0, tzinfo=dt.timezone.utc)


def iso(minutes_ago: int) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def issue(number, labels=(), created=None, closed=None, updated=None, title="t"):
    return {
        "number": number,
        "title": title,
        "labels": [{"name": l} for l in labels],
        "created_at": created or iso(60 * 24 * 5),
        "closed_at": closed,
        "updated_at": updated or iso(30),
    }


# ---- label parsing -------------------------------------------------------

def test_label_names():
    assert hub.label_names(issue(1, ["status:available", "bug"])) == [
        "status:available", "bug"]


# ---- stale-claim rule ----------------------------------------------------

def test_live_claim_is_not_stale():
    claim = {"claimed_at": hub.parse_utc(iso(30)), "updated_at": hub.parse_utc(iso(30))}
    assert hub.count_stale([claim], NOW) == 0


def test_fresh_claim_with_old_updated_at_is_not_stale():
    # Claim made 10 min ago; updated_at is old/equal. Age gate wins -> live.
    claim = {"claimed_at": hub.parse_utc(iso(10)), "updated_at": hub.parse_utc(iso(10))}
    assert hub.count_stale([claim], NOW) == 0


def test_old_claim_with_no_activity_is_stale():
    claim = {"claimed_at": hub.parse_utc(iso(120)), "updated_at": hub.parse_utc(iso(120))}
    assert hub.count_stale([claim], NOW) == 1


def test_old_claim_with_recent_activity_is_live():
    claim = {"claimed_at": hub.parse_utc(iso(120)), "updated_at": hub.parse_utc(iso(5))}
    assert hub.count_stale([claim], NOW) == 0


def test_claim_with_no_parseable_time_is_not_counted():
    claim = {"claimed_at": None, "updated_at": None}
    assert hub.count_stale([claim], NOW) == 0


# ---- flow metrics --------------------------------------------------------

def test_blocked_ratio_and_counts():
    opens = [
        issue(1, ["status:available"]),
        issue(2, ["status:claimed"]),
        issue(3, ["status:blocked-needs-input"]),
        issue(4, ["status:blocked-needs-input", "bug"]),
    ]
    flow = hub.build_flow(opens, [], [], NOW)
    assert flow["open_total"] == 4
    assert flow["wip"] == 1
    assert flow["blocked"] == 2
    assert flow["available"] == 1
    assert flow["blocked_ratio"] == 0.5


def test_blocked_ratio_zero_when_no_issues():
    flow = hub.build_flow([], [], [], NOW)
    assert flow["open_total"] == 0
    assert flow["blocked_ratio"] == 0.0
    assert flow["wip"] == 0


def test_needs_review_counts_both_label_shapes():
    opens = [
        issue(1, ["needs-review"]),
        issue(2, ["review:pending"]),
        issue(3, ["review:confirmed"]),
        issue(4, []),
    ]
    assert hub.build_flow(opens, [], [], NOW)["needs_review"] == 3


def test_cycle_time_omitted_when_none_closed():
    flow = hub.build_flow([issue(1)], [], [], NOW)
    assert "cycle_time_median_hours" not in flow


def test_cycle_time_median_over_closed():
    closed = [
        issue(1, closed=iso(60)),
        issue(2, closed=iso(60)),
        issue(3, closed=iso(60)),
    ]
    for i in closed:
        i["created_at"] = (NOW - dt.timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    flow = hub.build_flow([], closed, [], NOW)
    assert flow["cycle_time_median_hours"] == 9.0
    assert flow["closed_last_30d"] == 3


def test_cycle_time_ignores_closed_before_lookback():
    old = issue(1, closed=(NOW - dt.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    flow = hub.build_flow([], [old], [], NOW)
    assert "cycle_time_median_hours" not in flow


def test_median_even_count():
    assert hub.median([1, 2, 3, 4]) == 2.5
    assert hub.median([5]) == 5
    assert hub.median([]) is None


# ---- TRL --------------------------------------------------------------

def test_trl_absent_file_is_omitted():
    with tempfile.TemporaryDirectory() as td:
        assert hub.build_trl(Path(td)) is None


def test_trl_reads_components_and_clamps_range():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "status").mkdir()
        (root / "status" / "trl.json").write_text(json.dumps(
            {"components": {"IR": 4, "gates": 2, "bad_high": 99, "bad_str": "x"}}))
        assert hub.build_trl(root) == {"IR": 4, "gates": 2}


def test_trl_invalid_json_is_ignored():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "status").mkdir()
        (root / "status" / "trl.json").write_text("{not json")
        assert hub.build_trl(root) is None


# ---- snapshot + append semantics ----------------------------------------

def test_snapshot_shape_has_timestamp_flow_notes():
    snap = hub.build_snapshot([issue(1, ["status:available"])], [], [], Path("."), NOW)
    assert snap["timestamp"].endswith("Z")
    assert "flow" in snap and "notes" in snap
    assert "trl" not in snap


def test_append_only_never_rewrites(tmp_path):
    log = tmp_path / "status_log.jsonl"
    hub.append(log, {"timestamp": "2026-01-01T00:00:00Z", "flow": {"wip": 0}})
    hub.append(log, {"timestamp": "2026-01-02T00:00:00Z", "flow": {"wip": 1}})
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["flow"]["wip"] == 0
    assert json.loads(lines[1])["flow"]["wip"] == 1


def test_append_handles_missing_trailing_newline(tmp_path):
    log = tmp_path / "status_log.jsonl"
    log.write_text('{"timestamp":"a","flow":{"wip":0}}')  # no trailing newline
    hub.append(log, {"timestamp": "b", "flow": {"wip": 1}})
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_should_append_skips_identical(tmp_path):
    prev = {"flow": {"wip": 1}, "trl": {"a": 2}}
    same = {"flow": {"wip": 1}, "trl": {"a": 2}, "timestamp": "later"}
    assert hub.should_append(same, prev, force=False) is False
    assert hub.should_append(same, prev, force=True) is True


def test_should_append_when_flow_changes():
    prev = {"flow": {"wip": 1}}
    changed = {"flow": {"wip": 2}}
    assert hub.should_append(changed, prev, force=False) is True


def test_should_append_first_time_always():
    assert hub.should_append({"flow": {}}, None, force=False) is True


def test_read_last_snapshot_handles_blank_and_garbage(tmp_path):
    log = tmp_path / "s.jsonl"
    assert hub.read_last_snapshot(log) is None
    log.write_text('{"flow":{"wip":1}}\n\n')
    assert hub.read_last_snapshot(log) == {"flow": {"wip": 1}}
    log.write_text("garbage\n")
    assert hub.read_last_snapshot(log) is None


# ---- pagination link parsing --------------------------------------------

def test_next_link_parsing():
    header = ('<https://api.github.com/x?page=2>; rel="next", '
              '<https://api.github.com/x?page=9>; rel="last"')
    assert hub._next_link(header) == "https://api.github.com/x?page=2"
    assert hub._next_link('<https://api.github.com/x?page=1>; rel="prev"') is None
    assert hub._next_link("") is None


def test_claim_regex_extracts_run_id():
    body = "claimed by openhands run=20260919-1004-db83 at 2026-09-19T10:05Z"
    m = hub.CLAIM_RE.search(body)
    assert m.group("run") == "20260919-1004-db83"
    assert m.group("who") == "openhands"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                if fn.__code__.co_argcount:
                    with tempfile.TemporaryDirectory() as td:
                        fn(Path(td))
                else:
                    fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    print(f"\n{'ok' if not failures else str(failures) + ' failed'}")
    raise SystemExit(1 if failures else 0)