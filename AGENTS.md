# AGENTS.md

> Condensed operational reference — dense by design, not narrative prose. For the
> project's purpose see `README.md`; for audit behaviour see `docs/AUDITOR.md`.
> The sibling repos (`philipdallen/Maith`, `philipdallen/PleaNP`) carry their own
> AGENTS.md and their own trees; this file covers ephapse only.

## Project overview

Ephapse probes open-weight model internals — activations, SAE features, circuits —
for **cross-domain co-activation**: unrelated inputs triggering the same internal
structure, as a candidate generator for mathematical hypotheses.

- **Domain:** interpretability of small open-weight transformers.
- **Target model:** `pythia-70m-deduped` (DEC-014), pinned in
  `tooling/gates/target_model.txt`.
- **Stage:** proof-of-concept. No co-activation event has been found and reviewed
  by a human yet. Findings live in `findings.jsonl`; the run log in
  `experiments/README.md`.
- **Active branch:** `dev` is the only active branch (DEC-001).

## The validation layer

Three layers, deliberately separated. Conflating them is the failure this repo
exists to avoid.

| Layer | Where | What it proves |
|---|---|---|
| Tier-0 gates | `tooling/gates/` | Artifacts are internally consistent and each check *can* fail |
| Tier-1 | not here | A detector measures what it claims (needs the model) |
| Human | review | The claim is worth believing |

### Running the gates

```bash
python3 tooling/gates/run_all.py                 # all gates, fixtures
python3 tooling/gates/run_all.py --gate G-R3     # one gate
python3 -m pytest tooling/gates/tests/ -q        # the harness's own tests
python3 tooling/tests/test_auditor.py            # auditor suite (stdlib)
python3 tooling/tests/test_hub_sweep.py          # hub-sweep suite (stdlib)
```

Exit codes: `0` when every gate is `PASS`; `1` when any is `FAIL` or `BROKEN`.
`BROKEN` means a gate's fixture pair is missing — not a tree defect.

**The gate suite validates fixtures, not the real tree.** `run_all.py` runs each
gate against its clean/failing fixture pair. To check the real artifacts, call
the entry points directly:

```bash
python3 tooling/gates/validate_findings.py       # real: rc=0
python3 tooling/gates/validate_experiments.py    # real: rc=1 (G-R1/R2/R5, issue #15)
python3 tooling/gates/validate_deps.py           # real: rc=1 (unpinned numpy, issue #21)
python3 tooling/gates/validate_program.py        # real: rc=0
```

The two real-tree failures are **known and tracked** (#15, #21), asserted by
`test_experiment_gates_fail_on_the_real_tree_at_this_issue` so a gate silently
going green is itself a failure. Do not "fix" them by weakening the gate.

### The fixture rule

Every gate must ship a *failing* fixture that proves it can fire. A gate that
cannot be shown to fail is `BROKEN`, and `BROKEN` is not a pass. This rule was
vacuous the first time it was hand-checked in Maith, so CI now verifies it by
deleting a failing fixture and requiring `BROKEN`.

## CI

`.github/workflows/ci.yml` runs on push/PR to `dev`. Three jobs: `gates`,
`tests`, `summary`. It installs **pytest only** — never `requirements.txt`, since
torch would break the tier-0 guarantee.

Before this workflow existed, *no* CI ran the auditor or hub-sweep suites in any
of the three repos. A broken check would have reported "no findings" and been
indistinguishable from a clean repo. Adding CI immediately surfaced three
pre-existing defects (recorded in `tooling/gates/README.md`) — that is the
argument for the workflow, made by the workflow.

**A green tier-0 run is necessary, not sufficient.** It does not mean a detector
measures what it claims.

## Gotchas

- **Run the suites from the repo root, and from somewhere else.** `test_hub_sweep.py`
  was cwd-dependent: it passed from `/tmp` and failed from the repo root because it
  passed `Path(".")` where a `tmp_path` belonged. CI now re-runs both suites from
  `/tmp` to pin this class of bug shut. Use `tmp_path`, never `Path(".")`.
- **`findings.jsonl` is append-only, enforced by count.** G-E6 compares the record
  count to `findings.highwater` (a committed integer). Adding a record means
  raising the mark in the same change. A stale mark fires; the gate names the fix.
- **Unknown keys in `findings.jsonl` fail G-E1.** Additions go in
  `KNOWN_EXTENSIONS` in `validate_findings.py` — making the change explicit is the
  point, not freezing the schema.
- **One gate test is tier 1 and skips in CI.**
  `test_g_p2_is_right_in_both_directions_on_strings_vs_ids` downloads the tokenizer.
  It uses `pytest.importorskip`, so it skips visibly under `-rs` rather than
  failing the job. It is an *unenforced* check until the token-id sets are committed
  (spec §10 Q2).
- **No secret scanner false positives.** `tooling/auditor.py` is scanned by its own
  tests; `test_auditor_source_never_flags_itself` guards this. If you add a pattern
  that matches its own source, that test fires.
- **Workflows need the top-level `permissions` block.** The auditor's
  workflow-hardening check flags a workflow that omits it.

## Code style

- Stdlib-only for tier-0 tooling. Add a dependency only with a reason that survives
  the tier-0 guarantee.
- Mutation-check anything load-bearing: a check that cannot be shown to fail is not
  a check. Existing examples in Maith's `python/test_*_guard.py`.
- Don't restate the code in comments. Explain non-obvious invariants (append-only
  by count, `BROKEN` vs `FAIL`, why a check is advisory) — those earn a comment.

## Three-repo shared code

`tooling/auditor.py`, `tooling/tests/test_auditor.py`, and
`tooling/tests/test_hub_sweep.py` are **byte-identical across all three repos**.
A fix in one must be propagated to the other two and the hashes re-verified:

```bash
for f in tooling/auditor.py tooling/tests/test_auditor.py tooling/tests/test_hub_sweep.py; do
  md5sum /workspace/work/{Maith,PleaNP,ephapse}/$f
done
```

Divergence is silent drift, not a merge conflict.
