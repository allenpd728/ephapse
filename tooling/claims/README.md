# tooling/claims

Claim tooling for the multi-agent protocol (`docs/MULTI_AGENT_WORKFLOW.md` § 4).

Two tools, and the split matters:

| Tool | Role |
|---|---|
| `claim.py` | **Prevention.** The authoritative lock: a git-ref compare-and-swap. |
| `audit_claims.py` | **Detection.** Finds collisions, names the winner by earliest comment id. |

## Why the lock is a git ref

GitHub labels are last-write-wins, and with one shared account there is no
conditional write on labels, assignees, or comments. So a label cannot prevent a
race. `git push` **is** a compare-and-swap — a non-fast-forward update is
rejected — and that is what `claim.py` uses:

```
claims/<issue>.claim     contents: <run-id> <UTC timestamp>
```

Claiming writes the file, commits, and pushes. The push that lands first owns
the issue; the loser is rejected in seconds having done no work. One file per
issue, so two *different* claims never touch the same path.

**The file is authoritative; the label and comment are visibility only.** Two
sources of truth for "who owns this" is the defect #27 removes.

## Why detection still exists

`audit_claims.py` covers what the lock cannot: legacy claims made before the
lock existed, scratch or offline repos, and the case where a session already
holds a label but no claim file. On collision it names the winner by **earliest
server-assigned comment id** — ids are monotonic and server-assigned, while the
timestamps in claim comments are agent-supplied and can be skewed, so timestamps
do not order. Verified against the real incidents:

```
#5  id 5737426522 (20260918-2329-zbmn) < id 5737450441 (20260918-2332-e7c4)
#11 id 5739467938 (20260919-0451-6421) < id 5739479618 (20260918-2332-e7c4)
```

## Usage

```bash
# take the lock (authoritative)
python3 tooling/claims/claim.py claim 27 20260919-1004-db83

# who holds it?
python3 tooling/claims/claim.py status 27 --run-id 20260919-1004-db83

# give it up (refuses a claim held by another run-id)
python3 tooling/claims/claim.py release 27 20260919-1004-db83

# collision audit, live or offline
python3 tooling/claims/audit_claims.py --fetch --run-id <id>
python3 tooling/claims/audit_claims.py --cache issues.json --run-id <id>
```

### Exit codes (the contract)

`claim.py` distinguishes "lost" from "broken":

| Code | Meaning |
|---|---|
| `0` | You hold the claim, or the operation succeeded |
| `2` | **You lost the race** — another run-id holds a live claim. Back off and pick other work. |
| `1` | A real error (bad args, git failure, dirty tree) |

Branch on `2`; do not parse the output. `2` is not a failure — losing a race is
the system working.

## Tests

```bash
python3 tooling/claims/tests/test_claim_cas.sh        # the race, end to end
python3 -m pytest tooling/claims/tests/ -q            # the audit
```

`test_claim_cas.sh` builds a scratch bare remote and two clones, then races them
at the same claim. It asserts exactly one winner, the loser's exit code is `2`,
the loser leaves no claim on the remote, and **the loser's working tree is
clean** — it genuinely did no work. Stable across repeated runs.

## NOT a CI gate

Both need git and/or network, so they are **tier 1** by
`TEST_VALIDATION_SPEC.md` § 3 and must not be wired into
`tooling/gates/run_all.py` — same reasoning as G-E7's `SKIP`. The CAS test is a
script, not a gate: it needs a scratch remote and is too slow for CI.

## Rejected approach, recorded so it is not re-proposed

**Distinct PATs do not help.** Measured: `GITHUB_TOKEN` and `ALL_REPOs_GH_TOKEN`
both resolve to login `philipdallen`, id `26507447`. Separate tokens on one account
change no API semantics — every comment, label change, and commit is authored by
the same user. Distinct *accounts* would improve attribution but still provide no
conditional write, so they would not prevent the race either. This is why the fix
is a git-ref CAS rather than a token or an assignee.