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

---

## DEC-014 — Target model is pythia-70m-deduped; the 160M plan was unbuildable

**Date:** 2026-09-18 · **Status:** adopted (supersedes the model guidance in
DEC-004 and the tooling section as originally written)

**Decision:** the probed model for all experiments is **`pythia-70m-deduped`**
(`d_model=512`, `n_layers=6`). Every "Pythia-160M" reference in the handoff
doc and in the issue-#1 baseline is superseded.

**Rationale — measured, issue #2 run `20260918-1720-altu`.** SAELens exposes
**7 Pythia SAE releases and all of them are `pythia-70m-deduped`.** There is no
pythia-160m release and no non-deduped pythia-70m release. The handoff doc
recommended "Pythia-70M to ~410M" and the #1 session measured 160M as the
working target — both were selecting on parameter count without checking
whether a pretrained SAE exists. It does not. **The cross-check requirement in
issue #2 is unsatisfiable at 160M** without training an SAE, which is out of
scope (this is not a training project).

This is a case of the project's own most-repeated lesson: a decision was made
from a plausible-sounding range rather than from a query against the actual
catalogue. The constraint is hard, not a preference.

**Consequences:**

1. `pythia-70m-deduped` is *smaller* than the 160M target, so the #1 measured
   latencies and memory figures remain valid as upper bounds.
2. The `neuronpedia_id` field in the SAELens release directory is the
   authoritative bridge for matching a local SAE to its hosted copy (e.g.
   `blocks.3.hook_resid_post -> 'pythia-70m-deduped/3-res-sm'`). Do not
   guess hosted naming.
3. Later issues must check SAE availability before naming a model, not after.

---

## DEC-015 — Neuronpedia does not serve decoder vectors; use local `W_dec`

**Date:** 2026-09-18 · **Status:** adopted (corrects DEC-003)

**Decision:** the decoder direction comes from **local** `sae.W_dec`
(shape `(d_sae, d_model)`, confirmed `(32768, 512)`). The remote-probing path
is for *inspection* only: dashboards, top-k activations, `maxActApprox`,
autointerp labels.

**Rationale — measured.** An earlier claim in DEC-003 and the handoff doc said
the Neuronpedia feature endpoint returns a feature's decoder vector usable for
held-out-text testing. It does not: `hasVector` is `False`, `vector` is an
empty list, and `?includeVector=true` does not change either — verified on
five `pythia-70m-deduped/3-res-sm` features and one `gpt2-small/9-res-jb`
feature. The claim was written from the API's *field names* rather than from a
response, and the field exists but is empty.

**Why this is not a loss:** local `W_dec` is strictly better for the purpose —
no rate limit, no network dependency, no hosted copy to trust, and it is the
actual direction the local SAE uses. DEC-003's core distinction still stands
(remote is a different path, not a smaller local one); only the claim about
what it *returns* was wrong.

**Also recorded from the same run:** the cross-check between local SAE
activations and Neuronpedia's `maxActApprox` agrees in magnitude for 4 of 5
features but spans 0.275x–4.7x. That spread is expected, because
`maxActApprox` is Neuronpedia's maximum over their dataset while the local
figure is over 8 prompts — **neither bounds the other.** The endpoint is a
sanity check on feature *identity* only; `maxActApprox` must not be used as a
reference value for anything quantitative.

---

## DEC-016 — The detector's BH-FDR layer was structurally impossible; the max-statistic test is the criterion

**Date:** 2026-09-18 · **Status:** adopted (corrects the method notes and
issue #5's specification)

**Decision:** the co-activation detector's family-wise control is the
**max-statistic permutation cutoff** (95th percentile of the per-permutation
maximum NPMI). The Benjamini-Hochberg FDR layer is **removed as a criterion**
and must not be used unless `N_PERM >= 1e4`.

**Rationale — found by running, not by review.** The issue-#5 positive control
(commit pending, run `20260918-2329-zbmn`) used N_PERM=100 permutations over
m=62,500 feature pairs at q=0.10. With 100 permutations the *smallest
achievable* p-value is 1/100 = 0.01, while BH's most permissive threshold is
q/m = 1.6e-6. **The gap is 6250x, so no pair could ever pass, regardless of how
strong the signal is.** The reported `fdr=0` was therefore structural, not
evidence — and a reader could easily have recorded "no significant pairs
found" as a finding about the model when it was a fact about the arithmetic.

Permutation p-values cannot resolve a family of 6e4 at q=0.1 with 1e2
permutations: the resolution and the required significance are 3.8 orders of
magnitude apart. Fixing it by raising N_PERM to 1e4 costs 100x the permutation
loop; the max-statistic cutoff achieves valid family-wise control at the
current cost and is what the positive control uses.

**This is the second time in two issues that a plausible-looking spec was
wrong in a way only execution exposed.** Issue #2 found a model target with no
SAE; this found a multiplicity correction that could not fire. Both had been
written into the method notes from an authoritative-sounding source
(PRIOR_ART §2's "compare against a threshold with correction") rather than
checked against the arithmetic of the actual run.

**Consequence for the method notes:** the handoff doc's instruction to
"correct for multiplicity (BH-FDR or a permutation null) over the whole
feature x pair matrix" was ambiguous between two things that are not
interchangeable at this scale. It now specifies the max-statistic permutation
cutoff as the default and records the BH constraint explicitly.

---

## DEC-017 — The detector positive control passes; scope of the claim is narrow

**Date:** 2026-09-18 · **Status:** adopted

**Decision:** issue #5's positive control **passes** on the max-statistic test,
and `findings.jsonl` now holds its first record. The scope of what this
establishes is recorded precisely, because the temptation to overclaim is
high.

**Result (run `20260918-2329-zbmn`):**

- Negative control (no injection): 0 pairs above the 95th-percentile cutoff.
- Injection sweep: best NPMI exceeds the cutoff at **every** rate — 0.8485 vs
  0.5614 at 1%, rising monotonically to 0.9717 vs 0.5740 at 20%.
- The detector recovers an injected cross-domain pair present in as few as
  **13 of 1310 passages**.

**What this establishes.** The detector's *mechanics* are correct: it finds a
planted cross-domain correlation, degrades gracefully rather than
all-or-nothing, and produces no false positives on an uninjected corpus.

**What it does NOT establish — recorded so it is not misread later.** The
planted signal is a **surface-token effect**. A bag-of-bigrams model would
detect it by construction, so this says nothing about whether the detector
finds *semantic* structure. The genuine cross-domain question remains #6's
(paraphrase invariance), which is now the gate that matters. **A pass here must
not be cited as evidence that co-activation detection works on real
cross-domain structure.**

**Incidental value:** because the signal is surface-level and known, this run
also gives a clean read on **feature absorption** (PRIOR_ART §4) — the SAE did
represent the planted co-firing signal at 1% prevalence, so absorption did not
erase it at this scale. That is a small positive for the absorption concern.

**Process note:** three designs were wrong before this one ran — independent
RNG draws on the two sides (nothing coupled, no signal to find), one-sided
injection (a token only in domain A cannot induce a cross-domain
co-activation, so the null would have been a benchmark bug), and an unbounded
pair search (~1e8 pairs x 100 permutations). Each was caught by inspecting the
design before or during execution. The first would have produced a false
negative that looked like a real result.

---

## DEC-018 — Independent replication of the #5 positive control (analytic null)

**Date:** 2026-09-18 · **Status:** adopted

**Context — this is an independent second implementation of #5.** It ran
concurrently with the permutation-test version recorded in DEC-016/017, from
a different agent session, using a different null: an **analytic**
Poisson-independence null (per-pair upper tail, BH-FDR over the whole
family) rather than a permutation null. Both passed. The difference in null
matters, and it bears directly on DEC-016's conclusion:

- DEC-016 found the BH-FDR layer *structurally impossible* because a
  permutation null with N_PERM=100 has a resolution floor of p=0.01 while
  BH at m=6e4 needs p <= q/m = 1.6e-6 — a 6250x gap.
- This run's analytic null has **no such floor**: p-values are computed,
  not counted. BH therefore does fire, and it is what drives detection
  onset (FDR passes all 400 planted pairs from rate 0.01; NPMI is the
  binding constraint until rate 0.05).

So DEC-016's conclusion is correct *about permutation nulls at N_PERM=100*
and should be read with that scope, not as a general claim that BH cannot
work on this family. Recording both is the point: the two implementations
dissociate "the correction is arithmetically unable to fire" from "the
detector cannot see the signal."

**Decision:** the injected-positive-control parameters are frozen before the
run and recorded here, so the recovery curve is a result rather than a
reshaping: N=2000 background samples (pile-10k idx 0..1999), CTX=64,
GROUP_SIZE=20 per group, injection rates 0, 0.001, 0.005, 0.01, 0.02, 0.05,
0.10, 0.20, 0.40, BH-FDR at q=0.05 over the full pair family, NPMI > 0.8,
decoder-cosine semantic filter < 0.2, cluster cos >= 0.6. Detection is the
conjunction of the three. The naive comparison is top-M raw co-occurrence at
the detector's own flag budget.

**Rationale:** DEC-007 says a null from an unvalidated detector is
uninterpretable; DEC-005 says the null model and correction are fixed before
the run. This extends both to the *control*: if the injected signal, the
thresholds, or the rate grid are chosen after seeing recovery, the curve
measures nothing. Committing them first is what makes the number meaningful.

---

## DEC-019 — A positive control must be shown constructible before it is run

**Date:** 2026-09-18 · **Status:** adopted

**Decision:** every positive control must carry an explicit
**constructibility check** — evidence that the planted signal actually
activates both feature groups — and the run is invalid without it. Recorded
after four consecutive runs of #5 returned zero recovery for reasons that
had nothing to do with detector sensitivity.

**What happened (all four failures, kept because each is a distinct trap):**

1. **Catch-all groups** (run 1). Groups chosen as top-activation features on
   the signal text. At pythia-70m that selects features firing on
   ~2000/2000 background samples. Injecting into more rows cannot raise a
   marginal already at 1.0, so NPMI stays structurally < 0.8 at any rate.
   Measured later: group-A marginals were 0.811 after a 0.20 injection.
2. **Band ceiling too high** (run 2). Restricting to support <= 300 did not
   fix it: with replacement injection pA >= pXY, so NPMI is bounded, and at a
   15% ceiling it tops out at 0.416.
3. **Groups that do not fire** (run 3). Restricting to a low-support band but
   *still* ranking by activation selected features the signal text never
   fires; the planted row activated 0/20 of each group. The check that would
   have caught this immediately did not exist.
4. **Inverted statistical test** (runs 1-4). The per-pair p-value used
   `gammaincc(k, lambda)`, which is the regularized *lower* incomplete gamma
   with the arguments reversed; it returns 1.0 for every pair. No pair could
   be significant, and the *only* reason detection ever appeared to fire was
   that the NPMI mask alone was being counted. The correct upper tail is
   `poisson.sf(k - 1, lambda)`.

**The general lesson, and why it is a decision rather than a bug note.** Every
one of the four produced a *plausible-looking negative result* — no
co-activation found, which is the outcome the project expects anyway. A
broken detector, a broken control, and a genuine absence of structure are
indistinguishable in the output unless the control is separately shown to be
constructible and the test separately shown to be able to fire. This is
`MULTI_AGENT_WORKFLOW.md`'s "a check that cannot fail is not a check"
applied to the *control*, not just the metric — and it is the same failure
Ephapse was created to avoid at the level above.

**Consequence for later issues:** #3 and #6 must each report (a) that the
planted/constructed signal is present in the data by construction, and (b)
that their test statistic fires on a case where the answer is known. A
recovery curve alone is not sufficient evidence that a detector works.

**Result after the fix (run 5, `2026-09-18-injected-positive-control-results.json`):**

| rate | n injected | cross-pair NPMI (median) | detector recovery | naive recovery |
|---|---|---|---|---|
| 0.0 | 0 | 0.025 | 0.000 | 0.000 |
| 0.005 | 10 | 0.282 | 0.000 | 0.000 |
| 0.01 | 20 | 0.391 | 0.000 | 0.000 |
| 0.02 | 40 | 0.507 | 0.000 | 0.000 |
| 0.05 | 100 | 0.663 | 0.015 | 0.000 |
| 0.10 | 200 | 0.762 | 0.150 | 0.000 |
| 0.20 | 400 | 0.834 | **0.868** | 0.000 |
| 0.40 | 800 | 0.887 | **0.895** | 0.000 |

Detection onset sits between rates 0.02 and 0.05, as the arithmetic in the
test header predicts (NPMI crosses 0.8 between those points). It is driven by
the NPMI threshold, not by significance: FDR alone passes all 400 cross pairs
from rate 0.01 onward. The naive raw-co-occurrence baseline recovers **zero**
at every rate and at every budget — the direct evidence that the NPMI +
semantic screen is doing work the obvious alternative does not.

**Ceiling, stated:** recovery saturates at ~0.90, not 1.0, because 42 of 400
cross pairs fail the semantic filter (decoder cosine >= 0.2 for 10.5% of the
A x B block), and 6 further pairs fall below NPMI 0.8 even at rate 0.40. The
0.90 is therefore a property of this group construction, not a detector
limitation.

---

## DEC-020 — Single-feature intervention is below the noise floor at pythia-70m; the ladder is the interpretable instrument

**Date:** 2026-09-19 · **Status:** adopted

**Decision:** a per-feature intervention null at pythia-70m-deduped /
`blocks.3.hook_resid_post` is **inconclusive by construction**, and the
ablation harness must report a **cumulative dose-response ladder** alongside it
or the per-feature reading is uninterpretable. Issue #7's harness implements
both.

**Rationale — measured, issue #7 (`2026-09-18-intervention-positive-control.py`).**

Three things were established, in this order:

1. **The harness works.** Full residual-stream interchange (the known-positive
   DEC-019 requires) moves the output on **5/5** prompt pairs — e.g. base target
   probability 0.389 -> 0.000 while the source target rises 0.000 -> 0.280. So
   the intervention mechanic reaches the output; a null below is about features,
   not about the plumbing.
2. **Single features do not.** Across 50 features (top-10 by source activation
   on 5 pairs), **0** exceeded the 0.01 cause threshold. Cause values were
   0.000 to 0.004. The interference control was clean (max probability shift
   0.00e+00 for a feature inactive in both prompts), so this is not leakage.
3. **The ladder does.** Cumulatively ablating the top-k base features moves the
   target monotonically — e.g. p(base target) 0.389 at k=1 -> 0.055 at k=25 and
   flat thereafter, in 5/5 pairs.

**The interpretive consequence, which is the actual decision.** A single SAE
feature at this scale contributes a share of an output that is small relative to
the residual stream's other ~100 active features, and the SAE's own
reconstruction error is large: **mean relative error 0.362, mean cosine 0.933**
between `resid_post` and `sae.decode(sae.encode(resid_post))`. At 36% relative
reconstruction error, "feature F is causally load-bearing" is not a claim this
setup can test per-feature. Per DEC-008 a null here is **inconclusive, not
negative** — it does not count against any feature.

**A vacuity trap the harness now blocks.** The isolate score (RAVEL's second
property) is *trivially* high when the cause is ~0: if nothing moved, "other
attributes untouched" is necessarily true. The first version of the harness
reported `isolate = 0.996` across all 50 features, which reads like a strong
result and was computed entirely from cases where nothing happened. The harness
now reports isolate **only when cause exceeds the threshold**, and prints
`n/a (cause~0)` otherwise, with the summary stating "NOT REPORTABLE" when no
feature qualifies. This is DEC-019 applied again: a reading that cannot come out
low is not a reading.

**Consequences.**

- #7's `findings.jsonl` record (if any) must carry the ladder and the
  reconstruction error, not a per-feature cause/isolate pair.
- Any later claim of the form "feature F is causally load-bearing in both
  domains" (the claim `PRIOR_ART.md` §11 supports) needs either a larger model,
  a narrower intervention that isolates F's downstream target rather than the
  next-token distribution, or acceptance that the claim is about *aggregate*
  structure rather than a single feature.
- RAVEL's ceiling is carried for calibration as required: SAE 48.6/46.8
  disentanglement vs 60.1/65.6 supervised. This run's per-feature numbers are
  below even that ceiling, consistent with the reconstruction error above.

---

## DEC-021 — Adopt the test & validation spec; decline PleaNP's probe-checklist layer

**Date:** 2026-09-19 · **Status:** adopted

**Decision:** `docs/reference/TEST_VALIDATION_SPEC.md` is **adopted** as the
authority for Ephapse's automated validation layer. Its 24 gates (20 tier-0,
4 tier-1) and their fixture rule become the standard; the two-tier split is
binding and the tiers are never merged. Issue #8 carries this decision.

**Why now.** Four failures in a single day (recorded across DEC-016 to
DEC-020) shared one shape: **a plausible-looking artifact produced by a process
whose correctness was never checked.** The permutation null that could not fire.
The positive control that activated neither group. The per-feature isolate score
that was trivially 1.0 because nothing had moved. Each read as a result and was
an artifact of the apparatus. Ephapse's discipline until now has been prose in
`MULTI_AGENT_WORKFLOW.md` and `AGENT_HANDOFF.md`, enforced by agent diligence —
which is exactly the enforcement that failed four times.

**What is borrowed, and from where.** The central test idea is Maith's
prior-art alignment test (`EXPERIMENT_MEASUREMENT.md`): a result is credible
when it lands where prior art predicts for these conditions. Ephapse's prior art
predicts a **null**, an **absorption-limited** null, and **token-shaped**
detector output — so a strong positive here is the surprising event and is
treated as suspect, not celebrated. The production-line structure and the
fixture rule come from Maith's `PIPELINE_QUALITY_GATES.md` and
`tooling/gates/README.md`. The three-category shape (must-prove / must-refute /
smoke) comes from PleaNP's `VALIDATION_SUITE.md`.

**Declined: PleaNP's probe checklist, and the reason is recorded so it is not
re-proposed.** PleaNP's Layer 3 turns a claim into 3–5 single-choice probes for
a non-Lean-writing reviewer. That design works because the expected answers are
**machine-derivable from the formal text** — `statement_lint.py` computes
quantifier order, direction, and bound from Lean syntax. Ephapse has no formal
text: it has activation statistics and a prose claim. Deriving "expected"
answers would require asking an LLM what the claim means, inserting an
unverifiable step between reviewer and artifact. That is precisely PleaNP's
Pattern-A failure (`FAILURE_AUDIT.md`), where the check confirms the author's
recollection rather than the artifact's content — and it is the same class as
the four failures above, one level up. What does transfer is the *shape*: one
crisp mechanical check on a rendered artifact beats asking a human to weigh
subtle prose. Ephapse's rendering is the done-comment block that mechanically
corresponds to `findings.jsonl` fields, so the human diff is a diff.

**The two-tier rule, adopted verbatim from Maith.** Tier 0 needs no model and
no torch and runs in CI; tier 1 requires loading the probed model. **A tier-0
pass is not "gate passed."** Maith's formulation is exact and binding here:
*"Treating a grep pass as a gate pass is itself an integrity hole."*

**Why this is DEC-recorded rather than a doc edit.** The spec itself says it
"is the input to a decision-log entry, not a decision." Adopting it changes the
authority structure of the repo — what counts as evidence, and what an agent
may not claim on its own. That is a decision, and per the workflow it needs a
dated record with its rationale so a later session inherits the reasoning, not
just the file.

**Consequences.**

- `docs/AGENT_HANDOFF.md` gains a **Validation layer** section pointing at the
  spec, stating the two-tier split, and stating that a tier-0 pass is not a
  gate pass.
- The spec's `Status` line changes from proposal to adopted, citing this DEC.
- Issue #8's Definition of Done becomes satisfiable; #9–#14 and #17–#20 are
  unblocked in dependency order.
- The status ladder (§5) binds: **the word "finding" is reserved for rung 3 and
  above**; rungs 0–2 are observations. Rung 3 (per-feature causal) is not
  currently reachable per DEC-020; rung 4 (aggregate causal) is. Rung 5
  (handoff) is not reachable by an agent.

*Superseded on the ladder and the gate count by DEC-022.*

---

## DEC-022 — The validation layer gains a code-gate series; the spec was pointed one level too high

**Date:** 2026-09-19 · **Status:** adopted (revises the spec adopted by
DEC-021; #22 created)

**Decision:** add a `G-C` series of gates over experiment **code**
(`experiments/*.py`), plus four new artifact gates (G-D7 constructibility,
G-D8 frozen parameters, G-F5 aggregate attribution, and G-D2's
arithmetic-capability requirement), raising the inventory from 24 gates to 34.
The spec's causal rung splits into a per-feature rung 3 (not currently
reachable) and an aggregate rung 4.

**Rationale — the spec's gate inventory gated artifacts, and the failures were
in code.** `TEST_VALIDATION_SPEC.md` was drafted and filed as #8–#21 on
2026-09-18, before issues #5 and #7 ran. Those runs produced five measurements
that looked like results and were artifacts of vacuous code:

| Defect | Decision | Shape |
|---|---|---|
| BH-FDR arithmetically unable to fire (permutation floor p=0.01 vs required 1.6e-6) | DEC-016 | a criterion that cannot pass |
| Catch-all groups with marginal 1.0 | DEC-019 | a statistic bounded below its own threshold |
| Band ceiling still leaving the statistic bounded | DEC-019 | same |
| Groups that never fire on the planted text | DEC-019 | a control never shown constructible |
| Inverted survival function (`gammaincc` for `poisson.sf`) returning 1.0 for every pair | DEC-019 | a test that cannot fire |
| Isolate `0.996` computed entirely from no-effect cases | DEC-020 | a reading that cannot come out low |

None would have been caught by any gate in the original inventory, because all
of them were in the experiment code, not in the artifact it emitted. Every one
is mechanically detectable at design time. This is DEC-019's own formulation —
*a check that cannot fail is not a check* — applied one level up: the spec
checked the outputs and not the apparatus that produced them.

**The self-implicating part, recorded deliberately.** The original spec
contained the right principle in §4: *a gate without a failing fixture is
assumed broken*. Applied to the experiment code rather than to the gate
scripts, that principle would have caught the catch-all groups and the
inverted survival function before either ran. The gates were pointed one level
too high — the same mistake the spec's §1 table attributes to the repo's first
two sessions, made by the spec itself.

**What this changes.**

- `TEST_VALIDATION_SPEC.md` §1 gains the fifth defect class; §3 gains `G-C1–C5`,
  G-D7, G-D8, G-F5 and the corrected G-D2; §5 splits rungs 3 and 4; §6 adds
  `check_experiment_code.py` and `fixture_code/`.
- `docs/AGENT_HANDOFF.md` § Validation layer gate counts updated from DEC-021's
  "20 of 24" to 29 of 34, with the count history noted rather than silently
  rewritten.
- **#22** carries the `G-C` implementation; **#23** logs the detector-contract
  registry as an open gap.
- `fixture_code/` is drawn from the real DEC-019/020 failures, since the
  original code is already fixed — the fixtures are the only way to show a
  `G-C` gate can fire on the shapes that motivated it.

**Scope note — this does not reopen #8.** #8's Definition of Done was met
honestly by run `20260918-2332-e7c4` (`4c84ec6`, DEC-021) against the spec as
then written. Per `MULTI_AGENT_WORKFLOW.md` § 8, a later finding that work was
lacking becomes a new task (#22), not a reopened issue. The sequencing was
briefly wrong in the other direction too: run `20260918-2332-e7c4` blocked #8
on the spec being absent from git, which was correct — the filing run had
written the spec and filed thirteen dependent issues without committing the
document. That is the same class of defect as the ones above, in the process
rather than the code.

---


## DEC-023 — Two detector bugs found by diagnostic; the max-NPMI statistic does not replicate under corrected thresholds

**Date:** 2026-09-19 · **Status:** adopted

> **Numbering note.** This entry was originally written as DEC-018 and was
> renumbered to DEC-023 at rebase because a concurrent session claimed
> DEC-018–022 while this work was in flight. See DEC-018–022 for that
> session's independent replication of #5 and the tier-0 gate scaffolding —
> it reached the same 'catch-all features saturate the statistic' conclusion
> from a different direction (its DEC-019 trap 1). (supersedes DEC-017's pass claim;
corrects the threshold and input-format guidance)

**Two independent bugs in the co-activation detector, both found by diagnostic
after #6's first run returned a degenerate `best = cutoff = 1.0` in every arm
including the null.**

### Bug 1 — the pooled threshold disabled the detector

The 99th percentile of positive activations **pooled across all features** was
11.08, dominated by a few extreme features. At that threshold **32,764 of
32,768 features fired on ZERO prompts.** The detector was not discriminating —
it was switched off. Measured: with per-feature thresholds, 1,632 features
receive a finite threshold and 533 fire on at least one prompt.

**Fix:** per-feature thresholds (95th pct of each feature's *own* positive
activations), plus a selectivity band that excludes features firing on almost
nothing (no signal) or almost everything (bridge saturates to 1.0 under *any*
pairing, destroying contrast).

### Bug 2 — prompts were too short for the substrate

Median prompt length was **5 tokens**, starving the residual stream. Measured
usable features (firing on >=20% of prompts) by input format:

| Format | Median tokens | Features firing on >=20% |
|---|---|---|
| bare prompt | 5 | 541 |
| sentence | 10 | 909 |
| passage | 31 | **1,188** |

**Fix:** all renderings are wrapped in a shared carrier passage, so only the
rendering itself differs and the comparison stays clean.

### Consequence 1: #5's positive control does not replicate

#5 used the same pooled-threshold rule. Re-run with per-feature thresholds
(`experiments/2026-09-19-detector-positive-control-rerun.py`):

```
negative control: best 0.6322, cutoff 0.5830, above=2   <- false positives
injection sweep : best 0.6322 IDENTICAL at every rate, above=3..4
```

**`best` is identical with and without injection at every rate**, so the
top-ranked pair is *not* the injected pair — it is a high-frequency pair
co-occurring for structural reasons. The negative control yields 2 pairs above
a 95th-percentile cutoff where ~0 is expected. Pair count exploded to 7.5M
(from 62,500) because ~2,500–3,000 features per side now fire.

**Verdict: the max-NPMI-over-all-pairs statistic cannot separate the injected
signal from noise at this selectivity.** DEC-017's pass is withdrawn; #5's
result is re-classified as a null, with the statistic itself indicted rather
than the model.

### Consequence 2: the bridge statistic did discriminate

Under the same corrected thresholds, the *bridge* statistic
(`bridge(f) = P(f fires in both renderings)`, restricted to 63 features in the
selectivity band) gave, in #6:

```
matched verbal-symbolic : 6 survivors   (best 0.035 vs cutoff 0.015)
shuffled null           : 0 survivors   (best 0.010 vs cutoff 0.015)
paraphrase within-words : 17 survivors  (best 0.050 vs cutoff 0.015)
```

Matched exceeds null, and paraphrase exceeds matched (expected, since
paraphrase shares lexical items). **This is a weak but real signal** — and it
is the first evidence the project has that a feature can bridge two
lexically-disjoint renderings of the same relation. The effect is small: the
best feature bridges ~7 of 200 pairs, and only 63 of 32,768 features fall in
the selectivity band.

**Design consequence for #3:** use the bridge statistic, not max-NPMI. The
max-statistic-over-millions-of-pairs form is unstable at this feature
selectivity; a per-feature bridging statistic with a restricted selectivity
band is what actually discriminates.

### The pattern, stated plainly

This is the third detector/spec parameter in three issues that was wrong in a
way only execution exposed (#2: a model target with no SAE; #5: a multiplicity
correction that could never fire; #6/#5: a threshold rule that disabled the
detector, plus an input format too short for the substrate). Every one was a
plausible-looking parameter written against an authoritative-sounding source
rather than measured. The mitigation is not more care in writing — it is
measuring before claiming, and recording the measurement.

---

## DEC-024 — Adjudication: the analytic-null positive control stands; the max-NPMI permutation variant does not

**Date:** 2026-09-19 · **Status:** adopted (resolves the DEC-023 vs DEC-018/019
conflict; supersedes the supersession in DEC-023)

**Two concurrent sessions reached opposite verdicts on issue #5.** This entry
resolves it from the committed result files rather than by preference.

### The evidence

**Sibling implementation** (`2026-09-18-injected-positive-control-results.json`,
run `20260918-2332-e7c4`):

```
rate 0.00  n_injected 0    recovered 0    (cross_all3 = 0, no false positives)
rate 0.001 n_injected 2    recovered 0
rate 0.005 n_injected 10   recovered 0
rate 0.01  n_injected 20   recovered 0
rate 0.02  n_injected 40   recovered 0
rate 0.05  n_injected 100  recovered 6     (recovery_rate 0.015)
rate 0.10  n_injected 200  recovered 60    (0.15)
rate 0.20  n_injected 400  recovered 347   (0.8675)
rate 0.40  n_injected 800  recovered 358   (0.895)
naive raw-co-occurrence baseline: 0 hits at every rate
cross-pair minimum p as low as ~1.6e-101
```

**My implementation** (`2026-09-19-detector-positive-control-rerun.py`):

```
negative control: best 0.6322 vs cutoff 0.5830 -> 2 false positives
injection sweep : best 0.6322 IDENTICAL at every rate including 0.0
```

### Verdict

**The sibling's positive control is the valid one and stands.** Mine ran an
instrument that cannot resolve the family it was pointed at. Both are honest
work; they are not equally informative.

### Root cause — three design differences, all favouring the sibling's form

1. **Pair scope.** Theirs tests **400 pre-specified cross-group pairs**
   (20 x 20). Mine tested **all pairs among ~2,500 x ~3,000 active features =
   7.5M**. A max-statistic over 7.5M pairs is governed by the noisiest pair in
   the family; over 400 targeted pairs it is well-behaved. This is the dominant
   cause: my statistic's maximum was set by an unrelated high-frequency pair,
   which is why `best` was *identical* with and without injection.
2. **Group construction.** Theirs pre-specifies groups as
   **low-background-support** features (support 0–30 of 2,000), which
   guarantees the marginals can rise when injection occurs. Mine picked
   features post hoc via a selectivity band, without checking that the planted
   rows actually move them.
3. **Null form.** Theirs is an **analytic Poisson-independence** per-pair
   p-value with BH over the family — no resolution floor. Mine was a
   **permutation null at N_PERM=100**, whose floor (p = 0.01) cannot resolve a
   7.5M-pair family, and whose 95th-percentile estimate is itself noisy at
   that size.

### What my run *did* contribute

Not nothing, and worth keeping distinct from the pass/fail:

- **The pooled-threshold bug is real and independently confirmed** (DEC-023):
  the 99th percentile of activations pooled across all features left 32,764 of
  32,768 features firing on zero prompts. The sibling's DEC-019 trap 1 found
  the same saturation phenomenon ("catch-all groups with marginal 1.0") from
  the opposite direction. Two independent routes to one conclusion.
- **The bridge statistic discriminated where max-NPMI did not** (#6: 6
  survivors vs 0 null, on 63 features). That is a design finding for #3.
- **The prompt-length dependence** (bare 541 / sentence 909 / passage 1,188
  usable features) is a measured constraint on every future experiment, and
  is not in the sibling's work.

### Consequence for the record

DEC-023's framing — "the max-NPMI statistic does not replicate under corrected
thresholds" — is **correct in scope but was drafted as a supersession of #5's
pass, which was wrong**. Corrected here: #5's pass stands; the
*max-NPMI-plus-permutation-null* variant is the instrument that failed, and
that instrument should not be used for a family of millions of pairs.

**Protocol consequence:** the two failures were avoidable *by construction*.
A positive control must demonstrate that the planted signal actually moves the
selected features (a constructibility check), and must use a pre-specified,
bounded pair set rather than an unbounded search. Both are now method-note
requirements. The sibling's DEC-019 reached the first requirement
independently; the second is new here.

**Process note.** This conflict is the first real instance of the shared-identity
hazard the run-id protocol exists for: two sessions, one GitHub account, opposite
verdicts on the same issue, discovered only when a rebase collided. The protocol
surfaced it — the claims carried run-ids and the collision was visible — but it
took reading committed result files to resolve it. Recording that the mechanism
worked, and that resolution required human-legible evidence files, which is why
the results JSONs being committed mattered.

---

## DEC-025 — The #7 intervention result is site- and scale-dependent; DEC-020's negative is a property of its measurement choice, not of the features

**Date:** 2026-09-19 · **Status:** adopted (extends DEC-020, does not supersede it)

**Decision:** two independent runs on issue #7 reached opposite conclusions
about single-feature intervention at pythia-70m-deduped. Both are correct; they
measured different things. The reporting rule that follows is that **every
intervention result must state its intervention site and its metric scale**,
because at this model scale the answer flips on both.

**Two runs, two answers.**

- Sibling run `20260918-2332-e7c4` (DEC-020): ablation/patching at the **final
  token**, scored on **probability**. Result: **0 of 50 features** exceeded a
  0.01 cause threshold. Conclusion drawn: single-feature intervention is below
  the noise floor, and the cumulative ladder is the interpretable instrument.
- This run `20260919-0229-to3m`: patching at the **country token** (the feature's
  own position), scored on the **logit difference**. Result: **mean Cause 0.75**
  (3 of 4 attribute-selective features), against a matched-norm random-direction
  null with an interference control at **0/240**.

**Both sites and both scales, in one harness.** The extension ran the same 24
interchanges at both sites with a separate null per site:

| site | mean Δ logitdiff | mean Δ probability | Cause pass | per-site cutoff | mean Isolate |
|---|---|---|---|---|---|
| country token | **1.309** | 0.00082 | 0.750 | 0.557 | 0.148 |
| final token | 0.775 | 0.00046 | 0.500 | 0.847 | −0.050 |

Two mechanisms are visible in that table, and they are both real:

1. **The effect is a logit-scale effect, not a probability-scale one.** Mean Δ
   probability is 8e-4 at the country token and 5e-4 at the final token — either
   way an order of magnitude below DEC-020's 0.01 threshold. On the probability
   scale both runs agree: a single feature does not visibly move the output
   distribution. On the logit scale the country-token effect is ~1.3 and clears
   its null. A threshold of 0.01 applied to a probability is therefore a
   different, much stricter test than the same number applied to a logit
   difference — the two runs were never measuring the same quantity.
2. **The final token is the worst place to intervene, and its null bar is
   higher.** Random directions at the output position score 0.847 (95th pct),
   because at the last position everything written is the next-token
   prediction. The same random directions at the country token score 0.557. So
   the final token both dilutes a real feature's attributable effect and raises
   the bar it must clear. Patching a feature at its own position and reading the
   difference is the more sensitive configuration.

**What this changes about DEC-020.** Its measurement stands exactly as recorded;
its *generalization* does not. "Single-feature intervention is inconclusive at
pythia-70m" is true at the final token on the probability scale, and is not
established beyond that. Attribute-selective features at their own token do move
the logit difference against a clean null.

**The negative that survives, and it is the more important one.** Mean **Isolate
0.208** at the country token: only f11504 (0.667) clears the 0.400 cutoff;
f21315 and f24019 score 0.00. Across four causally load-bearing entity features,
three fail context isolation. This reproduces DEC-020's diagnosis by a different
route — DEC-020 attributes it to reconstruction error (**mean relative error
0.362, mean cosine 0.933**); this run shows it directly as isolation failure.
Both point at the same ceiling: RAVEL's SAE 48.6/46.8 disentanglement against
60.1/65.6 for supervised methods (arXiv:2402.17700).

**Consequences.**

- Reporting rule: intervention findings carry site + scale. A bare "Cause 0.0"
  is not interpretable without them.
- An entity feature flagged as active in two domains can be causally
  load-bearing without keeping the domains apart, so #3 must report the causal
  and semantic results together, never one alone.
- DEC-020's cumulative ladder remains the right instrument for *aggregate*
  questions; this run's per-feature result is about *attribution* at a known
  site. They answer different questions and both are retained.
- The `findings.jsonl` record for this run sets `causal_claim` to **false**
  deliberately: the schema reserves that flag for a feature load-bearing in both
  domains, and this is a harness self-test on one known-causal task.

**Process note.** This reconciliation was found by the repo's own concurrent-work
rule (rebase revealed a sibling landed the same task). The first instinct — that
one run must be wrong — was itself the error. Neither was: DEC-020 kept its
conclusion and gained a boundary, and this run's `causal_claim=false` is what
keeps it from being read as more than a harness validation.

---

## DEC-026 — G-D9/G-D10: an instrument can pass its cutoff and track the wrong pair

**Date:** 2026-09-19 · **Status:** adopted (revises DEC-022's inventory;
corrects the handoff and gates README citations of DEC-018; adds G-F6)

> **Numbering note.** Drafted as DEC-024, then DEC-025; renumbered again at
> rebase because concurrent sessions claimed both numbers while this was in
> flight (DEC-024 the #5 adjudication, DEC-025 the #7 site/scale reconciliation).
> Its content is independent of both; its framing of #5 defers to DEC-024.

**Decision:** add **G-D9** (the recovered pair is the injected pair — not merely
a pair above cutoff), **G-D10** (a retired or superseded instrument is cited as
such wherever its results were reported), and **G-F6** (an intervention result
states its **site and scale**). Inventory 34 → 37 gates. Correct three stale
`DEC-018` citations in the handoff, which point at content renumbered to
**DEC-023** at rebase.

**Rationale 1 — G-D9/G-D10: a failure class `G-C` does not cover.** DEC-022's
`G-C` gates address code that *cannot fire*: bounded statistics,
non-constructible controls, inverted tests, readings that cannot come out low.
DEC-023's failure is different in kind. The max-NPMI instrument **fired**,
passed its cutoff, and reported a recovery curve — but the top-ranked pair was
**identical with and without injection** (0.6322 at every rate), so it was never
selecting the injected pair. The negative control also produced false positives.

Constructibility alone does not catch this, because the signal *was*
constructible — DEC-019's four traps are fixed in both implementations and it
still happened. DEC-024 located the cause: a max-statistic over an **unbounded**
~7.5M-pair search is governed by its noisiest pair, so an unrelated
high-frequency co-occurrence always wins. The catching question is narrower —
**is the thing you recovered the thing you planted?** — which is G-D9, plus
DEC-024's constraint that the pair set be pre-specified and bounded.

**Rationale 2 — G-F6, from DEC-025.** The #7 reconciliation found two runs
reaching opposite conclusions about single-feature intervention: **0 of 50
features** above a 0.01 cause threshold at the final token on a probability
scale (DEC-020), versus **mean Cause 0.75** at the country token on a logit scale
(DEC-025). Both correct; they measured different things. The same number applied
to a probability and to a logit difference is a different test, and the final
token both dilutes the attributable effect and raises the null bar (random
directions score 0.847 there versus 0.557 at the country token).

G-F2 already required `cause` and `isolate`; it did not require *where* or *on
what scale*. A bare "Cause 0.0" was therefore schema-valid while being
uninterpretable. G-F6 closes that.

**Consequence 1 — a retirement and a boundary must propagate.**
Three documents needed correcting, and the corrections differ from what a first
reading of DEC-023 alone suggests — which is why both are recorded:

- `docs/AGENT_HANDOFF.md` § Immediate first issues item 3 said #5 was
  "**DONE — twice, independently**". Rewritten: which instrument stands (analytic
  null, DEC-018/019), which is retired (max-NPMI + permutation null, DEC-023),
  and the bounded-pair-set constraint that follows from DEC-024.
- `docs/AGENT_HANDOFF.md` method notes cited "DEC-018" three times for the
  threshold bugs and the max-NPMI result — content now **DEC-023**, renumbered
  at rebase when a concurrent session claimed DEC-018–022. Corrected.
- `tooling/gates/README.md` carried DEC-021's "20 of the 24 gates" count.
  Corrected to 29 of 37 with a pointer to the count history.

**Consequence 2 — this is why G-D10 exists.** A retired instrument is a
documentation hazard, not only a scientific one: the pass was recorded in good
faith, is quoted in the handoff, and would have been cited by #3 as
justification for a statistic that does not work. The sequence here — pass
(DEC-017), non-replication (DEC-023), adjudication (DEC-024) — is precisely the
case where a doc can hold three contradictory states at once.

**Consequence 3 — the count moved four times in one day.** DEC-021 said 24,
DEC-022 said 34, DEC-025 said 36, this says 37. Each revision paid a coherence
cost across the spec, handoff, and gates README, and each collision cost a
renumber. Most of that is real design work, but the frequency is a signal worth
naming: **the inventory is accreting a gate per incident.** If that continues,
it is tracking failures rather than being designed — DEC-023's own observation,
*measuring before claiming*, applies to the spec too. Recorded as a caution, not
a fix.

**Scope note.** This entry is inventory and documentation-integrity work. It does
not re-adjudicate #5 (DEC-024 did that from the committed result files) nor #7
(DEC-025), and defers to both.

---

## DEC-027 — The cross-domain probe returns a clean null; a raw co-activation-rate cutoff was the third structurally-broken statistic

**Date:** 2026-09-19 · **Status:** adopted

**Decision:** issue #3's cross-domain probe finds **no feature that co-activates
across the two domains more than chance**, with an interpretable null (the
injected positive control recovers). The statistic required two fixes found by
running; a **raw co-activation-rate family-max cutoff is retired** as a
criterion for the same structural reason BH-FDR was retired in DEC-016.

**Setup (run `20260919-0229-to3m`).** `pythia-70m-deduped`, SAE
`pythia-70m-deduped-res-sm`, hook `blocks.3.hook_resid_post`. 120 cooking and
120 astronomy passages (median 18-19 tokens), generated by
`gen_cross_domain.py` with **zero shared tokenizer ids** - each domain also has
its own glue tokens, so this is the strict DEC-011 input gate, checked
mechanically rather than assumed.

**Result.**

- Positive control (planted token at 10% of paired passages): **recovered**,
  best z **11.30** vs family-wise cutoff **4.47**, on the feature the token
  actually drives.
- Real run: |family| = 793 (selectivity band [0.05, 0.60] in both domains),
  best z **3.10** vs cutoff **4.41**, **0 survivors**. The per-feature-threshold
  variant agrees (66 features, best z 3.37 vs 4.97, 0 survivors).

**The third broken statistic, and why it is the same bug as DEC-016.** The first
version scored the **raw co-activation rate** with a family-max cutoff and its
positive control **failed**: injecting a shared token into 10% of pairs gave
best rate 0.3417 against cutoff 0.3750. Diagnosing that instead of shipping it
showed the cutoff is dominated by high-firing-rate features whose *chance*
co-activation is ~0.37 regardless of what is injected - so no sparse signal can
clear it. This is exactly DEC-016's shape: a family-wise cutoff built on a
statistic whose scale depends on a nuisance parameter (there, p-value resolution
under N_PERM; here, firing rate) becomes unbeatable for the signal of interest.
**Retired rule: do not use a raw co-activation rate with a family-max cutoff
unless features are first put on a common scale.** Standardizing per feature -
`(observed - perm_mean) / perm_sd` - fixed it, and the same control then
recovered at z 11.30.

A second, smaller failure is retained: a **per-feature 95th-percentile firing
threshold** (DEC-023's rule) excludes sparse planted signals, so it did not
recover the control here. It is not wrong for dense signals; it is the wrong
tool for a 10%-prevalence feature. Both firing rules are reported rather than
one being silently chosen.

**What this establishes.** At this model scale, with a bounded pre-specified
family, token-disjoint domains, a recovering positive control, and a
family-wise standardized cutoff, **cross-domain co-activation is not detected**.
Given #6's weak bridging (6 survivors vs 0) and the feature-absorption caveat
(PRIOR_ART §4), the honest reading is that the method has poor signal-to-noise
at 70M, not that cross-domain structure is absent.

**Ceilings and caveats carried.**

- A **null may reflect SAE representational limits** rather than absence of
  structure (feature absorption, PRIOR_ART §4). This is the primary alternative
  explanation and is stated in `findings.jsonl`.
- **Unusual activation is not evidence of correctness**; the converse - a clean
  null - is also not evidence that the structure does not exist.
- Feature splitting: 740 clusters at decoder cosine 0.5 for 793 features, so the
  family is not 793 independent hypotheses; clustering is reported so a raw
  count would not have been inflated.

**Consequence for the repo.** #3's method proof-of-concept is **complete and
negative**: the detector was shown to work (positive control), the inputs were
shown disjoint (mechanically), and the result is null. This is the "method has
no usable signal-to-noise at this scale" outcome the issue named as a legitimate
done state - not a failure to run. It also closes the loop #6 and #5 opened:
three issues, three statistics that looked plausible and could not fire, all
caught by running the positive control first.

**Process note.** This is the fourth plausible-looking statistic in four issues
(#2 model target, #5 multiplicity, #6 threshold, #3 rate cutoff). The pattern is
consistent enough to state as a working rule: **a family-wise cutoff over an
unstandardized statistic is the recurring bug, and only the positive control
catches it.**


---

## DEC-028 — A domain-label permutation null requires label-invariant selection; a concurrent duplicate of #3 was dropped rather than merged

**Date:** 2026-09-19 · **Status:** adopted

**Context.** A second session (run `20260919-0447-mzem`) worked #3 concurrently
with the session that landed it (run `20260919-0229-to3m`, DEC-027), reached the
same null conclusion independently, and — per `MULTI_AGENT_WORKFLOW.md` §5 —
**dropped its own probe** rather than pushing a second copy. The landed #3
design is stronger on the axes that matter (token-disjoint domains, a
mechanically verified zero token-id intersection, clustering, a position
control, and an excess-activation constructibility check), so there was nothing
to merge. This entry records the one methodological residue that is not a
duplicate, and the process event.

**The finding: label-invariance is a precondition for a label-permutation
null.** The dropped implementation permuted **domain labels** — it pooled the
prose and code passages and reshuffled which items were called A vs B. In that
design it selected its feature family (a selectivity band) from the *observed*
per-domain firing rates, then evaluated the observed statistic against the
permuted null. That is circular: features chosen for sitting at the band under
the real labels have their permuted rates scatter, so the observed statistic is
lifted above its own null mechanically. The run reported `T=0.0504` against a
null mean of `0.0470` (sd `0.0007`), `p=0.0` — which reads as a significant
positive and is entirely an artifact of the selection. Binarizing per-domain
(rather than on the pooled corpus) compounds it, and deepens the problem
because the transform itself then depends on the label assignment, so permuting
labels does not permute the transform.

**Why this is not a defect in the landed #3.** #3 permutes **pairing** — it
holds the two domains fixed and reorders one side's rows. A pairing permutation
preserves each side's marginal firing rates, so features selected on observed
rates remain at the band under permutation and no inflation occurs. The landed
result and DEC-027 are unaffected. The rule below is a constraint on a
*different* design that a future probe might reasonably choose.

**Rule adopted.** If a null is built by relabeling items (a domain-label
permutation), then binarization and feature selection must be **label-invariant**:
threshold once on the pooled corpus, and select the family on a pooled
criterion that does not consult the labels. A pairing permutation does not carry
this requirement. The failure is silent — it does not error, it manufactures a
positive — which is the same class as DEC-016, DEC-019, and DEC-027: *a
statistic that looks plausible and cannot be trusted until a positive control is
run against it.*

**Constructibility, independently converged.** The dropped session also
re-derived DEC-019's constructibility precondition, and failed it twice before
getting it right: selecting the planted signal's feature by largest raw
activation on marker text picked a broadly-firing feature (id 21809, firing
1.000 on the code domain at baseline) whose rate then moved for reasons
unrelated to the injection; selecting by **excess** activation over baseline
(`with marker` minus `without marker`) picked a signal-specific feature (id
1684) whose rate rose monotonically as intended. The landed #3 control already
implements the correct form (`top_feature_activation_elevation`), so this is
recorded as convergence rather than as new work.

**Process note.** This is the second instance of the shared-identity hazard
DEC-024 recorded, and the first where the protocol's *drop-the-duplicate* branch
was exercised rather than the adjudication branch. The collision was visible
only because claims carried run-ids and the rebase surfaced it; resolution again
required reading committed result files to determine that one implementation
subsumed the other. The protocol worked as written.

---

## DEC-029 — The claim protocol's ownership check was defective; duplicate claims resolve by earliest comment id

**Date:** 2026-09-19 · **Status:** adopted (corrects `MULTI_AGENT_WORKFLOW.md` § 4;
#26 closed, #27 filed)

**Decision:** the ownership check in § 4 was written as *"re-fetch the issue and
read the latest claim comment: if its run-id is not yours, a sibling won."*
That check **cannot detect the case it was written for**, and it is replaced by
an explicit rule: *does any unexpired claim comment exist whose run-id is not
mine?* When two claims collide, the winner is the claim with the **earliest
server-assigned comment id**.

**Rationale — measured, twice in one day.** A session that claims second always
finds *its own* comment latest, so the old check passes while an earlier live
claim sits unread. The incidents, from the tracker's own event and comment
records:

| Issue | First claim | Second claim | Outcome |
|---|---|---|---|
| #5 | `23:29:50` run `20260918-2329-zbmn` | `23:33:27` run `20260918-2332-e7c4` | Both completed. Their results **disagreed on the same question**, and reconciling that took DEC-023, DEC-024, and a third entry. |
| #11 | `04:52:34` run `20260919-0451-6421` | `04:55:03` run `20260918-2332-e7c4` | Both built the gate in full; resolved at rebase, one implementation discarded. |

On #11 the cost was duplicated effort. On #5 it was **contradictory recorded
results** — the far more expensive failure, and the one that made the bug worth
a decision entry rather than a note.

**Why earliest comment id, and not earliest timestamp.** Comment ids are
monotonic and assigned by GitHub; timestamps in claim comments are
agent-supplied and can be skewed or simply wrong. On both incidents the id order
and the timestamp order happen to agree, so the tiebreak is verified against
real data:

```
#5  id 5737426522 (20260918-2329-zbmn) < id 5737450441 (20260918-2332-e7c4)
#11 id 5739467938 (20260919-0451-6421) < id 5739479618 (20260918-2332-e7c4)
```

The tool `tooling/claims/audit_claims.py` reports collisions and names the
winner; its tests reproduce both incidents. It is deliberately **not** a CI
gate: it needs issue state, so it is tier 1 by `TEST_VALIDATION_SPEC.md` § 3 and
must not be wired into `tooling/gates/run_all.py` (the same reasoning as G-E7's
`SKIP`).

**Rejected: distinct PATs.** Measured — `GITHUB_TOKEN` and `ALL_REPOs_GH_TOKEN`
both resolve to login `allenpd728`, id `26507447`. Separate tokens on one account
change nothing on GitHub's side: every comment, label change, and commit is
authored by the same user regardless of which token made the call. Distinct
*tokens* are therefore not a fix. Distinct *accounts* would make `assignee` and
comment authorship meaningful, but GitHub still offers no conditional write on
labels or assignees, so they would improve attribution without preventing the
race. **Rejected: shortening the stale window** — the #11 collision was ~2.5
minutes apart; any window short enough to catch that would expire legitimate
work. The defect is ordering, not timeout.

**What this does not fix, and the issue for it.** Detection happens at claim
time, but *both* sessions have claimed by then — the rule tells them who should
stop, it does not stop them. The structural fix is a real compare-and-swap, and
the only one available here is `git push` itself, which rejects a non-fast-forward
ref update. **#27** implements it: a claim becomes a committed file
`claims/<issue>.claim`, so the losing session is rejected at the push and stops
before doing any work. #27 is blocked by this entry so it changes a coherent
rule rather than one being rewritten concurrently.

**Procedural note.** The protocol's run-id mechanism *did* make both collisions
visible — the collision on #11 was found because the two claims carried distinct
run-ids. What it lacked was a rule that could act on what it revealed. That is
the gap this closes: the mechanism was sound, the check was wrong.

---

## DEC-030 — Adopt the program management spec; the outcome vocabulary separates instrument failure from phenomenon absence

**Date:** 2026-09-19 · **Status:** adopted

**Decision:** `docs/reference/PROGRAM_MANAGEMENT_SPEC.md` is **adopted** as the
authority for experiment program management. Its three classification axes
(issue kind, outcome class, rung), its append-only program ledger, its five
derived views, its emergent-requirement protocol, and the `G-M1` label-hygiene
gate become the standard. Issue #28 carries this decision.

**Why a second spec rather than an extension of DEC-021's.**
`TEST_VALIDATION_SPEC.md` gates the *evidence* — "is this artifact valid?" This
one tracks the *work* — "where is the program, and what does it need next?" They
fail separately: a repo can have perfectly gated artifacts and no idea what it
is doing, or a clear plan and invalid evidence. Ephapse has the first problem in
its primitive form and the second solved, which is why the two are adopted
separately.

**Why now, measured.** At `cc09eb6`: **8 of 15 open issues carried no `status:`
label** despite `MULTI_AGENT_WORKFLOW.md` § Task states requiring one; no issue
carried a *kind*, so "build a gate", "fix a bug in a gate", "we found a hole",
and "a human must decide" were indistinguishable; `findings.jsonl` classified
outcomes by `verdict` and a free-string `kind` but not by what they mean for the
program; 7 result JSONs sat unindexed with no traversal to their findings or
DECs; and the state of the program was only readable by reading 26 DECs across
1,217 lines, 15 issues, and 4 findings.

The measurement that settles the case: **the tree drifted while the analysis was
being written.** Two further issues were filed by a parallel session during it
(#26, #27) and one arrived unlabelled. A program view that must be re-measured
by hand to be trusted is the gap, not a caveat on it.

**The load-bearing decision, and the reason this needed a DEC rather than a doc
edit: the outcome vocabulary separates `instrument-failed` from
`phenomenon-null`.**

Those two look identical in a log — both read "no significant result" — and mean
opposite things. One says *the apparatus is broken, repair it*; the other says
*the world is empty here*. DEC-023, DEC-024, and DEC-025 are the record of this
project discovering that the same null was one, then the other, then
adjudicating between them across three entries. A vocabulary that cannot express
the distinction at a glance will keep costing that rediscovery.

The consequence is concrete and testable: issue #33's backfill gives #5 and #7
**two records each with opposite outcomes** (`instrument-validated` for the
original #5 control, `instrument-failed` for the rerun under corrected
thresholds; `instrument-failed` for #7 under DEC-020, revised by DEC-025). If
the vocabulary cannot carry that, it is the wrong vocabulary.

**Why this is not a second source of truth.** The ledger holds **only** what
GitHub cannot express: the outcome classification, the rung, and the traversal
links between results, findings, and decisions. It does not copy issue titles,
statuses, assignees, or priority. This is the direct application of Maith's
coverage-map decision — a stored copy drifts, a derived view cannot. Every view
in §5 is therefore computed, never stored.

**Also adopted:**

- **`kind:` labels as an axis orthogonal to `status:`.** `status:` says where a
  task is; `kind:` says what sort of work it is. Seven values: `experiment`,
  `gate`, `repair`, `defect`, `gap`, `decision`, `protocol`. `repair` and
  `defect` are separate because #15 repairs files against gates that work while
  #24 repairs gates that do not — conflating them hides which side of the trust
  boundary is broken. `decision` is a kind rather than a status because
  `status:blocked-needs-input` says "this is stopped" while `kind:decision` says
  "this is a judgment, and stopping is correct".
- **The rung reuses `TEST_VALIDATION_SPEC.md` §5 verbatim** rather than defining
  a parallel scale.
- **The emergent-requirement protocol.** #23, #24, and #25 were all discovered
  mid-task and filed ad hoc. The rule that makes it affordable: an agent filing
  an emergent issue does not have to solve it — the discovery is the deliverable.

**What is deliberately excluded**, so it is not re-proposed: no second source of
truth for task state; **no LLM in any gate or view** (DEC-021's §8 is binding —
a non-deterministic gate is not a gate); no promoted-findings database; no
burndown or velocity metric, because the work is not uniformly sized and such a
metric would measure the estimator rather than the progress.

**The cap, stated plainly.** This layer records *that* a judgment was made and
*what it rested on*. It cannot make the judgment. `TEST_VALIDATION_SPEC.md` §7's
Layer 4 is irreducible for the reason PleaNP gives: satisfaction is not internal
to the system. The ledger shortens the human's queue and makes the traversal
auditable; it does not shrink the judgment.

**Consequences.**

- The `kind:` labels exist in the repo (created by run `20260918-2332-e7c4`).
- `docs/AGENT_HANDOFF.md` gains a **Program management** section stating the
  three axes and the ledger's existence.
- The spec's `Status` line flips from proposal to adopted, citing this DEC.
- #29–#34 unblock in dependency order.
- **A note on the filing itself, recorded because it is the argument for
  `G-M1`.** Filing the six dependent issues produced the exact illegal
  dual-status state `MULTI_AGENT_WORKFLOW.md` §1a says the sweep must repair —
  two `status:` labels on one issue — and it was fixed within the same session.
  That is a ninth label-hygiene violation, in the session that proposed the gate
  to prevent them. The rule is easy to state and easy to violate by hand, which
  is why §7 makes it a gate rather than a convention.

---

## DEC-031 — The claim lock is a git-ref compare-and-swap; the label is visibility only

**Date:** 2026-09-19 · **Status:** adopted (#27 closed; corrects
`MULTI_AGENT_WORKFLOW.md` § 4)

**Decision:** the authoritative claim lock is a committed file,
`claims/<issue>.claim` containing `<run-id> <UTC timestamp>`, taken and released
through `tooling/claims/claim.py`. `git push` is the compare-and-swap: a
non-fast-forward ref update is rejected, so whichever push lands first owns the
issue. The `status:claimed` label and the claim comment are retained for
**visibility only**. Where the file and the label disagree, **the file wins**.

**Rationale — GitHub offers no conditional write, so a label cannot lock.**
DEC-029 fixed the *detection* of duplicate claims and made them deterministically
resolvable, but by then both sessions have already done the work. Prevention
needs a real compare-and-swap, and the issue API does not have one:

| Mechanism | Why it cannot lock |
|---|---|
| Labels | Last-write-wins. Two sessions can both `POST status:claimed`; neither is rejected. |
| Assignees | Multiple assignees are permitted, and there is no conditional form. Also useless here: both sessions are the same account (`allenpd728`, id `26507447`). |
| Comments | Append-only and unordered for this purpose; DEC-029's earliest-id rule orders them only after the fact. |

`git push` does have the property, is already relied on throughout this repo,
and costs nothing new. One file per issue number, so two *different* claims never
touch the same path and cannot conflict beyond the single file.

**Measured, not assumed.** `tooling/claims/tests/test_claim_cas.sh` builds a
scratch bare remote and two clones and races them at the same claim. It asserts
exactly one winner; the loser's exit code is `2` (distinct from error), the loser
leaves no claim on the remote, and **the loser's working tree is clean** — it
genuinely did no work. Stable across repeated runs (5/5 identical). The suite
also covers the negative directions, since a check that cannot fail is not a
check: idempotent re-claim, a live foreign claim refused without touching the
remote, a *stale* claim correctly reclaimed (the § 1 window still works), and
`release` refusing a claim held by another run-id.

**Exit-code contract.** `0` = you hold it; `2` = you **lost the race** (back off
and pick other work); `1` = a real error. Losing is distinguishable from breakage
without parsing output. `2` is not a failure — losing a race is the system
working.

**Why the file is authoritative rather than a second opinion.** The defect this
removes is *two sources of truth for who owns an item*. Keeping the label as a
peer would reintroduce it, so the protocol now states the precedence explicitly.

**Rejected, recorded so it is not re-proposed: distinct PATs.** Measured —
`GITHUB_TOKEN` and `ALL_REPOs_GH_TOKEN` both resolve to login `allenpd728`, id
`26507447`. Separate tokens on one account change no API semantics: every
comment, label change, and commit is authored by the same user regardless of
which token made the call. Distinct *accounts* would make `assignee` and
authorship meaningful but still provide no conditional write, so they would not
prevent the race either — they improve attribution, not exclusion. **Rejected:
shortening the stale window** — the #11 collision was ~2.5 minutes apart, and any
window tight enough to catch that would expire legitimate work. The defect was
ordering, not timeout.

**Cost and limits.** The lock needs git and network, so it is tier 1 and must
not be wired into the tier-0 CI runner. `audit_claims.py` is retained rather than
retired: it covers claims made before the lock existed, offline or scratch
contexts, and the case where a label exists with no claim file — and it remains
the tiebreak when the CAS is unavailable.

**Process note.** This entry was written after two rebase collisions cost two
renumbers of DEC-029. Two sessions editing the same ascending log is itself a
serialization problem of the same family; the claim-file mechanism does not help
there, because the log is a single shared file by design. Worth watching, but not
fixed here.

*Supersedes the label-as-lock framing in DEC-029 § 4; DEC-029's detection rule
and earliest-id tiebreak remain in force.*
