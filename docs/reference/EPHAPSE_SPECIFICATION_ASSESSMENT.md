# Assessment: the "Cross-Domain Synthesis & Latent Novelty Discovery Engine" spec

**Status:** assessment, drafted 2026-09-19 (run `20260918-2332-e7c4`). Input to
DEC-033. The reviewed document was authored outside this repo and is **not** an
adopted approach — this file records what was taken, what was rejected, and what
was postponed.

**Reviewed:** an external v1.0.0 system spec titled *Project Ephapse —
Cross-Domain Synthesis & Latent Novelty Discovery Engine*: a four-stage pipeline
(candidate generation → "Contamination Shield" → multi-domain feasibility matrix
→ "Innovation Vault") feeding a commercial **Innovation Asset Inventory** sold to
B2B enterprise clients, under a **Zero-Synapse Mandate**.

**Verdict in one line.** The *engineering* proposals are largely things this repo
already does better or has already declined; the *framing* is a direction the
repo is explicitly not authorized to pursue. Two ideas are worth taking, and one
question it raises — how a negative verdict gets revised — is the right question
and is answered by a new document, not by this spec.

---

## 1. What this repo actually looks like now

The assessment only makes sense against the current state, so it is stated first.

| Fact | Where |
|---|---|
| The method proof-of-concept is **complete and negative**. The cross-domain probe found no feature co-activating across the two domains above a family-wise cutoff, with a *recovering* positive control and mechanically-verified token-disjoint inputs. | DEC-027 |
| The honest reading of that null: **the method has poor signal-to-noise at 70M**, not that cross-domain structure is absent. Feature absorption is the primary alternative explanation. | DEC-027; PRIOR_ART §4 |
| **Four plausible-looking statistics in four issues could not fire** — the model target, the multiplicity correction, a per-feature threshold, and a raw co-activation-rate cutoff. Only the positive control caught each. The stated working rule: *a family-wise cutoff over an unstandardized statistic is the recurring bug.* | DEC-016, DEC-023, DEC-027 |
| One **weak bridging** signal exists, on a *constructed* related pair (verbal ↔ symbolic), not on arbitrary unrelated domains. | #6; findings.jsonl |
| The only ladder in the repo is the **claim** ladder (rungs 0–5), and rung 3 is not currently reachable at this scale. | TEST_VALIDATION_SPEC §5; DEC-020 |
| A general-purpose, non-mathematical cross-domain hypothesis-generation pipeline was **already reviewed and declined**, for having no validation oracle and for being the expensive substitute for the one Maith has. | DEC-012 |
| The repo is **"not authorized to claim a discovery is novel or valid"** on the strength of anything computed here. | README |
| The field is mapped: Swanson's ABC, analogical search engines, embedding-geometry analogy. Ephapse's differentiator is **substrate** (activations, not text), and `surprise = structural_similarity × semantic_distance` is **already the field's convention** for ranking cross-domain candidates. | PRIOR_ART §8 |

Two of those matter more than the rest. **DEC-012 already declined this shape of
project**, and **PRIOR_ART §8 already positions Ephapse within the field the
spec believes it is inventing.**

---

## 2. Rejected — and why each rejection is structural, not stylistic

### 2.1 The commercial framing (B2B IP marketplace, "Innovation Asset Inventory")

**Rejected.** This is the one rejection that is not about engineering.

The spec's end product is a saleable asset inventory for enterprise clients. This
repo's stated epistemic position is the opposite: it surfaces *candidates for a
human*, and it is *not authorized to claim a discovery is novel or valid*. An
"asset" implies a claim of novelty and validity; the repo's entire validation
layer exists because it cannot make that claim (TEST_VALIDATION_SPEC §8 excludes
"candidate-quality" judgments outright).

Adopting the commercial framing would not require new infrastructure — it would
require the repo to assert things its own gates are built to prevent it from
asserting. That is a values conflict, not a feature gap, and it is why this is
rejected rather than postponed.

### 2.2 The "Zero-Synapse Mandate" as the primary filter

**Rejected, and it inverts the actual problem.**

The mandate filters candidates on **commercial and bibliographic novelty** —
reject if cosine similarity to an existing patent exceeds 0.65, or if the
knowledge-graph path between two concepts is ≤ 3.

But this repo's measured problem is the **opposite**: cross-domain co-activation
fires *too much*. SAE feature universality makes overlap the near-default
(DEC-006), and the repo has spent five issues building filters that kill *boring*
co-activation — NPMI, a decoder-cosine semantic-distance screen, clustering for
feature splitting, paraphrase invariance, and a standardized family-wise cutoff.
A filter keyed to *commercial precedent* addresses a problem this substrate does
not have.

Two further problems:

- **It re-opens DEC-012.** A pipeline whose first stage generates cross-domain
  candidates and whose last stage produces a novelty-graded inventory is the
  declined project with a different first stage. DEC-012's reasoning applies
  unchanged: no validation oracle, and the apparatus substitutes for one.
- **It asserts novelty.** Certifying that a candidate has no precedent is exactly
  the claim README says this repo may not make. The repo's version of the same
  instinct already exists and is *weaker and more honest*: it does not certify
  novelty, it declines to describe rungs 0–2 as findings at all.

### 2.3 The four-stage pipeline and the "Innovation Vault" as specified

**Rejected as specified; the vault idea is postponed separately (§4.1).**

Stage 3's feasibility matrix (technology maturity, economic viability,
regulatory friction) evaluates candidates for *commercial* readiness. The repo
has no candidates — zero human-reviewed co-activation events exist, and the
general probe is a null. Building a grading matrix for an empty set is precisely
the failure mode this repo and Maith both name: **infrastructure ahead of
results.** The README's own "what not to build yet" section forbids it, and
Maith's history is the citation.

### 2.4 The asset-inventory schema

**Rejected.** `asset_id`, `codename`, `maturity_version`, `utilization_state`,
`readiness_grade` — a warehouse schema for contents that do not exist. If a
candidate is ever surfaced, the program ledger (PROGRAM_MANAGEMENT_SPEC §4) is
where its record belongs, and that schema is already specified with enforced
append rules. A second schema for the same concept is the drift the coverage-map
decision warns against.

### 2.5 The Python contamination shield

**Rejected — it is cruder than what is already in the repo.**

`verify_hypothesis_purity()` queries a vector DB for a max cosine and walks a
knowledge graph for a shortest path. Against what exists:

| Spec's shield | What the repo has |
|---|---|
| Max cosine > 0.65 → reject | NPMI > 0.8 **and** decoder-cosine semantic distance < 0.2, both required |
| No multiplicity handling | BH-FDR (analytic) *and* a max-statistic permutation cutoff, with the DEC-016 finding that one is structurally unable to fire at low `N_PERM` |
| No positive control | A mandatory constructibility check and a known-positive test — DEC-019 exists because four statistics looked plausible and could not fire |
| Graph path ≤ 3 → reject | Not applicable: the repo's inputs are activation vectors, not a citation graph |

The one genuinely useful line in it — rank by `structural similarity × semantic
distance` — is **already the field's convention** (PRIOR_ART §8), already
recommended for adoption, and *not* the spec's invention.

---

## 3. Rolled in — two ideas, both small

### 3.1 "Index the asset by the frictions it obliterates, not its features"

**Rolled in as a candidate input to the repo's deepest open problem.**

This is the most valuable line in the reviewed document, and it is valuable for a
reason the document does not claim: it is a *candidate answer* to the base-rate
problem.

PRIOR_ART §11 states that problem precisely — a causally load-bearing shared
feature can be **uninteresting** ("both inputs involve counting" is causally real
and mathematically vacuous), and this *resists technical solution*: "Ephapse can
make a candidate credible but never interesting; interestingness is the human's
call."

"Frictions obliterated" is a concrete way for the human to phrase *why* a
cross-domain match might matter, in a form that is domain-general rather than
mathematical. It does not solve the base-rate problem and is not proposed as a
gate. It belongs in PRIOR_ART §11 as a **referenced candidate input to the human
step**, labelled as such.

### 3.2 Independent arrival at the same wall

**Rolled in as a citation, not a claim.**

The spec's rationale for its translation layer — "radical innovation circumvents
explicit consumer requests" — is an independent statement of the same difficulty
PRIOR_ART §11 describes from the mathematical side. Two documents reaching the
same wall from different directions is weak evidence that the wall is real, and
that is worth one sentence where the wall is documented.

---

## 4. Postponed — real ideas that need results first

These are not rejected. They are **conditioned on something the repo does not
yet have**, and the condition is stated so they are not re-proposed as
immediately actionable.

### 4.1 The Vault / time-capsule idea — postponed on a stated condition

**What is worth keeping:** a candidate that fails *for a specifiable, fixable
reason* should be stored with that reason attached, so a later change in
circumstances re-opens it automatically rather than requiring rediscovery.

**Why it is the best transferable idea here:** this repo has an *exact* instance
of that situation already. DEC-020 and DEC-025 established that rung-3
per-feature causal claims are **not reachable at 70M** — a failure with a named
and changeable cause (model scale, or intervention scale). That is a vaulted
candidate in everything but name.

**The condition:** it needs a *candidate*. There are none. And the mechanism it
needs already half-exists: PROGRAM_MANAGEMENT_SPEC §4's ledger carries
`blocks` and `outcome`, and `kind:gap` already means "capability missing,
design unsettled". A vault is arguably a `kind:gap` record plus a re-evaluation
trigger.

**Action now:** record the mapping in this assessment. **Do not** build a vault
subsystem. When the first candidate fails for a fixable reason, extend the ledger
then — the same discipline the program spec applies to its own open questions.

### 4.2 Hotspot-density search — postponed on a stated condition

**What is worth keeping:** re-allocating search toward the semantic neighbours of
*successful* results rather than searching uniformly. This is the rejector-density
idea from PleaNP applied to candidate proposals, and it is a plausible
efficiency gain.

**The condition:** it requires *successes* to be adjacent to. There are none —
DEC-027 is a null. Re-allocating search around an empty set is undefined.

**Secondary objection, recorded now:** it also assumes semantic proximity to a
success is informative about a *different* domain, which is the base-rate problem
again (§3.1), not a solution to it.

### 4.3 Multi-domain feasibility grading — postponed on a stated condition

Conditioned on there being candidates to grade, and on the grading criteria being
ones the repo may legitimately apply. Commercial readiness is not among them
(§2.1). A *technical* readiness assessment — "does the toolchain for this exist
at this scale" — is closer to the repo's own `kind:gap` and to DEC-020's
scale-dependence finding, and could be reconsidered in that narrower form.

---

## 5. The question the spec raises that is genuinely ours

The reviewed document assumes a project can move from "no results" to
"commercialized assets" along a single track. This repo's actual situation is
harder and more interesting: **its method has returned a negative verdict, and
the repo has no written account of what would revise that verdict.**

That is a real gap. DEC-027 states the null and its caveats; DEC-012 states a
declined direction; PRIOR_ART §11 states what decomposition cannot fix. But
nothing states **the conditions under which the current negative verdict would
change, what each such condition would cost, and what is independently valuable
about reaching each.**

That is what a rung ladder is for, and it is the recommendation in
[`docs/ROADMAP.md`](../ROADMAP.md) (new, with this assessment). The ladder is
deliberately **not** modelled on PleaNP's: PleaNP's rungs are a *construction*
ladder toward a known target, while Ephapse's method is complete-and-negative, so
its ladder must be a **verdict-revision ladder** — each rung being a
pre-specified reason the null might be wrong.

---

## 6. What was explicitly not done

- **The spec was not treated as an approach to adopt.** Its four stages, its
  mandate, and its schema are not implementation plans.
- **No pipeline was built.** No contamination shield, no feasibility matrix, no
  vault, no asset schema. Building any of them now would be infrastructure ahead
  of results.
- **No claim was made about the reviewed document's origin or intent.** It was
  read as a set of proposals and assessed on engineering and epistemic grounds.
- **The rejected items were not softened.** The commercial framing is rejected on
  this repo's stated position, not deferred for a later decision.

## 7. Consequences

| Item | Disposition |
|---|---|
| B2B commercial framing; asset inventory; marketplace | **Rejected** (README's own scope; DEC-033) |
| Zero-Synapse Mandate as primary filter | **Rejected** — inverts the measured problem; re-opens DEC-012 |
| Four-stage pipeline; feasibility matrix; vault *as specified* | **Rejected** as infrastructure ahead of results |
| Asset-inventory schema | **Rejected** — the program ledger already covers it |
| Contamination-shield code | **Rejected** — cruder than the existing detector; its good line is already field convention |
| "Frictions obliterated" framing | **Rolled in** — PRIOR_ART §11, as a candidate input to the human step |
| Independent arrival at the base-rate wall | **Rolled in** — one citation line |
| Vault / time-capsule | **Postponed** — conditioned on a first candidate |
| Hotspot-density search | **Postponed** — conditioned on a first success |
| Multi-domain feasibility grading | **Postponed** — conditioned on candidates, and narrowed to technical readiness only |
| "What would revise the negative verdict?" | **Adopted as a new document** — `docs/ROADMAP.md` |
