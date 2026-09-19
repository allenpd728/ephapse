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
  above**; rungs 0–2 are observations. Rung 4 is not reachable by an agent.

