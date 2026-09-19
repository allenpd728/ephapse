# Roadmap: the verdict-revision ladder

> **Status:** proposal, drafted 2026-09-19 (run `20260918-2332-e7c4`). Input to
> DEC-033. Not yet adopted.
>
> **Why this is not PleaNP's ladder.** PleaNP's rungs are a *construction* ladder
> toward a known target — each rung builds a component, and the project is
> valuable at every rung regardless of whether the top is reached. Ephapse's
> method has already returned a verdict: the general cross-domain probe is a
> **clean null** at 70M (DEC-027). A construction ladder would be the wrong
> shape, because there is no next component to build. What the repo lacks is a
> written account of **what would change the verdict** — and that is what each
> rung below states.

## The shape of this ladder

Each rung is a **pre-specified reason the current negative verdict might be
wrong**, together with what it would cost and what is valuable about reaching it
even if the verdict stands.

Three properties, borrowed from PleaNP because they are what make a ladder
honest rather than aspirational:

1. **Each rung is independently valuable.** Reaching rung *n* is a contribution
   whether or not rung *n+1* is ever attempted.
2. **Each rung states its falsifier.** A rung that cannot conclude negatively is
   not a rung; it is a wish.
3. **A rung may end the ladder.** If rung 3 concludes "no, scale does not help",
   that is a result, and rungs 4+ become moot for this method. The ladder is not
   a plan to reach the top.

And one the other ladders do not need:

4. **The out-of-scope note binds at every rung.** §4 states a direction the repo
   may not pursue. It applies at rungs 0–6 equally, so it does not have to be
   re-litigated each time a rung is attempted.

**The honest framing.** The most likely outcome of this program is **not** a
cross-domain discovery. It is: a validated method for reading model internals for
cross-domain structure, a negative result at the only scale reachable here, an
honest account of why that result is not decisive, and a reusable validation
layer. That is a real contribution — three issues (#5, #6, #3) and five
process decisions were spent learning that four plausible-looking statistics
could not fire, and that knowledge transfers to anyone probing small models.

---

## Rung 0 — Method validated

**Goal:** show the detector can detect. A positive control that recovers a signal
known by construction to be present.

**Deliverable:** an injected-correlation recovery curve, with a constructibility
check proving the planted signal reaches both feature groups.

**Status:** **Done** (DEC-017, DEC-018, DEC-024). The detector recovers the
injected signal; a naive raw-co-occurrence baseline recovers zero.

**Why it is independently valuable:** without it, every later null is
uninterpretable — a broken detector and an absent phenomenon look identical.

**Its falsifier:** the control does not recover. Then the method is not viable at
this scale and the ladder ends here. This is what actually happened, four times,
before the harness was right.

---

## Rung 1 — Surface-controlled signal

**Goal:** establish that any signal is not merely surface form. A co-activation
claim is a vocabulary claim until it survives paraphrase and zero-shared-token
controls.

**Deliverable:** a bridging statistic computed on inputs verified to share no
tokenizer ids.

**Status:** **Done — weakly positive** (#6, DEC-011). Six survivors against zero
under a shuffled null, on a *constructed* related pair (verbal ↔ symbolic).

**Why it is independently valuable:** the requirement is detector-side, not a
small-model artifact. If the SAE represents tokens well and relations poorly, the
detector's output is token-shaped at any scale, so this control is needed before
any scale-up can be interpreted.

**Its falsifier:** survivors equal the null. Then the detector reads tokens and
the ladder ends.

**Scope note, carried from #6:** this is a *related* pair, not arbitrary
unrelated domains. It establishes the control works; it is not evidence of
cross-domain bridging in general.

---

## Rung 2 — General cross-domain probe ← **current, concluded negatively**

**Goal:** run the method on genuinely unrelated domains, with the null model,
multiplicity correction, and confound checklist fixed in advance.

**Deliverable:** a result with a recovering positive control, mechanically
verified disjoint inputs, and a family-wise standardized cutoff.

**Status:** **Done — clean null** (DEC-027). 120 cooking and 120 astronomy
passages, zero shared tokenizer ids, positive control recovers at z 11.30,
real run finds **0 survivors**.

**Why it is independently valuable:** it is a *complete method
proof-of-concept*, with the two things a negative needs to be credible — the
instrument shown to work, and the inputs shown disjoint. It also retired a third
structurally-broken statistic (a raw co-activation rate with a family-max
cutoff), which is a transferable finding.

**The verdict, stated with its ceiling:** at 70M, with a bounded pre-specified
family, token-disjoint inputs, and a recovering control, **cross-domain
co-activation is not detected**. The honest reading is *poor signal-to-noise*, not
*absence of structure* — feature absorption produces false negatives and may be
structural to the sparsity objective (PRIOR_ART §4).

**Its falsifier:** the control fails, or the inputs share tokens. Both were
checked, so the null stands as a null.

---

## Rung 3 — Sensitivity at scale

**Goal:** test the primary alternative explanation for the rung-2 null — that 70M
is simply too small for the structure to be legible.

**The specific question:** does the rung-2 null survive at a scale where SAE
features are more monosemantic and reconstruction error is lower? The measured
reconstruction error at 70M is **0.362** relative (DEC-020), and a feature is one
of ~100 active at a token — a per-feature effect is below the noise floor by
construction.

**What it would cost — corrected by checking rather than assuming.**

The first draft of this rung claimed it was *blocked on SAE availability*, by
analogy with DEC-014 (which found no Pythia-160M release). **That was wrong, and
checking the registry contradicted it** — which is DEC-014's actual lesson: the
availability question must be answered by querying, never by assuming.

Measured via `get_pretrained_saes_directory()` on 2026-09-19:

| Model | Releases | SAEs (largest release) |
|---|---|---|
| `pythia-70m-deduped` (current) | 7 | 7 |
| `gemma-2-2b` | 8 | **316** (`gemma-scope-2b-pt-res`); 25 in `gemma-2-2b-res-matryoshka-dc` |
| `gpt2-small` | 18 | 12 per release, many hooks |
| `qwen3-4b`, `google/gemma-3-4b-pt`, `mistral-7b`, `qwen3-8b` | 1–8 each | 1–9 |
| `meta-llama/Llama-3.1-8B` | 7 | 7 |

So the scale-up target is **`gemma-2-2b`** — a 2B model, ~28× the current
parameter count, with both a Matryoshka residual release (25 SAEs, the closest
analogue to the current setup) and the Gemma Scope residual suite (316). This
makes rung 3 **feasible, not blocked.**

The real costs, stated honestly:

- **CPU feasibility is unmeasured.** A 2B model in fp32 is ~8 GB of weights, which
  is inside the sandbox's ~10 GB per-run budget (`SANDBOX_BASELINE.md`) but with
  little headroom for cached activations. Latency at 2B on 4 CPU cores is a
  measurement to take before designing the run, not an assumption.
- **The hook differs.** The current setup reads `blocks.3.hook_resid_post`; Gemma
  Scope's residual releases are keyed `layer_N/width_16k/...` and Matryoshka
  releases expose `blocks.N.hook_resid_post`. The family-wise statistic and the
  selectivity band must be re-derived for the new SAE, not copied.
- **Features are wider**, so the family is larger and the multiplicity correction
  must be re-pre-registered (DEC-016/DEC-018's parameters do not transfer
  silently).
- **The remote path remains unusable for this** (DEC-003): Neuronpedia and
  nnsight/NDIF return top-k and dashboards, never an arbitrary activation matrix,
  so the standardized family-wise statistic cannot be computed through them.
  Local CPU is the only path.

**Deliverable if attempted:** the rung-2 probe re-run at the largest scale with
real SAE coverage, same inputs, same control, same cutoff construction.

**Why it is independently valuable:** it converts "we could not see it at 70M"
into "we could not see it at scale *X*", which is a materially stronger negative —
and it would either validate or retire the scale explanation as the reason the
method found nothing.

**Its falsifier:** no larger model has usable SAE coverage, or the null
reproduces. Either outcome is a result. A reproduction at larger scale is
*stronger* evidence than rung 2, not a failure.

**Status:** not started. **Feasible, not blocked** — SAE coverage exists for
`gemma-2-2b` (316 SAEs in the Gemma Scope residual release). The open question is
CPU feasibility at 2B and re-deriving the statistic for a new SAE, both of which
are measurements to take rather than blockers to report.

---

## Rung 4 — Causal reachability

**Goal:** make the repo's strongest claim — "feature F is causally load-bearing in
both domains" — *testable* at whatever scale rung 3 settles on.

**The current obstruction, already measured:** DEC-020 found **0 of 50 features**
above the cause threshold at 70M, and DEC-025 showed the negative is a property of
the *measurement choice*, not of the features — single-feature intervention is
real on the logit scale at a feature's own token and invisible on a probability
scale at the output. Rung 3 per-feature causal claims are therefore **not
currently reachable**, which is why TEST_VALIDATION_SPEC §5 marks rung 3 of the
*claim* ladder as unreachable at 70M.

**Deliverable:** a causal measurement — Cause and Isolate, above the interference
control — at a granularity where a per-feature verdict is meaningful, or a
demonstration that no reachable scale permits one.

**Why it is independently valuable:** it is the difference between this repo
producing *correlations it declines to call findings* and producing a claim it is
allowed to make.

**Its falsifier:** no reachable scale or intervention design permits a
per-feature verdict. Then the repo's ceiling is the **aggregate** dose-response
ladder (DEC-020), which is a smaller but honest claim, and rung 5 becomes the
only remaining one.

**Status:** not started. Depends on rung 3's scale decision.

---

## Rung 5 — Interestingness (human-owned, and the reason the ladder has a ceiling)

**Goal:** nothing technical. This rung is the acknowledgement that **credibility
is not interestingness** and that the second is not a technical problem.

**The problem, stated where it was already documented:** a causally load-bearing
shared feature can correspond to something vacuous — "both inputs involve
counting" is causally real and mathematically empty (PRIOR_ART §11). This is a
**base-rate problem**, and it resists technical solution: "Ephapse can make a
candidate credible but never interesting; interestingness is the human's call."

**What has been added, and only this:** a candidate *framing* for the human step,
taken from the reviewed external spec — index a candidate by **the frictions it
obliterates rather than its features**. It is not a gate and cannot be one; it is
a way of phrasing *why* a match might matter that is domain-general rather than
mathematical (EPHAPSE_SPECIFICATION_ASSESSMENT §3.1).

**Why the rung exists at all:** it names the ceiling. A reader who expects the
ladder to terminate in a discovery should see, in the ladder itself, that the
last mile is a judgment this system cannot make.

**Its falsifier:** none — and that is the point. A rung without a falsifier is
appropriate only when it is explicitly a human step, which is why it is marked
here rather than left implicit.

**Status:** not reachable by an agent, at any scale. It requires a credible
candidate from rungs 2–4, and there is currently none.

---

## Rung 6 — Handoff to Maith (the terminus, and not this repo's to reach)

**Goal:** a human articulates a surfaced candidate as a plain-language
mathematical claim and passes it to Maith's gate 1.

**Status:** not reached. No candidate has been surfaced, so there is nothing to
hand off. This rung is listed for completeness: it is where the ladder *ends*,
and it is the only rung whose success is measured in another repo.

**Why it is listed rather than omitted:** it makes the interface explicit. This
repo's product is a *candidate*, not a result; the result belongs to Maith's
gate-3 survivors. Recording the terminus prevents this ladder from being read as
a promise of mathematical output.

---

## Out-of-scope at every rung

One direction must be foreclosed once, not re-argued per rung.

**This project does not certify novelty, and does not produce commercial assets.**

Two distinct prohibitions, both binding at rungs 0–6:

1. **Novelty certification.** README: the repo is "not authorized to claim a
   discovery is novel or valid" on the strength of anything computed here. The
   validation layer exists *because* it cannot make that claim
   (TEST_VALIDATION_SPEC §8 excludes candidate-quality judgments outright).
2. **Commercial framing.** An "Innovation Asset Inventory" sold to enterprise
   clients implies claims of novelty and validity this repo may not make. The
   reviewed external spec's marketplace, feasibility matrix, and asset schema are
   rejected on this ground
   (EPHAPSE_SPECIFICATION_ASSESSMENT §2).

A related direction was **already declined before this ladder existed**: a
general-purpose, non-mathematical cross-domain hypothesis-generation pipeline
(DEC-012), for having no validation oracle and for being the expensive substitute
for the one Maith has. That reasoning is unchanged, and it is why the reviewed
spec's pipeline is rejected rather than postponed.

---

## Rung summary

| Rung | Question | Status | Falsifier |
|---|---|---|---|
| 0 | Can the detector detect? | **Done** — yes | control fails |
| 1 | Is the signal more than surface form? | **Done** — weakly yes | survivors equal null |
| 2 | Does it fire across unrelated domains? | **Done** — clean null | control fails / inputs share tokens |
| 3 | Is the null a scale artifact? | Not started — **feasible** (`gemma-2-2b`, 316 SAEs) | null reproduces, or 2B is CPU-infeasible |
| 4 | Is a per-feature causal claim reachable? | Not started — depends on 3 | no scale permits a per-feature verdict |
| 5 | Would a candidate be *interesting*? | Not reachable — human step | none (explicitly) |
| 6 | Handoff to Maith | Not reached — no candidate | n/a (measured in another repo) |

**The ladder currently has one live rung (3), one conditional on it (4), and one
that is not an engineering problem at all (5).** That is an accurate picture of
where the method stands, and it is stated so the roadmap is not mistaken for a
plan to produce a discovery.
