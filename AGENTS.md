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

`dev` is the working branch and the GitHub default — every commit lands here, and this is
the branch visitors and all tooling read. There is no `main`.

If a `main` is ever created it is a **milestone marker**, per the portfolio branch policy
(`portfolio-ops` `OPERATING_CADENCE.md` §5): promoted from `dev` deliberately at a
milestone, then left to sit still. It is not a working branch, and creating one is an
owner decision — a `main` that immediately sits stale is worse than no `main`.

**Edit workflows on `dev`.** A `schedule:` trigger fires only from the default branch,
which is `dev` here, so a workflow on any other branch will not run.


## Project overview

Ephapse probes open-weight model internals — activations, sparse-autoencoder features,
circuits — to find **cross-domain co-activation**: cases where unrelated inputs trigger
the same internal structure. The bet is that such overlaps are a useful *candidate
generator* for mathematical hypotheses.

- **Substrate:** model weights and activations (not Lean terms).
- **Toolchain:** Python / PyTorch — TransformerLens, SAELens, Neuronpedia.
- **Single active branch:** `dev`, which is also the GitHub default. See the Branches note
  below before creating any other branch.
- **Status:** proof-of-concept. The detector is validated against an injected positive
  control; a probe found a weak bridging signal; the general cross-domain probe returned
  a **clean null** at 70M. No co-activation event has been human-reviewed.

**There is no kernel oracle here.** That is the central difference from a formal-math
repo, and why the two-tier validation layer in `tooling/gates/` carries as much
discipline as is mechanically checkable.

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

## Recent state

Read `docs/AGENT_HANDOFF.md` and `docs/NEXT_STEPS.md` before picking work — they carry the
current position more accurately than this file, which is a stable reference and is not
updated per session.
