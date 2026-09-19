#!/usr/bin/env python3
"""Tests for the claim audit tool (issue #26).

Run:  python3 -m pytest tooling/claims/tests/ -q

The audit exists because the protocol's original ownership check — read the
*latest* claim comment, confirm it is yours — cannot detect a live earlier
claim. These tests pin the corrected behaviour on the real incidents:

  * collision_5.json  — the #5 duplicate claims that produced opposite verdicts
  * collision_11.json — the #11 duplicate claims (2.5 min apart)

and the two negative directions that matter:

  * clean_single_claim.json — one live claim is NOT a collision
  * stale_claim.json        — an expired claim is NOT a live collision

A tool that fires on the clean or stale cases would block legitimate work; one
that stays silent on the collision cases would miss the bug it was written for.
Both directions are asserted, per the repo's fixture rule.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import audit_claims as A  # noqa: E402

FIXTURES = HERE / "fixtures"

# Fixed clock for the synthetic (non-fixture) cases below. The fixture-based
# tests use each fixture's own declared `_evaluate_at` instead.
NOW = datetime(2026, 9, 19, 11, 0, 0, tzinfo=timezone.utc)


def _load(name: str):
    """Load a fixture and its declared evaluation time.

    Each fixture carries `_evaluate_at`, the moment it is meant to be judged.
    This matters: the collision fixtures reproduce real incidents from
    2026-09-18/19, so against wall-clock `now` their claims have long since
    passed the 1-hour stale window and would read as reclaimable rather than as
    live collisions. The first version of these tests did exactly that and
    failed against its own fixtures — recorded because it is the same class of
    error as a gate fixture that cannot reach the branch it targets.
    """
    base = FIXTURES / name
    issues, comments = A.load_cache(base)
    return issues, comments, A.cache_evaluate_at(base)


def _verdicts(name: str, mine: str | None = None):
    issues, comments, when = _load(name)
    return A.audit(issues, comments, mine=mine, now=when)


# ------------------------------------------------------------ collisions
def test_real_5_collision_is_detected():
    """The #5 duplicate claims must be reported as a collision."""
    v = _verdicts("collision_5.json")
    collided = [x for x in v if x["collisions"]]
    assert len(collided) == 1
    assert collided[0]["issue"] == 5


def test_real_5_winner_is_the_earliest_comment_id():
    """Winner by earliest server-assigned id, not by timestamp string."""
    v = [x for x in _verdicts("collision_5.json") if x["issue"] == 5][0]
    assert v["winner"].comment_id == 5737426522
    assert v["winner"].run_id == "20260918-2329-zbmn"


def test_real_11_collision_is_detected_and_winner_is_earliest_id():
    """The #11 incident: 2.5 minutes apart, my claim (earlier id) wins."""
    v = [x for x in _verdicts("collision_11.json") if x["issue"] == 11][0]
    assert v["collisions"], "the #11 duplicate claims must be reported"
    assert v["winner"].comment_id == 5739467938
    assert v["winner"].run_id == "20260919-0451-6421"


def test_i_own_is_reported_from_the_losers_side():
    """From the losing run's view the audit must say it lost."""
    v = [x for x in _verdicts("collision_11.json", mine="20260918-2332-e7c4")
         if x["issue"] == 11][0]
    assert v["i_own"] is False
    assert "I LOST" in A.report([v], "20260918-2332-e7c4")


def test_i_own_is_reported_from_the_winners_side():
    v = [x for x in _verdicts("collision_11.json", mine="20260919-0451-6421")
         if x["issue"] == 11][0]
    assert v["i_own"] is True
    assert "I HOLD THE CLAIM" in A.report([v], "20260919-0451-6421")


def test_earliest_id_wins_even_when_timestamp_shows_the_opposite():
    """The tiebreak must not trust agent-supplied timestamps.

    A skewed clock could make the later claim *report* an earlier time. The id
    is server-assigned and monotonic, so it must decide regardless.
    """
    issues = [{"number": 99, "title": "t", "state": "open"}]
    comments = {"99": [
        {"id": 5000, "created_at": "2026-09-19T09:59:00Z",
         "body": "claimed by openhands run=later-id-early-clock "
                 "at 2026-09-19T09:00:00Z"},
        {"id": 4000, "created_at": "2026-09-19T09:01:00Z",
         "body": "claimed by openhands run=earlier-id-late-clock "
                 "at 2026-09-19T10:30:00Z"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert v["winner"].comment_id == 4000, "id must decide, not the timestamp"
    assert v["winner"].run_id == "earlier-id-late-clock"


# --------------------------------------------------------- negative cases
def test_single_live_claim_is_not_a_collision():
    """Ordinary single ownership must not be reported as a problem."""
    v = _verdicts("clean_single_claim.json")
    assert not any(x["collisions"] for x in v)
    assert "no live claim collisions" in A.report(v, None)


def test_stale_claim_is_not_a_live_collision():
    """An expired claim is reclaimable, not a collision."""
    v = _verdicts("stale_claim.json")
    assert not any(x["collisions"] for x in v)
    assert "reclaimable" in A.report(v, None)


def test_stale_plus_fresh_is_not_a_collision():
    """An expired claim alongside a fresh one is ordinary reclaim, not a race."""
    issues = [{"number": 98, "title": "t", "state": "open"}]
    comments = {"98": [
        {"id": 100, "created_at": "2026-09-18T10:00:00Z",
         "body": "claimed by openhands run=old at 2026-09-18T10:00:00Z"},
        {"id": 200, "created_at": "2026-09-19T10:30:00Z",
         "body": "claimed by openhands run=new at 2026-09-19T10:30:00Z"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert not v["collisions"]
    assert v["winner"].run_id == "new"


def test_issue_with_no_claims_is_ignored():
    issues = [{"number": 97, "title": "t", "state": "open"}]
    v = A.audit(issues, {"97": [{"id": 1, "created_at": "2026-09-19T10:00:00Z",
                                 "body": "just a comment"}]}, now=NOW)
    assert v == []


def test_done_comments_are_not_parsed_as_claims():
    """`done by ... run=` must not register as a claim."""
    issues, comments, when = _load("collision_5.json")
    claims = A.parse_claims(issues, comments, now=when)
    assert all("done by" not in c.run_id for c in claims)
    assert {c.run_id for c in claims} == {
        "20260918-2329-zbmn", "20260918-2332-e7c4", "20260919-0600-aaaa"}


def test_unparseable_timestamp_is_treated_as_stale_not_live():
    """A malformed timestamp must not create a permanent phantom lock."""
    issues = [{"number": 96, "title": "t", "state": "open"}]
    comments = {"96": [
        {"id": 300, "created_at": "2026-09-19T10:00:00Z",
         "body": "claimed by openhands run=x at NOT-A-TIMESTAMP"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert not v["live"], "a claim with no valid timestamp cannot be live"
    assert v["winner"] is None


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {name}\n          {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}\n          {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())