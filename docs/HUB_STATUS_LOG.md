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
- `trl` — *only present if* `status/trl.json` exists. TRL is a human judgement
  about this project's components and cannot be derived from issue counts, so
  it is never guessed here: absent file means the field is omitted and HuB
  shows its "no TRL entries" message. To publish TRL, commit
  `status/trl.json` as `{"components": {"<name>": <0-9>, ...}}`.

## Tests

```bash
python3 {test}
```

They are offline and stdlib-only — no network, no token. They cover the
claim-staleness rule, the flow counts, TRL handling, and the append-only /
no-duplicate guarantees.
