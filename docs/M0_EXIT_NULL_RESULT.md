# M0 exit: the cross-domain probe's clean null

> **Status:** the milestone-M0 exit statement — concluding, not shipping.
> **Written:** 2026-09-23 (run `20260923-0701-2sqh`, issue #63).
> **Basis:** DEC-027 (the result), DEC-021 (the validation layer),
> DEC-020/DEC-025 (why rung-3 causal claims are unreachable here), and
> `findings.jsonl` record 5, run `20260919-0229-to3m`.

> **Terminology — read this first.** The project's status ladder reserves the
> word **"finding" for rung 3 and above** (`README.md`; `TEST_VALIDATION_SPEC.md` §7).
> The result below is a **rung-2 observation**: a clean null. This document is the
> written account the M0 exit asks for; it is not a "finding" in the repo's
> reserved sense, and it does not claim to be one. Nothing below is a
> mathematical result.

## 1. What was asked

The general cross-domain probe (issue #3) tested one hypothesis: **that two
unrelated input domains drive the same internal SAE features more than chance** —
that cross-domain co-activation is detectable in `pythia-70m-deduped`. The bet
behind the program is that such overlaps are a useful *candidate generator* for
mathematical hypotheses. The probe is the first test of whether the detector
produces anything to generate from at all.

## 2. What was measured

| Item | Value |
|---|---|
| Model | `pythia-70m-deduped` (DEC-014) |
| SAE / hook | `pythia-70m-deduped-res-sm`, `blocks.3.hook_resid_post` |
| Inputs | 120 cooking + 120 astronomy passages (median 18–19 tokens), **zero shared tokenizer ids** — the strict DEC-011 input gate, checked mechanically, not assumed |
| Statistic | per-feature standardized `z = (observed − perm_mean)/perm_sd`, family-wise cutoff after multiplicity correction |
| Positive control | a planted token at 10% of paired passages |
| Run | `20260919-0229-to3m` — `findings.jsonl` record 5, issue #3 |

The gate that makes the measurement meaningful is the **recovering positive
control**: without it, a broken detector and an absent phenomenon look identical
(DEC-017/DEC-024).

## 3. What the answer was

**A clean null.**

- **Positive control recovered** — best `z` **11.30** vs family-wise cutoff
  **4.47**, on the feature the planted token actually drives. The instrument
  worked.
- **Real run** — |family| = 793 (selectivity band [0.05, 0.60] in both domains),
  best `z` **3.10** vs cutoff **4.41**, **0 survivors**. The
  per-feature-threshold variant agrees (66 features, best `z` 3.37 vs 4.97,
  0 survivors).
- An earlier probe found a weak bridging signal on a *constructed* related pair
  (verbal ↔ symbolic, 6 survivors vs 0 under a shuffled null — DEC-011). That
  established the control works; it is **not** evidence of cross-domain bridging
  in general.

**The verdict, stated with its ceiling.** At 70M, with a bounded pre-specified
family, token-disjoint inputs, and a recovering control, **cross-domain
co-activation is not detected**. The honest reading is *poor signal-to-noise at
this scale*, **not** *absence of structure*: feature absorption produces false
negatives and may be structural to the sparsity objective (PRIOR_ART §4). That
caveat is the primary alternative explanation and is recorded on the
`findings.jsonl` record.

## 4. What would change it

**Rung 3 of the roadmap** (`docs/ROADMAP.md`, adopted DEC-033) is the
pre-specified reason this null might be wrong: *at 70M the features are not
monosemantic enough for a per-feature effect to clear the noise floor*. The
measured mean relative SAE reconstruction error at 70M is **0.362** (DEC-020),
and a feature is one of roughly 100 active at a token — so a per-feature effect
is below the floor by construction. Rung 3 re-runs the rung-2 probe at a larger
scale, where reconstruction error is lower.

**Falsifier.** If the null survives at a scale where features are more
monosemantic, the scale explanation is ruled out and the null is materially
stronger. If it does not survive, that is the discovery the program exists to
find. Either outcome is a result and ends the ladder's current rung; that is what
makes rung 3 a rung and not a wish.

**Not available as a route.** Single-feature causal claims (status-ladder rungs
3–4) are not reachable at this scale: DEC-020 measured **0/50** features above
the cause threshold, and DEC-025 found the per-feature effect real only on the
logit scale at a feature's own token, with **3 of 4** features failing context
isolation. A stronger negative therefore has to come from scale, not from a
finer-grained causal instrument.

## 5. Why the null is reportable rather than ambiguous

The validation layer (DEC-021, `tooling/gates/`) is what separates *"the detector
is broken"* from *"the phenomenon was not found"*. The null rests on two checks
that could each have failed and did not:

1. **The instrument works** — the injected positive control recovers at
   `z` 11.30.
2. **The inputs are disjoint** — the two domains share zero tokenizer ids,
   verified mechanically.

A negative without both is uninterpretable. The three structurally-broken
statistics retired along the way (DEC-016, DEC-023, DEC-027) were each caught by
running the positive control first, which is why the process rule — *never report
a null the control did not survive* — is itself a transferable result.

## Reproducing the basis

- `docs/decisions/LOG.md` — DEC-027 (the result and its setup), DEC-021
  (validation layer), DEC-020/DEC-025 (the scale ceiling), DEC-011 (input gate).
- `findings.jsonl` record 5 — run `20260919-0229-to3m`, issue #3,
  `verdict: null`, `pythia-70m-deduped`, `blocks.3.hook_resid_post`.
- `docs/ROADMAP.md` — Rung 2 (concluded negatively) and Rung 3 (the scale test).
- `docs/reference/PRIOR_ART.md` §4 — feature absorption.
