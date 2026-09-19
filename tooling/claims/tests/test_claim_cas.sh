#!/usr/bin/env bash
# test_claim_cas.sh — proves the claim step is a real compare-and-swap (#27).
#
# The Definition of Done for #27 is: a deliberate concurrent race between two
# clones pushing the same claim, exactly one winner, no human in the loop.
#
# This builds a scratch bare remote on disk, two clones of it, and races them.
# It asserts:
#   1. exactly one claim wins,
#   2. the loser exits 2 (LOST, distinct from error),
#   3. the loser left NO claim file on the remote,
#   4. the loser's working tree is restored (it did no work),
#   5. a second claim by the winner is idempotent (exit 0),
#   6. a foreign, live claim is refused without touching the remote,
#   7. a STALE claim is reclaimable (the § 1 window still works),
#   8. release refuses to remove someone else's claim.
#
# Every assertion is also run in its failing direction where meaningful — a
# check that cannot fail is not a check (spec § 4).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLAIM_PY="$REPO_ROOT/tooling/claims/claim.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  PASS  $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL  $1"; }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }

# Well-formed run-ids (the tool validates the format).
RID_A_BASE="20260919-1004-aaaa"
RID_B_BASE="20260919-1004-bbbb"
RID_C_BASE="20260919-1004-cccc"

# ---------------------------------------------------------------- scratch remote
git init -q --bare "$TMP/remote.git"
# A bare repo's HEAD defaults to `master`; without this the clones check out
# nothing and every command fails with a confusing git error.
git --git-dir="$TMP/remote.git" symbolic-ref HEAD refs/heads/dev
git init -q "$TMP/seed"
cd "$TMP/seed"
git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
git branch -M dev
git remote add origin "$TMP/remote.git"
git push -q origin dev

# Run-ids are validated by the tool, so the fixtures must be well-formed:
# <YYYYMMDD-HHMM>-<4 alnum>. Using realistic ones also means the test exercises
# the same validation path a real session hits.
RID_A="$RID_A_BASE"; RID_B="$RID_B_BASE"; RID_C="$RID_C_BASE"; RID_STALE="20260919-0100-stal"

git clone -q "$TMP/remote.git" "$TMP/a"
git clone -q "$TMP/remote.git" "$TMP/b"

remote_claim() { git --git-dir="$TMP/remote.git" show "dev:claims/$1.claim" 2>/dev/null; }

echo "== 1. concurrent claim of the same issue =="
# Both clones start from the same base, so both will attempt to push a claim on
# issue 99. The first push wins the ref; the second is rejected and must lose.
( cd "$TMP/a" && python3 "$CLAIM_PY" --repo . claim 99 "$RID_A" >"$TMP/a.out" 2>&1; echo $? >"$TMP/a.rc" ) &
PA=$!
( cd "$TMP/b" && python3 "$CLAIM_PY" --repo . claim 99 "$RID_B" >"$TMP/b.out" 2>&1; echo $? >"$TMP/b.rc" ) &
PB=$!
wait $PA $PB

A_RC="$(cat "$TMP/a.rc")"; B_RC="$(cat "$TMP/b.rc")"
echo "    clone a exit=$A_RC ; clone b exit=$B_RC"

# Exactly one of the two must have exited 0.
WINNERS=0
[ "$A_RC" = "0" ] && WINNERS=$((WINNERS+1))
[ "$B_RC" = "0" ] && WINNERS=$((WINNERS+1))
check "exactly one claim won" "$WINNERS" "1"

if [ "$A_RC" = "0" ]; then LOSER_OUT="$TMP/b.out"; LOSER_RC="$B_RC"; LOSER_CLONE="$TMP/b"; WINNER_RUN="$RID_A"; LOSER_RUN="$RID_B"
else LOSER_OUT="$TMP/a.out"; LOSER_RC="$A_RC"; LOSER_CLONE="$TMP/a"; WINNER_RUN="$RID_B"; LOSER_RUN="$RID_A"; fi

check "loser exit code is 2 (LOST, not error)" "$LOSER_RC" "2"
if grep -q "LOST" "$LOSER_OUT"; then ok "loser output says LOST"; else bad "loser output says LOST"; fi

HEAD_RUN="$(remote_claim 99 | awk '{print $1}')"
check "remote holds exactly the winner's run-id" "$HEAD_RUN" "$WINNER_RUN"

# The loser must not have left its claim behind.
if grep -q "$LOSER_RUN" <<<"$(remote_claim 99)"; then
  bad "loser's run-id leaked into the remote claim"
else ok "loser's run-id absent from the remote claim"; fi

# The loser's tree must be clean: it did no work.
if [ -z "$(cd "$LOSER_CLONE" && git status --porcelain)" ]; then
  ok "loser's working tree restored (no work done)"
else bad "loser's working tree is dirty"; fi

echo
echo "== 2. winner re-claims idempotently =="
if [ "$A_RC" = "0" ]; then WINNER_CLONE="$TMP/a"; else WINNER_CLONE="$TMP/b"; fi
( cd "$WINNER_CLONE" && python3 "$CLAIM_PY" --repo . claim 99 "$WINNER_RUN" >"$TMP/idem.out" 2>&1 )
check "idempotent re-claim exits 0" "$?" "0"
grep -qi "already claimed by me" "$TMP/idem.out" && ok "idempotent re-claim says so" || bad "idempotent re-claim message"

echo
echo "== 3. a live foreign claim is refused without touching the remote =="
BEFORE="$(remote_claim 99)"
( cd "$LOSER_CLONE" && python3 "$CLAIM_PY" --repo . claim 99 "$RID_C" >"$TMP/foreign.out" 2>&1 )
RC=$?
check "foreign live claim refused with exit 2" "$RC" "2"
check "remote unchanged by the refused attempt" "$(remote_claim 99)" "$BEFORE"

echo
echo "== 4. a STALE claim is reclaimable (§ 1 window still works) =="
# Write a claim dated two hours ago directly onto the remote, then have the
# reclaimer FETCH it — without the fetch the clone still sees the live claim
# from step 1 and correctly refuses. (The first version of this test omitted the
# fetch and failed against its own setup, not against the tool.)
cd "$TMP/seed"
git fetch -q origin dev && git reset -q --hard origin/dev
mkdir -p claims
OLD_TS="$(date -u -d '2 hours ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-2H +%Y-%m-%dT%H:%M:%SZ)"
echo "$RID_STALE $OLD_TS" > claims/99.claim
git add -A
git -c user.name=t -c user.email=t@t commit -q -m "stale claim for 99"
git push -q origin dev
git --git-dir="$TMP/remote.git" show dev:claims/99.claim | head -1

( cd "$LOSER_CLONE" && git fetch -q origin dev && git reset -q --hard origin/dev \
  && python3 "$CLAIM_PY" --repo . claim 99 "$RID_C" >"$TMP/reclaim.out" 2>&1 )
RC=$?
cat "$TMP/reclaim.out" | sed 's/^/    /'
check "stale claim reclaimed with exit 0" "$RC" "0"
check "reclaimer now holds the claim" "$(remote_claim 99 | awk '{print $1}')" "$RID_C"

echo
echo "== 5. release refuses another run's claim =="
( cd "$LOSER_CLONE" && python3 "$CLAIM_PY" --repo . release 99 "20260919-1004-zzzz" >"$TMP/rel.out" 2>&1 )
RC=$?
check "releasing another run's claim exits 1" "$RC" "1"
check "claim still present after refused release" "$(remote_claim 99 | awk '{print $1}')" "$RID_C"

echo
echo "== 6. status reports ownership =="
( cd "$LOSER_CLONE" && python3 "$CLAIM_PY" --repo . status 99 2>&1 | tee "$TMP/status.out" >/dev/null )
grep -q "$RID_C" "$TMP/status.out" && ok "status names the owner" || bad "status names the owner"
grep -q "LIVE" "$TMP/status.out" && ok "status marks it LIVE" || bad "status marks it LIVE"

echo
echo "=============================================================="
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
echo "claim CAS verified: one winner, loser stopped before doing work."
exit 0