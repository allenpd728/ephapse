# HuB status log (`status_log.jsonl`)

This repo publishes one append-only status snapshot per sweep. The HuB
dashboard (https://allenpd728.github.io/HuB/) fetches
`status_log.jsonl` from this repo's `dev` branch and renders it. This repo is
the writer; HuB only reads.

## What writes it

`tooling/hub_sweep.py` — see its module docstring for the design rules. It computes a
snapshot from this repo's own GitHub issues at run time, so the log cannot
drift from the tracker the way a hand-maintained table does. Nothing in it is
hardcoded.

```bash
python3 tooling/hub_sweep.py --repo allenpd728/ephapse --dry-run   # print, write nothing
python3 tooling/hub_sweep.py --repo allenpd728/ephapse             # append one snapshot
```

It is normally run by the `hub_sweep` GitHub Actions workflow on a schedule and
on manual dispatch. The workflow file is `.github/workflows/hub_sweep.yml`.
A scheduled run that finds no change appends nothing, so an idle repo does not
grow the log.

## Record format

One JSON object per line; append-only; never rewritten. See HuB's
`PM_STATUS_FRAMEWORK.md` for the full schema. Fields:

- `timestamp` — UTC ISO-8601.
- `flow` — counts derived from this repo's issues: `open_total`, `wip`
  (`status:claimed`), `blocked` (`status:blocked-needs-input`), `available`
  (`status:available`), `needs_review`, `blocked_ratio`,
  `cycle_time_median_hours`, `closed_last_30d`, and
  `stale_reversions_since_last` (claims stale per
  `MULTI_AGENT_WORKFLOW.md`: claim comment older than 1 hour with no activity
  since).
- `notes` — the same counts as a one-line human-readable summary.
- `trl` — *only present if* `status/trl.json` exists at the repo root. TRL is a human
  judgement about a component's readiness and cannot be derived from issue counts, so it is
  never guessed: an absent file means the field is omitted and HuB shows its
  "No TRL entries" message. **That is the correct state until someone sets real levels**, not
  a bug to work around.

  What each level means is defined once, for all repos, in HuB's
  [`PM_STATUS_FRAMEWORK.md`](https://github.com/allenpd728/HuB/blob/main/PM_STATUS_FRAMEWORK.md)
  §"What TRL means here". Read it before setting a number — in particular: rate the weakest
  real capability, a component can move *down*, and TRL measures readiness of the *piece*, not
  confidence in the research hypothesis.

  **To publish:** copy `status/trl.json.template` to `status/trl.json`, replace the `null`s
  with integers 0–9, and commit on this repo's tracked branch. It appears on the dashboard
  after the next sweep (up to 30 min, plus ~5 min CDN lag). Existing characters in the log are
  never rewritten; only new snapshots carry the values.

  **Candidate components for ephapse** — drawn from this repo's own docs, not invented.
  Rename, merge, or drop any of these; the list is a starting point, not a contract:

  - **Validation layer** — `tooling/gates/` — the two-tier instrument-vs-phenomenon method. README calls this a first-class output, not scaffolding. Authority: `docs/reference/TEST_VALIDATION_SPEC.md`.
  - **Detector / probe harness** — The SAE/activation probing apparatus validated against the injected positive control (DEC-017/018/024).
  - **Candidate generator** — Cross-domain co-activation as a hypothesis source. Currently a clean null at 70M (`docs/ROADMAP.md` rungs 0-2).
  - **Claim tooling** — `tooling/claims/` — the git-ref compare-and-swap claim lock (#27).

  **How to arrive at a level for this repo.** The level is not a vibe — it is read off a
  structure this repo already maintains:

  Derive levels from the **rung ladder in `docs/reference/TEST_VALIDATION_SPEC.md` Section 5
  (Observed -> Recorded -> Surface-controlled -> Causal per-feature -> Causal aggregate ->
  Handed off)**, which is already adapted from PleaNP explicitly. Map rung 1 (Recorded) to
  level 4 and rung 5 (Handed off) to level 7. Respect the documented ceilings: the spec states
  rung 3 is not reachable at pythia-70m and rung 5 is not reachable by an agent, so nothing
  here may be rated as though those were met.

  Ephapse distinguishes *instrument-validated* from *phenomenon-present* (`docs/reference/PROGRAM_MANAGEMENT_SPEC.md` §3.2). That distinction is exactly what TRL should capture here: the validation layer can be highly ready while the candidate generator's *scientific* result is still a null. Rate the capability, not the finding.

  **Do not name a component after an internal task or issue.** Name the capability you would
  hand to someone else — that is what makes the level meaningful to a reader outside this repo.

## Tests

```bash
python3 {test}
```

They are offline and stdlib-only — no network, no token. They cover the
claim-staleness rule, the flow counts, TRL handling, and the append-only /
no-duplicate guarantees.
