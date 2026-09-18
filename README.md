# Ephapse

> **Proof-of-concept stage.** No co-activation event has been found and
> reviewed yet. The scaffolding is deliberately minimal — see "What not to
> build yet" below.

Ephapse probes open-weight model internals — activations, sparse-autoencoder
features, circuits — to find **cross-domain co-activation**: cases where
unrelated inputs trigger the same internal structure. The bet is that such
overlaps are a useful *candidate generator* for mathematical hypotheses.

Named for the neuroscience term for unintended signal crossover between
adjacent neurons (as opposed to a *synapse*, the intended connection). That
crossover is the literal phenomenon being searched for, here in a network's
activation space instead of a brain.

## At a glance

- **Substrate:** open-weight model weights and activations (not Lean terms).
- **Toolchain:** Python / PyTorch — TransformerLens, SAELens, Neuronpedia.
- **Validation story:** statistical and exploratory. **There is no kernel
  oracle here** — that is the central difference from Maith.
- **Single active branch:** `dev`.
- **Status:** scaffolding only. First real output will be a methodology
  null-result assessment, not a mathematical claim.

## What this project is not

- **Not a fork or extension of Maith.** Different substrate, different
  toolchain, different validation story.
- **Not a training project.** No model is trained or fine-tuned here. Every
  model is pretrained, open-weight, and used read-only for probing.
- **Not a P vs NP project**, and not a circuit-complexity project
  specifically. Domain-general cross-domain search, on the same reasoning
  as Maith's non-goals: aiming narrowly at a famous target produces worse
  scoping than aiming at a falsifiable, general method.
- **Not authorized to claim a discovery is novel or valid** on the strength
  of anything computed here.

## What counts as a result

A flagged co-activation event is a **statistical observation**, not a
finding. Significance is the bar for "worth a human looking at it," not
"worth calling a discovery." Writeups read like lab notebook entries, not
announcements. A candidate becomes a claim only by surviving Maith's gates.

**Unusual activation is not evidence of correctness.** Hallucination-like
generation and genuine insight can look identical from inside activation
statistics alone.

## Relationship to Maith

One-way handoff at exactly one interface point:

1. Ephapse flags a cross-domain co-activation event.
2. **A human** reviews it and, if worth pursuing, articulates it as a
   plain-language mathematical claim.
3. That claim goes to Maith as an ordinary candidate proposal, entering
   Maith's existing gate 1 (homomorphism obligation) like any other.

Ephapse does not implement Maith's gates 2–5, and no Lean validation layer
is built here. If a candidate needs Lean checking, it goes to Maith.

## Two model roles (and a third path)

Frequently conflated; see `docs/AGENT_HANDOFF.md` for the full statement.

1. **The agent-driving LLM** — writes code, drives the agent loop, API-only.
   **It cannot be probed.** No role in the research subject.
2. **The probed model** — a small open-weight model (Pythia-70M–410M),
   downloaded from HuggingFace and loaded locally in-process. The only kind
   of model TransformerLens/SAELens can instrument.
3. **The remote probing API** (Neuronpedia; nnsight/NDIF for larger models)
   — a *third path*, not a smaller local one. Returns top-k activations or a
   feature's decoder vector, never an arbitrary activation matrix. Its
   binding constraint is rate limit, not sandbox RAM.

## Compute

Measured, not estimated — see `docs/reference/SANDBOX_BASELINE.md`.

| Resource | Measured |
|---|---|
| RAM | 15 GiB total, ~13 GiB available (CPU only, no GPU) |
| CPU | 4 cores |
| Disk | 55 GB free |
| Pythia-160M | 2.65 GB RSS, ~217 ms/forward pass |
| Pythia-70M | 1.52 GB RSS, ~121 ms/forward pass |

This caps interactive CPU probing at roughly 70M–1B parameters. Larger
models technically run but forward-pass latency makes iteration
impractical. Note TransformerLens loads fp32 by default, so parameter count
alone is not the constraint — dtype and cached activations are.

## Tooling

Neuronpedia (hosted SAE features) · TransformerLens (probing) · SAELens
(pretrained SAEs) · Pythia suite (interpretability-native models) ·
nnsight/NDIF (remote GPU for larger models).

Prefer targets with real SAE coverage — GPT-2-small and the Pythia suite
have the deepest coverage — over picking a size and hoping an SAE exists.

## Layout

```
README.md                    — this file
requirements.txt             — pinned deps (CPU torch build)
experiments/                 — one dated file per experiment, with a header
                               stating model, inputs, and what's tested
findings.jsonl               — append-only log of flagged co-activation
                               events. Observations only; no conclusions.
docs/AGENT_HANDOFF.md        — scope, non-goals, constraints, first issues
docs/MULTI_AGENT_WORKFLOW.md — claiming, run-ids, dependencies, done-evidence
docs/reference/SANDBOX_BASELINE.md — measured sandbox numbers + evidence
docs/reference/PRIOR_ART.md  — literature review; read before designing a probe
docs/decisions/LOG.md        — decision log (DEC-0xx)
```

## Read this before designing an experiment

`docs/reference/PRIOR_ART.md` is not optional background. It establishes
that SAE feature universality across models is already known, and that SAE
features co-occur more than chance as a baseline — so raw cross-domain
co-activation is close to the expected result rather than a signal. The
interesting object is co-activation that survives a filter built to kill
the boring cases, and the review specifies that filter (NPMI plus semantic
distance, a positive control, clustering for feature splitting, a surprise
criterion).

## What not to build yet

No proposal generator, no automated gate-checker, no promoted-findings
database — not before a single co-activation event has been found and
reviewed by a human. Maith built infrastructure ahead of any result once
already and had to justify it afterward. Don't repeat that here at a
smaller scale.

## Working on this repo

Read `docs/AGENT_HANDOFF.md` first, then `docs/MULTI_AGENT_WORKFLOW.md` for
the claiming protocol. Development happens on the single `dev` branch.
