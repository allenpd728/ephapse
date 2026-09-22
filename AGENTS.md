# AGENTS.md — ephapse

> Condensed project reference for AI agents working in this repo. Dense by design.
> For a human-readable introduction see `README.md`; for the roadmap see `docs/ROADMAP.md`.

## Portfolio front door — read this before you start work

This repository is one part of a wider portfolio. Before you claim or start work
here, spend five minutes in **`philipdallen/portfolio-ops`** (private), in this order:

1. `HANDOFF.md` — current portfolio state, what is blocked and on whom.
2. `EXECUTION_PLAN.md` — the week's priorities and the sequencing principles.
3. `RISK_REGISTER.md` and `AGENTS.md` — open risks, and the rules that apply to you.

Why this is worth five minutes: it is the only place that records **decisions already
made** and **work already owned by a human**. Skipping it is how a session redoes
someone else's work, contradicts a recorded decision, or spends its run on something
a human must do anyway.

**If you are an unattended automation run, skip this step** — the operating contract
is already inlined at the top of your prompt, and this orientation is for
human-directed and ad-hoc sessions.

**Do not confuse the two queues.** Work here is claimed and executed locally. Janitorial
work — lint sweeps, stale references, mechanical hygiene — is deliberately tracked
privately in `portfolio-ops`, not filed here. If you find mechanical work, do not file
it publicly; note it in your run output so it can be routed.

## Branches

There is one branch: **`main`**, the working branch and the GitHub default. Every commit
lands here, and it is the branch visitors and all tooling read. (It was named `dev`; the
owner renamed it to `main` on 2026-09-22 so the portfolio converges on one convention.)

A second branch would be a **milestone marker**, per the portfolio branch policy
(`portfolio-ops` `OPERATING_CADENCE.md` §5): promoted deliberately at a milestone, then
left to sit. There is none today, and creating one is an owner decision.

**Edit workflows on `main`.** A `schedule:` trigger fires only from the default branch, so
a workflow on any other branch will not run. This is also why the workflows carry
`ref: main` and `git push origin main` — when the branch was renamed, those references had
to move with it or the sweep would fail to check out.

## Project overview

Ephapse probes open-weight model internals — activations, sparse-autoencoder features,
circuits — to find **cross-domain co-activation**: cases where unrelated inputs trigger
the same internal structure. The bet is that such overlaps are a useful *candidate
generator* for mathematical hypotheses.

- **Substrate:** model weights and activations (not Lean terms).
- **Toolchain:** Python / PyTorch — TransformerLens, SAELens, Neuronpedia.
- **Target model:** `pythia-70m-deduped` (DEC-014), pinned in `tooling/gates/target_model.txt`.
- **Single active branch:** `main` — working branch and GitHub default (renamed from `dev`).
  See the Branches note above before creating any other branch.
- **Status:** proof-of-concept. The detector is validated against an injected positive
  control; a probe found a weak bridging signal; the general cross-domain probe returned
  a **clean null** at 70M. No co-activation event has been human-reviewed.

**There is no kernel oracle here.** That is the central difference from a formal-math
repo, and why the two-tier validation layer in `tooling/gates/` carries as much
discipline as is mechanically checkable.

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

`.github/workflows/ci.yml` runs on push/PR to `main`. Three jobs: `gates`,
`tests`, `summary`. It installs **pytest only** — never `requirements.txt`, since
torch would break the tier-0 guarantee.

Before this workflow existed, *no* CI ran the auditor or hub-sweep suites in any
of the three repos. A broken check would have reported "no findings" and been
indistinguishable from a clean repo. Adding CI immediately surfaced three
pre-existing defects (recorded in `tooling/gates/README.md`) — that is the
argument for the workflow, made by the workflow.

**A green tier-0 run is necessary, not sufficient.** It does not mean a detector
measures what it claims.

## Key terms

| Term | Meaning |
|---|---|
| **Cross-domain co-activation** | Unrelated inputs triggering the same internal structure — the phenomenon being searched for. |
| **Gate** | A validation step in `tooling/gates/`. The authority is `docs/reference/TEST_VALIDATION_SPEC.md` §3–§4. |
| **Positive control** | An injected signal the detector must recover. A gate that cannot fire proves nothing. |
| **Null result** | A real, reportable outcome here — not a failure to be hidden or reframed. |
| **DEC-NNN** | A decision record in `docs/decisions/`. Cite them; do not relitigate them. |

## Working mechanics

**Claim before you work.** `tooling/claims/claim.py` is the authoritative lock — a git-ref
compare-and-swap, because GitHub labels are last-write-wins and cannot prevent a race.
The claim *file* is authoritative; the label and comment are visibility only. Exit `0`
means you hold it, `2` means you lost the race (do no work, pick another), `1` is an error.
See `tooling/claims/README.md` and `docs/MULTI_AGENT_WORKFLOW.md` §4.

**Run the gates before you claim done.** `python3 tooling/gates/run_all.py`. The pattern
these exist to catch is *a plausible-looking artifact produced by a process whose
correctness was never checked*. A passing gate you did not verify can fire is not evidence.

**Record findings in `findings.jsonl`,** per the schema the gates enforce. A committed
artifact is evidence of process; that is why it stays public.

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

## Recent state

Read `docs/AGENT_HANDOFF.md` and `docs/NEXT_STEPS.md` before picking work — they carry the
current position more accurately than this file, which is a stable reference and is not
updated per session.
