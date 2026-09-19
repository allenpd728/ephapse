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

    Note both `created_at` values are fresh server-side: liveness now follows
    the server timestamp (#35 defect 1), so a fixture relying on the declared
    string to stay live would be testing the wrong thing.
    """
    issues = [{"number": 99, "title": "t", "state": "open"}]
    comments = {"99": [
        # later comment id, earlier DECLARED time
        {"id": 5000, "created_at": "2026-09-19T10:59:00Z",
         "body": "claimed by openhands run=later-id-early-clock "
                 "at 2026-09-19T09:00:00Z"},
        # earlier comment id, later DECLARED time
        {"id": 4000, "created_at": "2026-09-19T10:58:00Z",
         "body": "claimed by openhands run=earlier-id-late-clock "
                 "at 2026-09-19T10:30:00Z"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert v["winner"] is not None, "both claims are server-fresh, so both are live"
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
    """An unparseable declared timestamp must not create a phantom lock.

    Superseded in mechanism by #35 defect 1: liveness now follows the SERVER
    timestamp, so a malformed in-body timestamp is simply ignored. The property
    this test protects is unchanged — a claim that is genuinely old must be
    reclaimable, and must not be kept alive by a broken timestamp string. The
    fixture is now server-stale so it exercises that.
    """
    issues = [{"number": 96, "title": "t", "state": "open"}]
    comments = {"96": [
        {"id": 300, "created_at": "2026-09-19T08:00:00Z",   # 3h: genuinely old
         "body": "claimed by openhands run=20260919-0800-aaaa "
                 "at NOT-A-TIMESTAMP"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert not v["live"], "a server-old claim with a broken ts is not live"
    assert v["winner"] is None


# ------------------------------------------- #35 defects 1-3 (each fails on
# pre-fix code; see the issue for the reproductions)
def test_35_defect1_liveness_uses_server_time_not_declared_time():
    """A skewed in-body timestamp must not make a fresh claim look stale.

    The server says the comment is 2 minutes old; the body claims 2020. Before
    the fix `age()` read the body string, so this reported stale and reclaimable
    — letting a live claim be swept, or (by the mirror) never swept at all.
    """
    issues = [{"number": 1, "title": "t", "state": "open"}]
    comments = {"1": [
        {"id": 9001, "created_at": "2026-09-19T11:58:00Z",
         "body": "claimed by openhands run=20260919-1158-aaaa "
                 "at 2020-01-01T00:00:00Z"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert v["live"], "a claim must be live by SERVER time, not declared time"
    assert v["winner"].comment_id == 9001


def test_35_defect1b_declared_time_cannot_make_a_stale_claim_immortal():
    """The mirror of defect 1: a future in-body timestamp must not prevent a sweep."""
    issues = [{"number": 1, "title": "t", "state": "open"}]
    comments = {"1": [
        {"id": 9002, "created_at": "2026-09-19T09:00:00Z",   # 3h old: stale
         "body": "claimed by openhands run=20260919-0900-aaaa "
                 "at 2099-01-01T00:00:00Z"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert not v["live"], "a server-stale claim must be sweepable regardless of prose"


def test_35_defect2_heartbeat_extends_liveness():
    """A heartbeat comment after the window keeps the claim alive.

    Protocol § 1 tells a session waiting on a remote queue to post a heartbeat
    with its run-id rather than lose the claim. Before the fix the parser looked
    only at `claimed by` clauses, so that prescribed heartbeat did nothing.
    """
    issues = [{"number": 1, "title": "t", "state": "open"}]
    comments = {"1": [
        {"id": 9003, "created_at": "2026-09-19T09:30:00Z",
         "body": "claimed by openhands run=20260919-0930-bbbb "
                 "at 2026-09-19T09:30:00Z"},
        {"id": 9004, "created_at": "2026-09-19T10:50:00Z",
         "body": "heartbeat run=20260919-0930-bbbb - waiting on the NDIF queue"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert v["live"], "the § 1 heartbeat must extend liveness"


def test_35_defect2b_without_heartbeat_the_claim_is_stale():
    """The negative direction: no later activity ⇒ genuinely stale."""
    issues = [{"number": 1, "title": "t", "state": "open"}]
    comments = {"1": [
        {"id": 9005, "created_at": "2026-09-19T09:30:00Z",
         "body": "claimed by openhands run=20260919-0930-bbbb "
                 "at 2026-09-19T09:30:00Z"},
        {"id": 9006, "created_at": "2026-09-19T10:50:00Z",
         "body": "unrelated remark from another session about the weather"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    assert not v["live"], "a heartbeat by another run must not keep this claim alive"


def test_35_defect3_claim_without_at_clause_is_parsed():
    """A claim omitting ` at <ts>` must still count, or a collision is missed.

    Before the fix this failed OPEN: the earlier real claim was invisible, so no
    collision was reported and the SECOND claimer could be named the winner.
    """
    issues = [{"number": 1, "title": "t", "state": "open"}]
    comments = {"1": [
        {"id": 9100, "created_at": "2026-09-19T11:50:00Z",
         "body": "claimed by openhands run=20260919-1150-cccc"},
        {"id": 9101, "created_at": "2026-09-19T11:52:00Z",
         "body": "claimed by openhands run=20260919-1152-dddd "
                 "at 2026-09-19T11:52:00Z"},
    ]}
    claims = A.parse_claims(issues, comments, now=NOW)
    assert len(claims) == 2, "a claim without the optional at-clause must parse"
    v = A.audit(issues, comments, now=NOW)[0]
    assert v["collisions"], "the collision must be reported"
    assert v["winner"].comment_id == 9100, "earliest id wins, not the later claimer"


def test_35_describe_issue_states_which_timestamp_was_used():
    """The lock and the auditor must not disagree about ownership (#35 DoD)."""
    issues = [{"number": 1, "title": "t", "state": "open"}]
    comments = {"1": [
        {"id": 9200, "created_at": "2026-09-19T11:58:00Z",
         "body": "claimed by openhands run=20260919-1158-aaaa "
                 "at 2020-01-01T00:00:00Z"},
    ]}
    v = A.audit(issues, comments, now=NOW)[0]
    text = A.describe_issue(v, now=NOW)
    assert "server_time" in text
    assert "declared_time" in text
    assert "2026-09-19T11:58:00Z" in text


def test_35_claim_is_live_accepts_a_heartbeat():
    """claim.py's is_live must honour the same heartbeat rule as the auditor."""
    import claim as C
    old = "20260919-0930-bbbb 2026-09-19T09:30:00Z"
    fresh = datetime(2026, 9, 19, 10, 50, 0, tzinfo=timezone.utc)
    assert not C.is_live(old, now=NOW), "90 min old with no activity is stale"
    assert C.is_live(old, now=NOW, last_activity=fresh), \
        "recent activity must keep the lock"


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