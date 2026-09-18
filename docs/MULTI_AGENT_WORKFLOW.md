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

Sizing rule: one task = completable in one agent run (well under an hour).
If a task can't be done in one run, decompose it before it becomes
`available`.

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
   `status:claimed` issues. For each, if the claim comment is older than
   **1 hour** with no activity since, the claim is void: remove
   `status:claimed`, restore the prior label, comment that the work was
   reclaimed (audit trail). A fresh claim carrying a run-id that is not
   yours belongs to a live sibling — leave it alone.

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

4. **Attempt the claim, then verify ownership.** Swap the item's current
   label to `status:claimed` **in one atomic edit** — self-assign, and post
   a claim comment (`claimed by <agent-name> run=<run-id> at <UTC
   timestamp>`). Then re-fetch the issue **and read the latest claim
   comment**: if its run-id is not yours, a sibling won — back off and pick
   a different item.

5. **Do the work; prove the done.** Commit directly to `dev` (no PR —
   review happens retrospectively on `dev`). Swap `status:claimed` →
   `status:done` and close the issue with a comment linking the commits.
   **Tasks with known-answer criteria close only when the done comment
   includes the exact command and its output** — a done claim without
   evidence is how full maps ship empty and nobody notices.

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
