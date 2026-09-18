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

---

## DEC-011 — Paraphrase invariance is a precondition, not a validation step

**Date:** 2026-09-18 · **Status:** adopted

A co-activation claim is a **vocabulary claim until proven otherwise**. Two
controls are added to the method notes (`AGENT_HANDOFF.md` § Method notes,
`PRIOR_ART.md` §6): the lexical-shuffle control, and a zero-shared-token
requirement between the two prompt sets.

**Rationale:** this objection arrived independently from two directions.
Externally (from a review of a general-purpose cross-domain hypothesis-
generation pipeline): a model's latent space blends genuine regularities with
conventional associations, outdated claims, and linguistic patterns that sound
explanatory without being true — so "search representations for insight" is not
a defensible objective as stated. Internally: this repo's own prior-art review
had already established the same thing three ways — universality makes overlap
the default (§1), absorption makes firing unreliable (§4), and surface artifacts
dominate at 160M. The combined statement is that a flagged co-activation is a
hypothesis about shared semantics that has not yet been separated from shared
surface form.

**Crucially, this is detector-side, not a small-model artifact.** The detector
finds whatever the SAE represents; if the SAE represents tokens well and
relations poorly, the output is token-shaped at any scale. Scaling changes the
mix, not the necessity of the control.

**Also note it is a different filter from NPMI + semantic distance.** That
screen kills pairs whose *features* are semantically similar. It does not kill
pairs whose *inputs* share surface tokens. The confound checklist previously
covered only the first.

**Consequence for issue ordering:** because paraphrase invariance gates the
interpretation of every other result, the paraphrase probe is promoted to the
*first* experiment rather than a later validation step.

---

## DEC-012 — No third repo for real-world cross-domain search (yet)

**Date:** 2026-09-18 · **Status:** adopted

A general-purpose, non-mathematical cross-domain hypothesis-generation pipeline
(document-dossier → candidate generation → adversarial critique → blind expert
scoring → retrospective validation) was reviewed as a possible new sibling
project. **Decision: do not start one now.** The useful parts are carried into
Maith and Ephapse instead.

**Rationale:** the reviewed design is the same intellectual ancestor as Maith
and Ephapse — cross-domain analogical transfer producing falsifiable candidates
— but with a different search mechanism (prompted LLM over text dossiers) and,
decisively, **no validation oracle**. Its entire apparatus — blinded expert
panels, a `ProbePriority = I×P×L/(C×R)` score, adversarial critique — exists to
substitute for the kernel oracle that Maith already has. Building it would mean
building the expensive substitute for an oracle, in a domain where validation
cost is the binding constraint, while the existing projects have not yet
produced a first result. This is the same failure mode as Maith's earlier
"infrastructure ahead of results" mistake.

**Reviewer note:** the reviewed document's NSF framing was also partly wrong
and should not be relied on. NSF 26-512 ("AI Datasets") is explicitly a
*data-readiness* program ("proposals must focus on enhancing the value of
existing scientific datasets… rather than new data collection"), not a
hypothesis-generation program; the relevant broad framing is the Genesis
Mission DCL (NSF 26-023). Separately, its eligibility claim was overstated in
the pessimistic direction: eligible proposers include for-profit organizations,
so an LLC is a cheaper route to eligibility than university partnership.
Verified: $60–100M total, Planning ≤$200k, Impact ≤$2M, Flagship ≤$5M,
deadline 2026-11-04, recurring first Wednesday in November.

**What was carried over instead:**

- **To Maith:** the retrospective time-cut validation design as the preferred
  answer to the missing ground-truth recovery setting (`PRIOR_ART.md` §9.5),
  with the training-cutoff caveat the source document omitted.
- **To Ephapse:** the non-verbal robustness requirement (`PRIOR_ART.md` §6,
  DEC-011).

**Reconsider when:** either project has a first result, or a specific real-world
problem class with a defined outcome measure and an accessible oracle is
identified — at which point the decision to build is about a concrete domain,
not about the general idea.

---

## DEC-013 — The oracle problem decomposes; findings are causal claims

**Date:** 2026-09-18 · **Status:** adopted

Ephapse's lack of a kernel oracle has been treated in this repo as its central
structural weakness. It is actually three questions
(`docs/reference/PRIOR_ART.md` §11). Instruments exist for the first two; the
third is correctly Maith's.

- **Q1 — is feature F causally active?** Yes, testable: **interchange
  intervention** (activation patching), scored on RAVEL's **Cause** and
  **Isolate** properties (Huang, Wu, Potts, Geva & Geiger, ACL 2024). No
  mathematical ground truth needed, and cheap here — one forward pass per
  intervention at ~217 ms, so hundreds of interventions are minutes of compute.
  A causal positive control is therefore *constructible*.
- **Q2 — is the cross-domain overlap real, or tokenization?** Yes, testable:
  the paraphrase and zero-shared-token controls (DEC-011), plus optionally
  SynthSAEBench (arXiv:2602.14687), which supplies 16,384 ground-truth feature
  directions and extends the SAELens this repo already uses.
- **Q3 — is the correspondence mathematically true?** No instrument here, and
  none is needed: the one-way handoff outsources this to the kernel. Ephapse
  should stop behaving as though it requires a kernel.

**The reframe.** The weakness was never the absence of an oracle — it was that
the project was *phrased* as though it needed one. "Statistical significance is
the bar for worth a human looking at it" invites "significant by what
standard?", which has no answer here. The claim this repo can actually support
is narrower and falsifiable:

> Feature F is **causally load-bearing** in both domains A and B, and the
> overlap **survives surface-form controls**.

**Ceilings carried, not buried.** RAVEL: SAE features score 48.6/46.8
disentanglement against 60.1/65.6 for supervised methods — SAEs are measurably
worse at isolation. SynthSAEBench: the best SAE reaches probing F1 0.88 against
a logistic-regression probe's 0.974, MCC 0.78 against ground truth — no SAE
recovers ground truth cleanly. Any Ephapse result inherits these. Both are
recorded in §11 and the references.

**What decomposition does not fix.** A causally load-bearing shared feature can
still be uninteresting ("both inputs involve counting"). That is a base-rate
problem, not an oracle problem, and resists technical solution. Mitigation is
procedural: choose domain pairs whose overlap is *a priori* improbable, and
keep the human gate. Ephapse can make a candidate *credible*, never
*interesting*.

**Consequences:** findings in `findings.jsonl` state causal claims, not
mathematical ones. A new issue adds the causal positive control (handoff
§ Immediate first issues, item 6). SynthSAEBench is recorded as optional and
conditional on measuring CPU feasibility — the paper assumes a single GPU, so
that is a measurement to take, not an assumption.

**Also imported:** the retrospective rediscovery protocol already exists as
literature-based discovery's **replication** method, with a mature evaluation
literature and two documented concerns worth carrying — it rests on a very
small set of confirmed discoveries, and those were made by a researcher with
personal experience of the conditions (a target-set selection concern).
