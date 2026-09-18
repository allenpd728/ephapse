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

---

## DEC-006 — Prior-art review performed; core premise revised

**Date:** 2026-09-18 · **Status:** adopted

`docs/reference/PRIOR_ART.md` records the field check performed before the
first probe. It revises the project's framing in one important way.

**Finding:** the premise that cross-domain co-activation is a
distinctive, low-base-rate event is not supported. SAE feature universality
across models is established (arXiv:2410.06981; Anthropic's *Towards
Monosemanticity*), and SAE features are already known to co-occur more than
chance even in large SAEs (Clarke, PIBBSS). Co-activation is close to the
*expected* result.

**Revised framing:** the object of interest is not co-activation, it is
**co-activation that survives a filter built to kill the boring cases**.
This keeps the project's premise alive — a filter yielding a small,
well-characterized residue is still a usable candidate generator — while
removing the false expectation that raw co-activation is signal.

**Also adopted from the review:** NPMI + semantic-distance filtering rather
than raw co-activation magnitude; surprise-style ranking
(`structural similarity x semantic distance`) rather than activation
magnitude; clustering before counting hits, to control for feature
splitting; and the feature-absorption caveat on all null results.

---

## DEC-007 — Detector validation (positive control) gates the first probe

**Date:** 2026-09-18 · **Status:** adopted

A new issue — validating the detector against an injected known
cross-domain correlation — is inserted between toolchain setup and the
first probe. It is a hard blocker for the probe.

**Rationale:** the reference method in `PRIOR_ART.md` §2 validates by
injecting known correlations into a background corpus and measuring
recovery, down to 10/10k injections, and shows an LLM-judge baseline
recovers them only unreliably. A null baseline alone establishes that a
detector is not *too permissive*; it cannot establish that the detector
works at all. Since a null result is an explicitly anticipated outcome of
the first probe, a null from an unvalidated detector would be
uninterpretable — we could not distinguish "no structure exists" from
"the detector cannot see structure." Validating first makes the probe's
result interpretable either way.

---

## DEC-008 — Intervention guidance qualified; ablation preferred over steering

**Date:** 2026-09-18 · **Status:** adopted

The handoff doc's "correlation triages; intervention evidences" is retained,
but the intervention bar is specified more carefully than in the original
draft:

- Prefer **ablation** over additive/contrastive steering. The unreliability
  results (arXiv:2505.22637; Tan et al. NeurIPS 2024) concern additive
  steering, where effects are high-variance and frequently opposite to the
  intended direction, with some concepts effectively "anti-steerable."
- Require **in-distribution** contexts; out-of-distribution is where
  steering failures concentrate.
- Include an **interference control**: intervening on one SAE feature is
  known to transfer to semantically unrelated features on Pythia-70M and
  GPT-2-small specifically (ICLR 2026, *Polysemantic Interference
  Transfers*) — Ephapse's exact target models.
- Treat a **failed** intervention as inconclusive, not as evidence against
  the feature.

**Rationale:** an earlier session recommended intervention as the evidence
bar without qualification. The literature does not support an unqualified
version of that claim, and the strongest counter-evidence is on this
repo's exact target models.

---

## DEC-009 — Arithmetic-adjacent candidates need a heuristic check

**Date:** 2026-09-18 · **Status:** adopted

Any flagged pair involving numerical or arithmetic input must explicitly
rule out the "bag of heuristics" explanation before a human spends time
articulating it as a mathematical claim.

**Rationale:** circuit analysis shows models solve arithmetic with
memorized heuristics rather than robust algorithms (arXiv:2410.21272, ~1.5%
of key MLP neurons suffice for ~96% of arithmetic accuracy). A math-adjacent
co-activation may therefore be two heuristics sharing a trigger pattern, not
a shared mathematical concept. This is the most likely way for the project
to produce a plausible-looking artifact.

---

## DEC-010 — Cross-repo note: gate 1 is not vulnerable; causal abstraction is borrowable

**Date:** 2026-09-18 · **Status:** corrected same day (see revision below)

**Original claim (now withdrawn as mis-sized).** This entry originally
flagged a risk that Maith's gate 1 (homomorphism obligation) could be passed
vacuously, citing Sutter et al. (arXiv:2507.08802, NeurIPS 2025 spotlight) —
the proof that causal-abstraction analyses become vacuous when the alignment
map is arbitrarily expressive, demonstrated at 100% interchange intervention
accuracy on randomly initialized models.

**Why that was wrong.** Reading Maith's actual gate definitions
(`AXIOM_DISCOVERY.md` §Validation pipeline) shows gate 1 is a *written Lean
obligation* — "Prove φ(x ∘ y) = φ(x) ⊕ φ(y) for the relevant operation pairs.
Fails to typecheck → candidate dead, no partial credit." Its complexity is
fixed by the term a human wrote; it is not a fitted, learned, or
capacity-selected map. The Sutter result concerns *learned* alignment maps in
causal-abstraction analyses (DAS-style), where it is the map's capacity that
makes the test vacuous. The result does not transfer to a kernel-checked Lean
term, so the warning did not apply.

Maith also already covers the degenerate case this entry was gesturing at:
gate 2 exists to reject the Unit-collapse, and Maith's own `AGENT_HANDOFF.md`
#29 starter names it explicitly ("a φ that passes gate 1 and fails gate 2").
Flagging a known-handled failure mode as a new risk is worse than not
flagging it — it spends the receiving project's attention on a non-issue.

**Correctly-aimed residue (minor).** A non-injective φ into a target whose
operations are weak enough that the homomorphism law holds for uninteresting
reasons is only partly caught by gate 2's "prove *or characterize* φ's
kernel." Worth a line in Maith's own docs at most; not a cross-repo risk.

**What is actually borrowable.** The causal-abstraction / interchange
intervention literature (Geiger et al., arXiv:2303.02536; causal abstraction
survey arXiv:2410.20161) is the rigorous formalization of the *question
gates 1–2 ask* — does a map preserve structure? It supplies a graded metric
(interchange intervention accuracy) and theory about when such a test is
meaningful. That is a strengthening for gates 1–2, not a defect in them, and
belongs in Maith's active-track prior art rather than here.

**Scope:** this repo's handoff creates the interface, so the note lives here;
the substance belongs on the Maith side. Raised there as an issue (see the
prior-art gap), not as a risk.
