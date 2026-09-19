# tooling/claims

Claim-collision detection for the multi-agent claim protocol
(`docs/MULTI_AGENT_WORKFLOW.md` § 4, DEC-029).

## Why this exists

The protocol's original ownership check was *"re-read the issue and confirm the
latest claim comment is yours."* A session that claims second always finds its
own comment latest, so that check **passes while an earlier live claim sits
unread** — it could not detect the case it was written for. It failed twice in
one day:

| Issue | Cost |
|---|---|
| #11 | Two sessions built the same gate in full; one implementation discarded at rebase. ~25 min of duplicated work. |
| #5 | Two sessions produced **contradictory verdicts on the same question**. Reconciling them took DEC-023, DEC-024, and a third entry. |

The second is the expensive one: not wasted effort, but conflicting recorded
results.

## What it does

`audit_claims.py` answers the question the protocol actually needs — *does any
**unexpired** claim by another run-id exist?* — and, on collision, names the
winner by **earliest server-assigned comment id**. Ids are monotonic and
server-assigned; the timestamps in claim comments are agent-supplied and can be
skewed, so they are not used for ordering.

Verified against the real incidents:

```
#5  id 5737426522 (20260918-2329-zbmn) < id 5737450441 (20260918-2332-e7c4)
#11 id 5739467938 (20260919-0451-6421) < id 5739479618 (20260918-2332-e7c4)
```

## Usage

```bash
# live
python3 tooling/claims/audit_claims.py --fetch --run-id 20260919-1004-db83

# offline, from a pre-fetched bundle (the G-E7 cache pattern)
python3 tooling/claims/audit_claims.py --cache issues.json --run-id <id>

# the suite
python3 tooling/claims/tests/test_audit_claims.py
```

`--run-id` makes the report say whether *you* hold each contested claim.

## NOT a CI gate

It needs issue state, so it is **tier 1** by `TEST_VALIDATION_SPEC.md` § 3 and
must not be wired into `tooling/gates/run_all.py` — same reasoning as G-E7's
`SKIP` when issue state is unavailable. It reports; it does not gate.

## What it does not do

It detects and adjudicates; it does not **prevent**. Both sessions have already
claimed by the time it runs, so a collision still costs a round trip. The
structural fix — a genuine compare-and-swap — is **#27** (claim as a committed
`claims/<n>.claim` file, so `git push` rejects the loser immediately).

## Rejected approach, recorded so it is not re-proposed

**Distinct PATs do not help.** Measured: `GITHUB_TOKEN` and `ALL_REPOs_GH_TOKEN`
both resolve to login `allenpd728`, id `26507447`. Separate tokens on one account
change no API semantics — every comment, label change, and commit is authored by
the same user. Distinct *accounts* would improve attribution but still provide no
conditional write, so they would not prevent the race either.

## Fixtures

`tests/fixtures/` reproduces both real incidents plus the two negative
directions (a clean single claim, and a stale claim that § 1 makes reclaimable).
Each carries `_evaluate_at`, the moment it is meant to be judged — without it the
incident fixtures would read as stale against wall-clock `now` and the tests
would fail against their own data, which is exactly what the first version did.