# Multi-agent task protocol

Ported from Maith's `docs/MULTI_AGENT_WORKFLOW.md` (itself ported from
PleaNP), which battle-tested it under a shared GitHub identity. Ephapse
starts with the lesson already applied rather than relearning it.

> **Why this exists.** Maith consolidated 21 parallel branches into one
> `dev` in DEC-036 precisely because it lacked this protocol: without
> run-ids, atomic claims, dependency lineages, and sweeps, parallel agents
> double-claim, strand dependents, and lose work at rebase. The branch
> sprawl *was* the symptom. This file is the fix.

> **System of record:** the issue queue plus `git log origin/dev`. Status
> tables in docs are caches updated by sweeps and may lag — check the queue
> and `dev` history before concluding work is undone.

## Run-ids

Every agent session generates a **run-id** at session start:
`<YYYYMMDD-HHMM>-<4 random alphanumerics>` (e.g. `20260918-1430-a1b2`). It
appears in every claim comment, done comment, and blocker the session
writes. It is the only way to distinguish claims under a shared GitHub
identity — all agents authenticate as the same account, so labels,
assignees, and author fields cannot tell claims apart. Without run-ids the
re-fetch check in §Claiming has no teeth.

## Credentials — which token goes where

Two token-shaped credentials are available in a session. Both belong to the
same account (`philipdallen`), so neither changes *who* a push is attributed to;
the difference is **lifetime**.

| Credential | Kind | Use it for | Notes |
|---|---|---|---|
| `$GITHUB_TOKEN` | session token (`ghu_…`) | the default for git and `gh` work | **can expire mid-session** (observed) — see below |
| `$ALL_REPOs_GH_TOKEN` | scoped PAT (`ghp_…`) | the fallback when `$GITHUB_TOKEN` returns 401 | durable; outlives the session |

**The rule: use `$GITHUB_TOKEN` by default, wire it through a
`credential.helper`, and fall back to `$ALL_REPOs_GH_TOKEN` the moment git or
`gh` reports a 401. Never write any token into the remote URL.**

Why this is written down: the clone URL as provisioned embeds a token
(`https://<token>@github.com/philipdallen/ephapse.git`). With no
`credential.helper` configured, git falls through to an interactive password
prompt — and an agent session has no one to answer it, so the command **hangs
rather than failing**, silently stranding committed work. Two separate tokens
were observed to return 401 during a single session: the embedded URL token,
and later `$GITHUB_TOKEN` itself (it authenticated fine at session start, then
failed mid-session). The expiry is real, not hypothetical, and it happens to
the session token too.

**Set this once at the start of every session** (idempotent; keeps the token
out of the URL and re-reads the live value from the environment on each use):

```bash
git remote set-url origin https://github.com/philipdallen/ephapse.git
git config credential.helper \
  '!f() { echo "username=x-access-token"; echo "password=${GITHUB_TOKEN}"; }; f'
```

Then a plain `git push origin dev` / `git pull --rebase origin dev` works, and
`gh issue …` / `gh pr …` work because the CLI already reads `$GITHUB_TOKEN`.

**If you get a 401** (`Invalid username or token`, or `Bad credentials` from
`gh`), `$GITHUB_TOKEN` is stale. Switch that one command to the fallback rather
than stopping:

```bash
# git: push with the durable token in the URL for this one command
GIT_TERMINAL_PROMPT=0 git push \
  "https://x-access-token:${ALL_REPOs_GH_TOKEN}@github.com/philipdallen/ephapse.git" HEAD:dev

# gh: GH_TOKEN takes precedence over GITHUB_TOKEN
GH_TOKEN="$ALL_REPOs_GH_TOKEN" gh issue view <n> --repo philipdallen/ephapse
```

Then report the expiry, because a session that hit it once will hit it again.

**Non-interactive guard.** Never let a git command block on a prompt:

```bash
GIT_TERMINAL_PROMPT=0 git push origin dev   # exits non-zero instead of hanging
```

A push that hangs on a password prompt is the failure mode to design out — it
silently strands committed work on the local branch, which is exactly what
"never stop on local" forbids (§1c, §5).

**Testing a credential: do not trust `git ls-remote`.** `philipdallen/ephapse` is
**public**, so `git ls-remote` succeeds anonymously and *cannot fail* — it
reports "OK" for a token that is already dead. A check that cannot fail is not
a check (the repo's own rule). Test authentication with an authenticated API
call instead:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" \
  https://api.github.com/repos/philipdallen/ephapse   # 200 = valid, 401 = stale
```

## Task states (labels)

| Label | Meaning |
|---|---|
| `status:available` | Ready to be claimed. All blockers are `done`. |
| `status:claimed` | An agent has claimed it. Claim comment is the heartbeat. |
| `status:done` | Work committed to `dev`. The human reviews on `dev` at leisure; anything needing changes spawns a follow-up task. |
| `status:blocked-needs-input` | Agent could not start or finish; needs human input. |
| `priority:high` | Jumps the work queue (default order is lowest issue number). |
| `needs-review` | Requires human or integrity review before acceptance. |

## Task definition

Each issue contains:

- **Summary** — what to build, in one paragraph
- **Definition of done** — the observable end state (files written, numbers logged, evidence)
- **Context** — links to spec sections, prior art, or related tasks
- **Blocked by** — native GitHub issue-blocking relationships forming the lineage

Sizing rule: one task = completable in **one agent run**. Note what a run now
means: scheduled OpenHands automation runs are hard-capped at **30 minutes
wall-clock**, and a run killed at the cap loses everything not already pushed.
Recon, cloning, and gates consume a large share of that, so **size a task for 20
minutes of work or less**. If a task can't be done in one run, decompose it
before it becomes `available`.

**Planning and research are legitimate tasks, not overhead.** When an issue is
too large or too uncertain to implement in a single run, the right decomposition
is usually a research or planning issue *first* — an investigation whose
Definition of Done is a written finding, a decision record, or a freshly filed
set of smaller issues. A 20-minute run that produces a well-scoped plan for the
next five issues is a good outcome, not a wasted run. Prefer a short, honest
research task over a half-finished implementation.

## Automated runs (bounded, 30-minute cap)

Some `status:available` work is picked up by a scheduled automation rather than
an attended agent. Those runs are hard-capped at **30 minutes** — the platform
rejects any longer timeout — and a run killed at the cap loses everything not
already pushed to GitHub. Three rules follow. Attended agents should follow them
too, because the loss mode is identical.

1. **Push constantly.** Commit and push each coherent step the moment it exists.
   Unpushed work dies with the sandbox; a pushed partial commit is a resumable
   checkpoint. Do not accumulate local edits and push once at the end.
2. **Checkpoint rather than overrun.** If a run cannot finish, push what is
   complete, then post a comment beginning `<!-- oh-agent -->` `CHECKPOINT`
   naming the run-id, the pushed SHAs, what is done, what remains, and the next
   concrete step. Release the claim (restore `status:available`) so the next run
   can pick it up immediately. A run that claims an issue whose last comment is a
   `CHECKPOINT` should **continue that work, not re-derive it**. Never use
   `status:blocked-needs-input` for mere time exhaustion — that label means a
   human decision is required.
3. **Mark every agent comment with `<!-- oh-agent -->`.** Claim comments,
   progress notes, checkpoints, and closing comments alike. This is a
   machine-readable marker, not decoration: an automation watches issue comments
   and would otherwise wake on agent output and spend an entire run deciding to
   do nothing. Omitting it costs a run.

## Writing for the human reviewer

Most issues are resolved without the human reading anything, but every so often
one stops and waits for a person. When that happens, write for someone who has
not read the thread. Two conventions make the human's queue scannable without
anyone spending an agent run to summarise it.

**1. `NEEDS:` — open every `status:blocked-needs-input` comment with it.**

The comment's **first line** must be a single self-contained statement of the one
thing a human must decide or provide:

```
NEEDS: choose whether the detector statistic is re-derived per-rung or once
globally — DEC-030 implies per-rung but the ledger records a single value.
```

Rules for that line:

- One decision or one piece of information. Not two.
- Self-contained: it must make sense to a reader who has read nothing else.
  A pointer ("see above", "as discussed") is not a `NEEDS:` line.
- Say what you already know and where the ambiguity is, so the human can answer
  in one message rather than asking a clarifying question.

This is what makes the whole blocker queue readable in one command — see
`needs-audit.sh` in this repo's tooling, or the recipe in
`automations/HUMAN_REVIEW.md`. A blocked comment without a `NEEDS:` line is
considered incomplete.

**2. "Not in my lane" — one line on your final comment, when you saw something.**

When a run finishes, if while working it noticed something outside its own task
that it did **not** act on, append one line:

```
Not in my lane: ephapse #21 needs a dependency decision; PleaNP #96 looks like
a duplicate of #77.
```

Only if true — never manufacture items to fill it. This costs nothing beyond a
line on a comment already being written, and it makes the human's periodic scan
surface cross-cutting problems that no single task owns. It is **not** a sweep:
do not go looking for things to report, and never let it extend a run.

**One task = one signal.** Every task's Definition of Done names a single
observable check that turns green only when the task is genuinely finished.
That check **must be demonstrably able to fail** — a check that cannot fail
is not a check.

**Ephapse-specific:** for any experiment task, the Definition of Done must
name the **null model, the multiplicity correction, and the confound
checklist** used, fixed *before* the run. An experiment whose null was
chosen after seeing the data is not a result.

## Dependencies

Dependencies are expressed as GitHub "blocked by" relationships, forming
lineages. A task becomes `available` only when **every** issue blocking it
is `status:done`. Within a lineage, only one task is ever available at a
time.

## Claiming protocol

The claim lock applies to **any issue an agent is actively working**.

**One claim per agent at a time.** An agent holds **exactly one**
`status:claimed` label across the tracker. Finish the claimed item (commit +
close + unblock dependents) before claiming the next.

1. **Sweep stale claims.** Before selecting work, list all
   `status:claimed` issues. For each, a claim is void when **both** hold:

   - the authoritative lock (`claims/<issue>.claim`, § 4a) is older than
     **1 hour**, and
   - there has been **no activity by that run-id since** — no claim comment, no
     commit, no comment mentioning `run=<id>`.

   Then remove `status:claimed`, release the claim file, restore the prior
   label, and comment that the work was reclaimed (audit trail). A fresh claim
   carrying a run-id that is not yours belongs to a live sibling — leave it
   alone.

   **Measure age from the server, never from the typed timestamp.**
   `claims/<n>.claim` carries a timestamp written by the claiming agent, and
   comment bodies carry an `at <ts>` clause of the same kind. Both are
   claimant-controlled and have been wrong; GitHub's `created_at` is
   authoritative. This is the same rule § 4c applies to *ordering*, applied to
   *liveness* — DEC-031.

   **The heartbeat works, and is what keeps a long-running claim.** The
   Ephapse caveat below tells a session waiting on a remote queue to post a
   heartbeat carrying its run-id rather than lose the claim. Any comment
   mentioning `run=<id>` counts as activity for that run, so a heartbeat does
   extend liveness — that path is implemented in `claim.py status` and
   `audit_claims.py` and covered by tests (#35).

   ```
   python3 tooling/claims/claim.py status <issue> --run-id <run-id>
   python3 tooling/claims/audit_claims.py --fetch --run-id <run-id>
   ```

   **Ephapse caveat:** remote probing (NDIF queue waits) and cold model
   downloads can legitimately exceed an hour without producing a commit.
   If you are waiting on a remote queue, post a heartbeat comment with your
   run-id rather than losing the claim to the sweep.

1a. **Sweep protocol violations.** An issue carrying two status labels at
   once is in an illegal state. The sweep repairs it: the *older* label
   wins (`blocked-needs-input` outranks `claimed`), the extra label is
   removed, and a comment records the repair.

1b. **Docs coherence sweep.** Check that `README.md`, `docs/AGENT_HANDOFF.md`,
   `docs/decisions/LOG.md`, and the relevant experiment writeup agree. If a
   recently-closed task changed the design or the plan, the sibling docs
   must reflect it in the same session — a stale doc is a process failure
   on par with a stale claim.

1c. **A sweep is not finished until it is pushed.** Any sweep that changed
   the tracker or the tree — reclaimed a claim (1), repaired a label (1a),
   or fixed a doc (1b) — **must end with the change committed and pushed to
   `origin/dev`**, and the sweep's results comment must name the commit it
   pushed. A sweep that stops at the local tree has not happened: the next
   session sees the unchanged remote and repeats the same work, and if the
   sweep only changed labels it leaves the tree and the tracker inconsistent.

   This is the same rule as §5 (work commits directly to `dev`) applied to
   sweeps. It applies with two caveats:

   - **Tracker-only sweeps** (label changes, reclaim comments) push nothing
     — there is no tree change — but they are still not finished until the
     comment recording them is posted, and the sweep comment says so
     explicitly.
   - **A sweep that finds nothing to change** is a valid, complete outcome.
     Say that, with the evidence checked (e.g. the `gh issue list` output),
     rather than leaving the absence of a comment ambiguous.

   Concretely: if `git status` is dirty when the sweep ends, the sweep is
   unfinished. Commit, `git pull --rebase origin dev`, push, and only then
   write the sweep comment. See §Credentials for the push setup — and never
   leave work sitting on the local branch behind a credentials prompt.

2. **Pick work.** Any `status:available` issue the agent can start. Default
   order: lowest issue number first; `priority:high` jumps the queue.
   Before concluding any work item is undone, check `git log origin/dev`
   and the issue queue — docs tables lag.

2a. **Filing is not atomic — search, file, search again.** Before filing a
   new task, search open issues for its slug. After filing, search again:
   if a twin with a **lower issue number** now exists, close yours as
   duplicate.

3. **When no task is available, fall through in priority order:**
   - **(a) Open blockers.** Work through `status:blocked-needs-input`
     issues one at a time; if resolvable, close the blocker and return the
     task to `status:available`.
   - **(b) Open PRs with unaddressed review comments.** Address each, reply
     to every thread with the fixing commit, mark threads resolved.
   - Only when tasks, PR comments, and blockers are exhausted is the queue
     empty and the session done.

4. **Take the claim — and make it a compare-and-swap, not a convention.**

   **Step 4a — the authoritative lock (git ref).** Claim via
   `tooling/claims/claim.py`, which commits `claims/<issue>.claim` containing
   your run-id and pushes it:

   ```
   python3 tooling/claims/claim.py claim <issue> <run-id>
   ```

   `git push` **is** a compare-and-swap on the remote ref: a non-fast-forward
   update is rejected. **The push that lands first owns the issue.** The loser
   is rejected in seconds and exits `2` having done no work.

   Exit codes are the contract: `0` = you hold it, `2` = you **lost the race**
   (back off, pick other work), `1` = a real error. Branch on `2`; do not parse
   the output.

   **The claim file is authoritative. The label and comment are visibility
   only.** This matters — two sources of truth for "who owns this" is the defect
   #27 exists to remove. If the file and the label disagree, the file wins.

   **Step 4b — the label and comment (visibility).** Swap the item's label to
   `status:claimed` **in one atomic edit**, self-assign, and post a claim
   comment (`claimed by <agent-name> run=<run-id> at <UTC timestamp>`). Never
   leave two status labels on one issue (§ 1a) — remove `status:available` in
   the same edit that adds `status:claimed`.

   **Step 4c — verify ownership against *every* claim, not the latest one.**
   *Does any **unexpired** claim by another run-id exist?* If yes, a sibling
   holds the item — back off. **Do not** merely read the latest claim comment
   and confirm it is yours: a session that claims second always finds its own
   comment latest, so that check passes while an earlier live claim sits
   unread. That was the original wording, and it failed twice in one day
   (#5, #11).

   **Tiebreak when the git-ref CAS is unavailable** (scratch repo, offline, or
   a legacy claim that predates the lock): the winner is the claim with the
   **earliest server-assigned comment id** — not the earliest timestamp string,
   which is agent-supplied and can be skewed or wrong. Comment ids are monotonic
   and assigned by GitHub, so both sessions derive the same answer without a
   human. `tooling/claims/audit_claims.py` reports collisions and names the
   winner. If you hold the later id, release your claim and pick another item.

   The owner is whoever holds the earliest *unexpired* lock; either side may
   compute it. **The loser must stop work, not race to finish** — two sessions
   completing the same item produces contradictory results, not redundancy:
   #5's duplicate claims yielded opposite verdicts on the same question and
   cost DEC-023, DEC-024, and a third entry to reconcile.

   **Release** when a claim must be dropped (blocked, abandoned, or lost by
   tiebreak): `python3 tooling/claims/claim.py release <issue> <run-id>`. It
   refuses to release a claim held by another run-id.

5. **Do the work; prove the done.** Commit directly to `dev` (no PR —
   review happens retrospectively on `dev`). Swap `status:claimed` →
   `status:done` and close the issue with a comment linking the commits.
   **Tasks with known-answer criteria close only when the done comment
   includes the exact command and its output** — a done claim without
   evidence is how full maps ship empty and nobody notices.

   **Done means pushed, not committed.** A task is not done while its
   commits exist only on the local branch; the reviewer reads `dev` on the
   remote. Before writing the done comment, confirm the remote actually has
   the commit:

   ```bash
   git push origin dev && git status --porcelain    # must print nothing
   ```

   A `git push` that hangs on a password prompt has failed even though it
   did not exit — set the credential helper in §Credentials, and use
   `GIT_TERMINAL_PROMPT=0` so a credential problem errors out instead of
   silently stranding the work.

   **Concurrent-work rules** (agents run in parallel against `dev`):
   - Pull before you start, and again before you push.
   - On push rejection (non-fast-forward): `git pull --rebase origin dev`,
     resolve conflicts, push again.
   - **Rebase revealed a sibling landed the same work?** Compare the two
     implementations: if yours adds nothing, drop it; if yours genuinely
     extends it, merge the two in the rebase. Never push a second copy.
   - **Never force-push to `dev`** — it can destroy a sibling's committed
     work.
   - A rebase conflict you cannot resolve confidently is a blocker — file it.

6. **Record the experiment.** Every experiment — not just every code change
   — gets an issue and a logged result in `findings.jsonl`, positive or
   negative. A null result is informative and is recorded with the same
   care as a positive one. This mirrors Maith's ledger discipline.

7. **Unblock dependents.** Before finishing, check the issues that listed
   this task under "Blocked by". For each whose blockers are all now
   `status:done`, label it `status:available` and comment that it is
   unblocked. Dependent tasks do not become visible to the queue on their own.

8. **Iterate.** If review later finds the work lacking, write a new task
   rather than reopening the old one.

## Gates (done-evidence)

Maith has a kernel oracle; Ephapse does not. That is the central structural
difference, and it means done-evidence here has to be **reproducible
numbers** rather than a proof checker.

A done comment for an experiment task must include:

- The exact command run.
- The model, layer, feature IDs, and inputs involved.
- The null model and multiplicity correction used.
- The confound checklist results (which confounds were checked, and which
  fired).
- The raw result, including nulls.

A finding with no confound checklist is not evidence. A finding whose
significance is not corrected for multiplicity across the feature × pair
matrix is not evidence. State plainly in any writeup that **unusual
activation is not evidence of correctness** — hallucination-like generation
and genuine insight look identical from inside activation statistics alone.

Nothing produced in this repo is described as a "new mathematical result."
That language belongs to Maith's gate-3-survivor artifacts, once earned there.
