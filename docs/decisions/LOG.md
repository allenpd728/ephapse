# Decision log

Chronological record of decisions that shape the repo. Format mirrors
Maith's `docs/decisions/LOG.md`: each entry is numbered `DEC-0NN`, dated,
and states the decision plus its rationale. Entries are append-only —
supersede rather than edit.

---

## DEC-001 — Single active branch: `dev`

**Date:** 2026-09-18 · **Status:** adopted

Development happens on one branch, `dev`. No feature branches, no PRs for
routine work; review happens retrospectively on `dev`.

**Rationale:** Maith's DEC-036 consolidated 21 parallel branches into a
single `dev` after branch sprawl caused double-claimed work and lost
commits. Ephapse starts with that lesson applied instead of relearning it
at a smaller scale. The multi-agent claiming protocol in
`docs/MULTI_AGENT_WORKFLOW.md` assumes a single integration branch.

---

## DEC-002 — Agent-driving LLM and probed model are separate roles

**Date:** 2026-09-18 · **Status:** adopted

`docs/AGENT_HANDOFF.md` states explicitly that the LLM driving the
OpenHands agent loop is not the model under study. The agent model is
API-only and cannot be probed; the probed model is a small open-weight
model loaded locally in-process.

**Rationale:** "Use OpenHands Cloud with the free LLM to probe a large
model" conflates two unrelated resources, and the conflation had already
propagated into a proposed plan before being caught. Recording it as a
decision makes the distinction durable across sessions.

**Note:** the doc deliberately does *not* name the agent model. The
platform default has changed repeatedly (GLM 5.2 → Kimi K3 → DeepSeek V4
Flash in the release notes) and account-level config can differ from the
platform default, so any hardcoded name would rot.

---

## DEC-003 — Remote probing APIs are a third path, not a smaller local one

**Date:** 2026-09-18 · **Status:** adopted

Neuronpedia and nnsight/NDIF are documented as a distinct execution path
with a distinct binding constraint (rate limit), not as a way to fit a
bigger model into the sandbox.

**Rationale:** The original tooling list presented Neuronpedia,
TransformerLens, SAELens, Pythia, and nnsight as peers. They are not the
same kind of thing. The local path gives arbitrary activation access over
a size-capped model; the remote path gives top-k results over an uncapped
model. They support different experiments, and the exploratory loop should
use the local path.

---

## DEC-004 — Compute constraints recorded as measured values

**Date:** 2026-09-18 · **Status:** adopted

`docs/reference/SANDBOX_BASELINE.md` records measured sandbox resources
rather than documented estimates. The handoff doc's "24GB RAM" figure was
found to be wrong — measured total is 15 GiB, ~13 GiB available.

**Rationale:** The original doc asked agents to "confirm actual headroom
empirically rather than trusting a back-of-envelope estimate." That
confirmation was performed and contradicted the doc's own premise. Storing
the raw numbers (commands and output) means later issues can size
experiments without re-deriving them, and it keeps the doc honest.

**Measured:** Pythia-160M loads in 7.6 s at 2.65 GB peak RSS with ~217 ms
forward passes; Pythia-70M at 1.52 GB and ~121 ms. Both comfortably inside
budget. No "blocked on compute" issue is warranted at this size.

---

## DEC-005 — Method discipline fixed before the first probe

**Date:** 2026-09-18 · **Status:** adopted

Before any cross-domain probe runs (issue 3), the null model, the
multiplicity correction, and the confound checklist must be fixed and
recorded. `findings.jsonl` records the null model, correction, N, and
confounds checked alongside the observation.

**Rationale:** Cross-domain co-activation is expected to fire often for
uninteresting reasons — polysemantic and catch-all features, shared surface
tokens, sequence position, discourse markers, corpus frequency. With 10^5
features, per-pair significance is meaningless without correction. If the
filter is chosen after seeing the data, `findings.jsonl` fills with noise
that looks like signal — which is the same failure mode as building
infrastructure ahead of results, one level down.

**Consequence:** a null result at 160M is an expected and legitimate
outcome, and is recorded with the same care as a positive one.
