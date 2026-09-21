# The Auditor — daily repo health & drift automation

A scheduled, read-only pass over this repo that surfaces drift, bugs, and
architecture issues for the human Orchestrator to triage. **It never takes
action on its own.** Every finding is a proposal held for review.

## What it is not

- **Not an agent.** It is a deterministic script (`tooling/auditor.py`). No LLM,
  no token cost per run, nothing to hallucinate. Every finding is a mechanical
  fact about the tree. This is a deliberate choice: the checks below are all
  decidable by inspection, and a deterministic run is safe to re-trigger.
  (The one network call it makes — the OSV.dev advisory lookup — is a single
  read-only `POST` to a public API. It sends package names and versions from
  `requirements.txt` and nothing else, and if it cannot run, that is *reported*
  rather than silently skipped.)
- **Not a fixer.** It never edits code, merges, closes, or resolves anything.
- **Not a second tracker.** It opens proposals and a digest; it does not move
  work through the pipeline.
- **Not connected to the dashboard.** It writes one line to this repo's own
  `status_log.jsonl` (see below). It never touches the HuB repo or any other.

## Trigger and idempotency

Runs from the `auditor` GitHub Actions workflow in this repo, on a daily cron,
plus `workflow_dispatch` for a manual run.

Before any analysis it reads the last-audited commit SHA from
`status/auditor_state.json` (the `status/` directory already holds this repo's TRL
file, so no new state location was invented; the checkpoint file itself is
created on the first successful run). **If `HEAD` has not moved, it
exits without creating anything** — no issue, no comment, no status line.

- On success the checkpoint advances to the new `HEAD`.
- On failure it does **not** advance, so the next run retries the same range
  rather than silently skipping it.
- Re-triggering manually is safe: findings are deduplicated against open issues
  by a stable signature (below), so a second run adds information to the
  existing issue instead of opening a twin.

## What it checks

### High level — architecture and drift

- **`dangling-doc-ref`** — backticked file paths in `docs/` that resolve nowhere.
  A reference attributed to a sibling repo, a wildcard/placeholder, or a bare
  basename that exists somewhere in the tree is *not* reported; those are
  citations or loose prose references, not drift.
- **`doc-count-drift`** — docs that cite contradictory counts of the same thing
  ("N gates", "N checks", "N ids"). This is the class the spec calls out
  explicitly. Only a disagreement *between* documents is reported; the check does
  not attempt to derive which number is correct, because for this repo family the
  count is often genuinely tiered.
- **`status-log-contract`** — this repo's own `status_log.jsonl` must stay
  parseable for the dashboard that reads it.
- **`stale-owner-ref`** — references to a *retired* account/repo slug surviving
  outside the frozen record. The project's GitHub account has been renamed, and a
  clone URL, `--repo` example, or prose sentence still naming the previous slug is
  a live contradiction that tells a reader or an agent to use an address that no
  longer resolves. The retired slug list lives in `RETIRED_OWNER_SLUGS` at the top
  of `tooling/auditor.py` — it is not repeated here, because this file is itself
  scanned (see below). Frozen logs (`docs/decisions/`, `docs/history/`) are
  excluded by design: they record the slug as it was at the time, and rewriting
  them would make them false. Only slugs *known* to have been retired are listed,
  because flagging "any slug that is not the current owner" would fire on the
  third-party projects these docs legitimately cite.

### Security

- **`committed-secret`** — credential-shaped strings in files git tracks.
  High-confidence shapes only (private-key blocks, AWS access-key ids, and the
  vendor-prefixed token formats `ghp_`/`github_pat_`/`xox`/`AIza`/`sk-`/`hf_`). A
  scanner that fires on prose, or on the example keys vendored into a lockfile, is
  a scanner a human learns to skip. The matched value is **never** reproduced in
  the issue: these issues are public, and echoing a live credential would complete
  the leak the check exists to catch. The finding says rotate first, because
  deleting the line does not remove it from history.
- **`workflow-hardening`** — GitHub Actions workflows that are under-hardened,
  by three mechanical rules:
  - **no top-level `permissions:`** — the job runs with the repository's *default*
    token scope, so every step (including one executing a third-party action)
    inherits whatever that is. A step-scoped `permissions:` does not satisfy this;
    it is the job-level default that decides what the token may do.
  - **untrusted interpolation into `run:`** — a PR title, branch name, or workflow
    input substituted directly into a shell command is code execution. Only `run:`
    blocks are inspected: `${{ ... }}` in an `env:` or `with:` value is the
    *remedy*, so flagging it would punish the correct pattern and bury the real
    finding.
  - **`checkout` of a PR head ref** — the `pull_request_target` anti-pattern, where
    a privileged workflow executes the contributor's code with the base repo's
    credentials.
- **`dependency-advisory`** — known advisories against `requirements.txt` pins,
  via the public [OSV.dev](https://osv.dev) batch API. Chosen over the GitHub
  advisory APIs because those are entitlement-gated (they return `403` for these
  repos), while OSV needs no auth and no GitHub Advanced Security. Three outcomes:
  advisories found → one finding; queried and clean → silent; **query unavailable
  → a reported Catch-all finding**, because an unavailable check and a clean repo
  must not look the same.

### Detailed level — bugs and hygiene

- **`gate-health`** — runs this repo's own gate/test runner and reports a
  non-zero exit. The runner is detected, not assumed, because inventing a
  command that does not exist would make this check silently vacuous. If no known
  runner is found, that is reported as a catch-all finding rather than treated as
  a pass.
- **`stale-todo`** — `TODO`/`FIXME`/`XXX` markers older than 120 days, aged by
  `git blame`. Capped so a legacy backlog produces a readable digest rather than
  a wall.
- **`committed-artifact`** — build/OS cruft that is *tracked by git*
  (`.DS_Store`, `__pycache__`, `*.pyc`, editor backups). Untracked cruft from a
  local test run is deliberately ignored: it is noise, and reporting it would
  make this check cry wolf.

### Catch-all

Anything that fits none of the above, plus a `check-crashed` finding when a check
itself raises. A crashed check is reported rather than swallowed, because a check
that silently stops running looks identical to a clean repo. The same rule covers
the advisory lookup: if OSV.dev is unreachable, that is a Catch-all finding, not
an empty result. A check that *cannot provide an answer* and a check whose answer
is *"nothing wrong"* are different states, and the audit refuses to conflate them.

## The `on-hold` states, and how to approve a proposal

Three labels drive the held-for-review model. None of them is a status label this
repo's task protocol treats as claimable.

| Label | Meaning |
|---|---|
| `auditor:proposed` | The Auditor proposes a new task. |
| `auditor:revise` | The Auditor proposes replacing or correcting an existing open task. |
| `on-hold` | Held for human review. **Not claimable by agents.** |

**To approve a proposal and move it into the real pipeline**, the human:

1. Reads the issue and decides whether the finding is worth acting on.
2. Removes `on-hold` and removes `auditor:proposed`.
3. Adds whatever status label this repo's protocol uses to make work claimable
   (the `status:available` label described in this repo's own workflow doc).

The Auditor **never** adds that last label. Making work claimable is the human's
decision alone, and it is the single most important boundary in this design.

To reject a proposal, close the issue. The Auditor does not reopen closed issues;
the dedup check considers only *open* issues, so a rejection is respected.

## Dedup

Each finding carries a stable signature of the form
`[auditor:<check>] <subject>` — for example `[auditor:dangling-doc-ref] docs/x.md`.
That signature is the issue *title*. Before opening anything, the Auditor looks
for an open issue whose title or body already contains the signature:

- **found** → comment with the new observation; never open a duplicate.
- **not found** → open one new issue.

Because the signature is derived from the check id and the subject rather than
the finding body, re-wording a finding does not create a second issue.

## Daily digest

One issue per day, titled `Auditor digest — YYYY-MM-DD`, labeled `on-hold`. It
contains the commit range covered, findings bucketed by category (Architecture &
drift, Security, Bugs & hygiene, Catch-all), and links to every issue opened or
commented on in that run. If a digest for the day already exists, the new run
comments on it rather than opening a second.

## What it writes to `status_log.jsonl`

The shared dashboard contract is documented in HuB's `PM_STATUS_FRAMEWORK`
document (the HuB repo, not this one). After a successful run the Auditor
appends **one** line:

```json
{"timestamp":"2026-01-01T00:00:00Z","trl":{...},"flow":{...},"notes":"audit 2026-01-01 @ abc1234: 2 proposed, 0 revise"}
```

- **No new field was added.** The audit summary fits the existing `notes` field,
  which the schema already defines as free text and which the dashboard already
  renders in its snapshot log. The spec asked for counts of new `on-hold` items
  and `auditor:revise` proposals and the covered SHA; all three are carried in
  that one string.
- **`trl` and `flow` are copied forward verbatim** from the previous line. This is
  load-bearing, not tidiness: the dashboard reads those values from the *last*
  entry, so an audit snapshot that omitted `trl` would blank the TRL panel for
  every viewer until the next scheduled sweep. The tests pin this behaviour.

## Hard constraints (enforced, and tested)

- Never merge, close, or auto-resolve anything.
- Never add a claimable-status label — only the human does that, after review.
- Never edit code. The only files it writes are `status/auditor_state.json` and
  `status_log.jsonl`.
- Never touch the HuB repo or any other repo.
- The analysis is read-only and takes no lock, so it cannot race a concurrent
  agent; the only shared state it mutates is appended under a single write.

## Running it by hand

```bash
python3 tooling/auditor.py --repo philipdallen/<repo> --dry-run   # print findings, write nothing
python3 tooling/auditor.py --repo philipdallen/<repo> --json      # machine-readable, write nothing
python3 tooling/auditor.py --repo philipdallen/<repo>             # do a real run
python3 tooling/auditor.py --repo philipdallen/<repo> --force     # ignore the checkpoint
```

`--json` emits the same findings as a structured object on stdout
(`{sha, audited_at, commits, finding_count, findings[]}`, each finding carrying
its stable `signature`). Like `--dry-run` it is strictly read-only — no issues,
no labels, no status line, and no checkpoint advance — so it is always safe to
call from a tool, a test, or an agent. It exists so the audit output can be
*consumed* rather than only read: a wrapper can diff one run against the next
without parsing the human-facing digest.

Tests are offline and stdlib-only:

```bash
python3 tooling/tests/test_auditor.py
```

## Which parts of the spec were interpreted

Recorded rather than decided silently:

- **"Architecture smells" are only partially covered.** Growing coupling and
  "a module doing more than its job" need judgement a deterministic script does
  not have. The checks cover the *mechanically checkable* subset — dangling refs,
  contradictory counts, a runner that fails, a check that cannot fail. The
  subjective layer is left to human review rather than faked with heuristics that
  would produce noise.
- **"A gate that can't fail"** is not detected directly. Detecting it properly
  requires mutating the gate and observing silence, which is invasive and outside
  a read-only auditor's remit. The digest note records the indirect signal
  instead: a gate count that does not match the number of executables.
- **TODO/FIXME age threshold** (120 days) and the report cap (8) were chosen, not
  specified. Both are constants at the top of `tooling/auditor.py`.
- **Checkpoint location** — `status/auditor_state.json`, because `status/` already
  exists in this repo family and the spec forbade inventing a new location.
- **`auditor:revise` is defined but not yet produced** by a built-in check. The
  label, the comment-on-existing-issue path, and the digest wiring all exist and
  are exercised; no check currently emits a revision proposal, because doing so
  reliably needs an LLM's judgement about whether an existing issue is *stale or
  wrong*. It is implemented so that adding such a check is a one-line registry
  change, and left honestly unused rather than filled with a guess.

### Interpretations specific to the security and consistency checks

- **"Security review" means the free, entitlement-independent layer.** Two classes
  of tooling were available and only one was usable here. GitHub's own code
  scanning, secret scanning, and Dependabot *alert* APIs are gated behind GitHub
  Advanced Security and returned `403` for these repos, so relying on them would
  have produced a check that silently never ran. The checks instead do the work
  they can do deterministically and locally (workflow hardening, credential
  patterns) and use a *public* advisory source (OSV.dev) for the one question that
  genuinely needs an external database.
- **Static analysis tooling (CodeQL, Semgrep) was deliberately not adopted.** It is
  a real capability, but it is heavy, needs per-repo workflow changes, and its
  output is a second finding stream to triage. That is a separate decision from
  this component, and the honest place to make it is on its own merits rather than
  folded into a daily audit. The same reasoning applies to AI/LLM PR reviewers:
  they are the right tool for the subjective layer this design explicitly declines
  to fake, and they should be adopted as their own component if wanted, not
  smuggled in as a "check".
- **`RETIRED_OWNER_SLUGS` is a hardcoded list, not a derived one.** The check can
  only know a slug *was* an address by being told. Deriving it ("flag anything that
  is not the current owner") was rejected because it fires on every third-party
  project these docs legitimately cite. When an account or repo is next renamed,
  add the old slug here — that is a one-line change, and the alternative is a check
  that trades precision for the illusion of automation.
- **The secret scan is a backstop, not a substitute for the platform feature.**
  It reads tracked files only, skips files over 2 MB and known lockfiles, and does
  not walk commit history the way a purpose-built tool does. Its value is that it
  runs with no entitlement; its limit is recorded here so nobody reads a clean
  result as "no secret has ever been committed".
- **The dependency check sends only names and versions.** It does not upload code
  or the lockfile, and it fails *loudly* (a Catch-all finding) rather than quietly
  when the API is unreachable. If a policy decision is ever made that no outbound
  request is acceptable from the auditor, `check_dependency_advisories` is one
  registry line to remove and the rest of the audit is unaffected.
- **The OSV query is dependency-injected (`query=osv_query`)** purely so the tests
  can exercise all three branches — advisories, clean, unavailable — without
  network access. The production default is the real API.