# Prior art and technique review

**Compiled:** 2026-09-18 · **Status:** reference, updated as findings land

This is the field check Ephapse needs before the first probe, in the spirit
of Maith's `LITERATURE_REVIEW` practice. It is not a bibliography — it is
organized around one question: **is Ephapse's core signal actually
surprising, and does an existing method already detect it?**

Read §1 first. It changes what issue 3 should be.

---

## 1. The core premise check

Ephapse's premise is that cross-domain co-activation is a distinctive,
low-base-rate event that flags something worth a human's attention. The
literature does not support the "low-base-rate" half of that.

**Feature universality is established, not hypothesized.** Lan et al.
(arXiv:2410.06981, *Sparse Autoencoders Reveal Universal Feature Spaces
Across Large Language Models*) find a high degree of similarity in SAE
feature spaces *across different models*, with semantically coherent
subspaces (emotions, calendar, people) even more similar than individual
features. Anthropic's *Towards Monosemanticity* reports the same
universality result: SAEs applied to different transformers produce mostly
similar features, more similar to each other than to their own model's
neurons.

**Co-occurrence is already a measured baseline.** Clarke (PIBBSS Symposium,
*Examining Co-occurrence of SAE Features*) reports that SAE features
co-occur more often than chance even in large SAEs, with co-occurrence
becoming rarer in larger SAEs because of feature splitting, and that
co-occurring features tend to jointly map interpretable subspaces (days of
the week, position in a URL).

**Consequence for Ephapse.** "Two unrelated inputs activate the same
feature" is close to what you should expect *by default*. The interesting
object is not co-activation. It is **co-activation that survives a filter
designed to kill the boring cases**. §2 and §3 supply that filter.

This is a reframing, not a refutation: a filter that produces a small,
well-characterized residue is still a usable candidate generator. But issue
3 as currently written ("check whether any SAE feature co-activates more
than a random baseline") will succeed trivially and prove nothing.

---

## 2. A close prior method — adopt it rather than reinvent it

The nearest existing work is the *Towards data-centric interpretability
with sparse autoencoders* line (LessWrong). It uses SAE latents as per-sample
labels and searches for **feature pairs that co-occur more than expected**,
with two refinements Ephapse needs:

1. **Filter on NPMI, not raw co-occurrence.** Candidate pairs are selected
   at `NPMI > 0.8` **and** semantic similarity `< 0.2`. The second clause is
   the important one: it explicitly excludes pairs whose features are
   semantically similar to each other, which is the naive confound.
2. **Validate against injected ground truth.** They inject known
   correlations into a background corpus (the Pile, ~10k samples) and check
   whether the method recovers them — down to a signal present in as few as
   10/10k samples — and compare against an LLM-judge baseline, which
   recovers them only unreliably.

That second point is the single most transferable methodological result in
this review. It converts "did we find something?" into "does our detector
find things we know are there?" — a **positive control**. Ephapse's issue 3
currently specifies only a null baseline, which can tell you your detector
is too permissive but not whether it works at all.

**Related technique:** *Activation Pattern SVD* (LessWrong) proposes
decomposing an `M features x N contexts` activation matrix by SVD to reduce
interpreting `M` activation patterns to interpreting `K` prototypes. Useful
if the flag rate turns out to be high: it gives a way to group the residue
rather than reading feature dashboards one at a time.

---

## 3. How much of an SAE feature set is real

A quantitative anchor for the multiplicity problem flagged in DEC-005:

*Which Sparse Autoencoder Features Are Real? Model-X Knockoffs for False
Discovery Rate Control* (arXiv:2511.11711) reports that **approximately 25%
of highly active SAE features from a single layer genuinely encode
task-relevant information, while 75% represent noise or spurious
correlations**, and concludes that naive feature analysis will be dominated
by false positives.

That is for *task-relevant* features on a specific task, so it is not a
direct estimate of Ephapse's false-positive rate. But it establishes the
order of magnitude for the problem: at 10^5 features, an unfiltered search
returns mostly noise. It also supplies the right statistical tool — FDR
control — which is the same family as the BH-FDR correction already
specified in the handoff doc.

---

## 4. Failure modes that bias the search in *both* directions

**Feature absorption** (Chanin et al., arXiv:2409.14507, *A is for
Absorption*) is the most consequential failure mode for this project.
A parent feature is "absorbed" by child features and stops firing on inputs
where it should. The authors show it occurs in every tested model, that the
rate increases with sparsity and SAE width, that it is robust to
hyperparameter tuning, and that it may be a structural consequence of the
sparsity objective rather than a fixable bug.

**Why this matters more here than it looks.** Absorption produces false
*negatives*. If a genuinely cross-domain feature has been absorbed, the
detector sees nothing — and Ephapse would record a null. So a null result
does not cleanly mean "no cross-domain structure exists at this scale"; it
may mean "the SAE cannot represent the structure we're looking for." The
handoff doc currently treats a null as straightforwardly informative, which
is only half right. Any null writeup must note the absorption caveat.

**Feature splitting** goes the other way: one coherent feature splits into
several finer ones as SAE width grows, so the same underlying structure can
appear as a *cluster* of partially-overlapping features rather than one
feature. This inflates apparent overlap and, per Clarke above, becomes
rarer-but-still-present in larger SAEs. Practical consequence: a
"co-activating pair" may be one split family, and should be clustered
before being treated as two independent hits.

**Polysemantic and catch-all features** remain the dominant naive confound,
already covered in the handoff doc's checklist. The activation-histogram
test (broad-and-weak firing is a red flag) is the right first screen.

---

## 5. The intervention test is weaker than it looks — revising an earlier recommendation

The handoff doc says "correlation triages; intervention evidences," and an
earlier session recommended ablation/steering changing behavior in both
domains as the evidence bar. **That recommendation needs to be qualified**,
because the intervention literature is considerably less encouraging than it
implies.

- *Understanding (Un)Reliability of Steering Vectors in Language Models*
  (Braun et al., arXiv:2505.22637) finds high variance across samples and
  effects that are frequently *opposite* to the intended direction; all
  prompt types tested produced net-positive but noisy effects. The
  conclusion is that vector steering is unreliable unless the target
  behavior is represented by a coherent linear direction — and some
  concepts are effectively "anti-steerable."
- Tan et al. (NeurIPS 2024, *Analyzing the Generalization and Reliability of
  Steering Vectors*) similarly find many behaviors unsteerable even after
  sweeping layers and strengths, and that effectiveness is strongly
  input-dependent.
- *Polysemantic Interference Transfers* (ICLR 2026) shows directly on
  **Pythia-70M and GPT-2-Small** — Ephapse's exact target models — that
  intervening on one SAE feature interferes with semantically unrelated
  features, with transfer across feature-direction steering, token-gradient
  steering, and prompt injection.

**Revised guidance.** Intervention is still the right evidence bar, but
specify it as: (a) prefer **ablation** over additive steering, since the
unreliability results are mostly about additive/contrastive steering; (b)
require **in-distribution** contexts, since out-of-distribution steering is
where the failures concentrate; (c) include an **interference control** —
verify the intervention doesn't move unrelated features' behavior, per the
Pythia-70M/GPT-2-small interference result; and (d) treat a failed
intervention as *inconclusive*, not as evidence against the feature, given
the anti-steerability finding.

---

## 6. Does the substrate even contain the structure? (the math-specific risk)

This is the section that should most temper expectations, and it has no
equivalent in the handoff doc.

*Arithmetic Without Algorithms: Language Models Solve Math with a Bag of
Heuristics* (arXiv:2410.21272) performs causal circuit analysis on
arithmetic in several LLMs and finds that models implement **neither a
robust algorithm nor pure memorization**, but a "bag of heuristics" —
~1.5% of neurons in key MLP layers suffice for ~96% of arithmetic accuracy,
each neuron acting as a memorize-and-trigger rule keyed on operand patterns.
The authors state explicitly that this suggests improving mathematical
ability may require fundamental changes to training and architecture rather
than post-hoc techniques like activation steering.

**Implication for Ephapse.** If the model's arithmetic is a bag of
memorized heuristics rather than an algorithmic structure, then a
cross-domain co-activation found on math-adjacent inputs may be two
*heuristics* sharing a trigger pattern — not a shared mathematical concept.
That is the single most likely way for this project to produce a plausible
artifact. Any flagged pair involving numerical or arithmetic input needs to
be checked against the heuristic explanation before a human spends time
articulating it as a claim.

The more encouraging adjacent result is grokking work (Nanda et al.,
arXiv:2301.05217), which *does* find clean, interpretable, algorithmically
structured circuits for modular arithmetic — but in small models **trained
on that specific task**, not in pretrained general models. That is a
material difference from Ephapse's setting: it suggests clean mathematical
structure in activations is most reliably found in models trained on
structured tasks, which argues for probing a task-trained model eventually
rather than a general-purpose Pythia checkpoint. Note this as a possible
direction, not a current capability.

---

## 7. Cross-domain hypothesis generation: the older field Ephapse sits in

The idea of detecting structural correspondence between unrelated domains to
generate hypotheses is decades old and has its own literature.

- **Literature-based discovery / Swanson's ABC model.** Swanson's
  ARROWSMITH system takes two disjoint document corpora *A* and *C* and
  lists bridging terms common to both, for a human to assess. This is
  structurally the same pipeline as Ephapse's handoff interface (automated
  candidate surfacing, human articulation), applied to text rather than
  activations. Bisociative LBD work extends this with word embeddings.
- **Analogical search engines.** Kang et al. (*Augmenting Scientific
  Creativity with an Analogical Search Engine*, ACM TOCHI 2022) build
  retrieval and mapping over scientific corpora explicitly for
  cross-domain analogy, and report that structural (not surface) similarity
  is what makes an analogy useful.
- **Embedding-geometry analogy discovery.** The `rudybear/cross-domain-analogy`
  repository discovers structural analogies between disconnected domains
  using transformer embedding geometry, runs on CPU, and scores candidates
  by `surprise = structural_similarity x semantic_distance` — deliberately
  the same shape of objective as an "unrelated domains, shared structure"
  detector.

**Positioning consequence.** Ephapse's distinguishing feature is *substrate*:
it operates on internal activations and SAE features rather than on text or
output embeddings. That is a real difference, but it is a difference in
where the signal is read out, not a new idea about cross-domain search. Per
the repo's own "what counts as a result," this is a positioning note, not a
novelty claim. It also means there is existing evaluation practice to borrow:
the `surprise` construction (high structural similarity, high semantic
distance) is a better candidate-ranking objective than raw co-activation
magnitude, and it is already the field's convention.

---

## 8. A metric caution: cosine similarity may be the wrong geometry

Ephapse's screens will naturally reach for cosine similarity between feature
vectors or activations. Park, Choe & Veitch (*The Linear Representation
Hypothesis and the Geometry of Large Language Models*, ICML 2024) show that
the geometry in which concepts behave linearly is **not** the naive
Euclidean one — they derive a specific (non-Euclidean) causal inner product
that respects the counterfactual structure of concepts. The follow-up
(*The Geometry of Categorical and Hierarchical Concepts*, ICLR 2025) extends
this to categorical concepts as polytopes and proves a relationship between
them.

Practical upshot: cosine similarity in the raw basis is a defensible
*triage* metric but should not be treated as a semantic-similarity
measurement without acknowledging the assumption. Where a similarity
threshold does real work (e.g. the `semantic similarity < 0.2` filter in
§2), state which geometry and which vectors are used.

---

## 9. Causal abstraction: a strengthening for the receiving pipeline, not a risk to it

**Corrected 2026-09-18 — an earlier version of this section over-claimed.**

This section previously warned that Maith's gate 1 could be passed vacuously,
citing Sutter et al. (*The Non-Linear Representation Dilemma*, arXiv:2507.08802,
NeurIPS 2025 spotlight), who prove that causal-abstraction analyses become
vacuous when the alignment map is arbitrarily expressive — 100% interchange
intervention accuracy on randomly initialized models that cannot perform the
task.

**That warning did not apply.** Maith's gate 1 is a written Lean obligation
(`AXIOM_DISCOVERY.md` §Validation pipeline: *"Prove φ(x ∘ y) = φ(x) ⊕ φ(y)…
Fails to typecheck → candidate dead"*). Its complexity is fixed by the term a
human wrote; it is not a learned, fitted, or capacity-selected map. Sutter's
result is about *learned* alignment maps (DAS-style), where map capacity is
what makes the test vacuous. Maith's gate 2 also already rejects the
Unit-collapse degenerate case by name.

**The properly-aimed version.** The causal-abstraction literature is worth
borrowing *for* Maith, not warning about:

- **Geiger et al., *Finding Alignments Between Interpretable Causal Variables
  and Distributed Neural Representations*** (arXiv:2303.02536) — distributed
  alignment search and interchange intervention accuracy (IIA), a graded
  metric for "does this map preserve structure?"
- **Causal abstraction in model interpretability: a compact survey**
  (arXiv:2410.20161) — the unified framing over causal scrubbing, DAS, and
  related intervention methods.
- **Sutter et al.** (arXiv:2507.08802) — useful not as a warning but as the
  boundary condition: it tells you *when* a structure-preservation test
  carries information, which is the question gates 1–2 ask.

Maith's gates 1–2 test whether a map preserves structure. That is the same
question causal abstraction formalizes, with a graded metric and known theory
about its failure conditions. The borrowable value is a sharper statement of
what gate 2's kernel characterization should establish — in particular for a
non-injective φ into a target with weak operations, where the homomorphism law
can hold for uninteresting reasons.

**No change to Ephapse follows from this.** Recorded because the interface is
created by this repo's handoff and the correction belongs on the record.

---

## 10. What this means for the issues

**Issue 3 should be re-specified**, not just executed. Concretely:

1. Replace the "random baseline" with **both** a null *and* a positive
   control: inject a known cross-domain correlation into a background
   corpus and confirm the detector recovers it (§2). Report recovery rate
   as a function of injection rate, as the reference work does.
2. Adopt the **NPMI + semantic-distance** filter as the primary screen
   (§2, §7), rather than raw co-activation magnitude.
3. Cluster co-activating features before counting them as independent hits,
   to control for splitting (§4).
4. Rank surviving candidates by a **surprise**-style score (structural
   similarity x semantic distance) rather than activation magnitude (§7).
5. Report the **absorption caveat** on any null result: a null may reflect
   SAE representational limits rather than absence of structure (§4).
6. For any numerical/arithmetic pair, explicitly test the **bag-of-heuristics**
   explanation before promoting it (§6).

**New issue warranted:** a detector validation task — the injected-correlation
positive control — which must run *before* issue 3, since issue 3's
interpretation depends on the detector's measured recovery rate.

**A possible future direction, not a current one:** probe a task-trained
model (per the grokking circuit results) rather than a general-purpose
checkpoint, if pretrained-model probing proves structurally empty.

---

## Sources

| Topic | Reference |
|---|---|
| Feature universality across models | arXiv:2410.06981 (Lan et al.); Anthropic, *Towards Monosemanticity* |
| SAE feature co-occurrence | Clarke, PIBBSS Symposium, *Examining Co-occurrence of SAE Features* |
| NPMI + injected ground truth method | LessWrong, *Towards data-centric interpretability with sparse autoencoders* |
| Activation pattern SVD | LessWrong, *Activation Pattern SVD* |
| FDR control / how many features are real | arXiv:2511.11711 (Model-X Knockoffs) |
| Feature absorption / splitting | arXiv:2409.14507 (Chanin et al.) |
| Steering unreliability | arXiv:2505.22637 (Braun et al.); Tan et al., NeurIPS 2024 |
| Polysemantic interference (Pythia-70M, GPT-2-small) | ICLR 2026, *Polysemantic Interference Transfers* |
| Arithmetic as bag of heuristics | arXiv:2410.21272 |
| Grokking circuits | arXiv:2301.05217 (Nanda et al.) |
| Cross-domain analogy / LBD | Swanson ABC model & ARROWSMITH; Kang et al., ACM TOCHI 2022; `rudybear/cross-domain-analogy` |
| Representation geometry | Park, Choe & Veitch, ICML 2024; Park et al., ICLR 2025 |
| Causal abstraction vacuity | arXiv:2507.08802 (Sutter et al.) |
