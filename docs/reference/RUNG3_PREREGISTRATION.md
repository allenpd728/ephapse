# Rung 3 pre-registration — detector statistic for the `gemma-2-2b` SAE

**Issue:** #40 (Rung 3 prerequisite B), unblocked by #39 (feasibility, closed).
**Date:** 2026-09-23 · **Status:** pre-registered — parameters frozen before the
rung-3 probe runs.
**Scope:** this document specifies *what the rung-3 probe computes and with what
thresholds*. It does **not** run the probe, and it contains no measurement of the
model. The probe itself is a separate, not-yet-filed issue (its Definition of
Done cannot be written before the parameters below are pinned — which is what
this document does).

**Authority.** Overlaps #23 (the machine-readable detector-contract registry).
#23 is blocked by #22 and has not landed, so this is a standalone instantiation
of the same contract pattern. When #23 lands, its registry entries should point
at these parameters rather than duplicate them.

**The rule this document exists to honor.** Three statistics in three issues
looked plausible and could not fire at 70M (DEC-016 p-value resolution, DEC-019
band ceiling, DEC-027 raw co-activation rate). The working statement is DEC-027's:

> A family-wise cutoff over an **unstandardized** statistic is the recurring bug.

The corresponding discipline: **re-derive** the parameters for the new SAE rather
than copy them, and record for each parameter **whether it transfers from 70M or
is newly derived** (the issue's Definition of Done).

---

## 0. Transfer table — what carries and what is re-derived

The Done comment must state each row; this table is the authoritative version.

| Parameter | 70M value | Rung-3 value | Transfers? |
|---|---|---|---|
| Hook | `blocks.3.hook_resid_post` | `blocks.12.hook_resid_post` | **Newly derived** — depth-fraction analogue (see §1) |
| SAE release | `pythia-70m-deduped-res-sm` | `gemma-scope-2b-pt-res-canonical`, `layer_12/width_16k/canonical` | **Newly derived** — and already shown to load (#39) |
| Selectivity band | `[0.05, 0.60]` per domain | output of the §2 rule on the measured firing distribution | **Newly derived** — not copied |
| Family size | 793 | measured at probe time from the band | **Newly derived** |
| Correction | family-wise max-statistic, no BH | family-wise max-statistic, no BH | **Transfers** — the DEC-016/027 lesson is scale-independent |
| N_PERM | 400 | 400 | **Transfers** (kept identical so the cutoff construction is the rung-2 one) |
| Statistic | `(obs − perm_mean) / perm_sd`, per feature | same | **Transfers** — this is the fix, not the bug |
| Firing rule (primary) | `gt0` (positive activation) | `gt0` | **Transfers** — `pct95` excludes sparse signals (DEC-027) |
| Plant token / rate | `Zorblat` / 0.10 of paired passages, both domains | same | **Transfers** — the control must be comparable across scales |
| Injection grid | `[0, .001, .005, .01, .02, .05, .10, .20, .40]` | same | **Transfers** (DEC-016/018) |
| Input corpus | 120 cooking / 120 astronomy, zero shared tokenizer ids | same | **Transfers** (DEC-011 input gate) |
| Reconstruction target | relative error 0.362 (DEC-020) | **not comparable yet** | **Open** — see §8 |

---

## 1. Hook

**Pre-registered:** `blocks.12.hook_resid_post` on `gemma-2-2b`
(`n_layers=26`, `d_model=2304`).

**Why this is the cross-scale analogue of `blocks.3.hook_resid_post`.** The 70M
model has 6 layers and read layer 3 — depth fraction **3/6 = 0.50**. The nearest
depth fraction on a 26-layer model is `round(0.50 × 26) = 13`, and the Gemma Scope
canonical residual release is keyed at even widths; **layer 12 (12/26 ≈ 0.46)** is
the closest available hook and is the one #39 loaded. Matching depth fraction is
the analogue rule, because the rung-3 question is whether the *same measurement at
a larger scale* changes the answer; a different depth would change the quantity
as well as the scale.

**Kind note.** Gemma Scope residual releases are keyed `layer_N/width_16k/...`;
the Matryoshka release (`gemma-2-2b-res-matryoshka-dc`, 25 SAEs) exposes
`blocks.N.hook_resid_post` natively. The **canonical 16k residual release** is
chosen because it is the one with a measured load (#39: `d_in=2304`,
`d_sae=16384`, `hook=blocks.12.hook_resid_post`, `arch=jumprelu`, encode works,
load wall 17.9 s). Choosing an untested release would re-open a feasibility
question #39 already closed.

**Precondition (see §8).** The hook is fixed here; the *input normalization* the
release expects is not, and must be settled before the probe's reconstruction
number is interpreted.

---

## 2. Selectivity band

**Pre-registered: the rule, not the numbers.** The band is re-derived from the new
SAE's firing distribution at probe time. The 70M band `[0.05, 0.60]` is the
*reference point the rule reproduces*, not a value to copy.

A family member must fire often enough to carry a bridge and rarely enough that
its *chance* co-activation does not saturate:

- **Lower bound `lo`.** A feature below `lo` fires on too few passages to carry
  the planted 10 %-prevalence signal in *both* domains. This is the DEC-027
  failure: a per-feature 95th-percentile rule **excluded the sparse planted
  signal** and failed to recover the control. `lo` is the rate below which a
  domain-passage firing rate cannot express a signal present in 10 % of pairs.
- **Upper bound `hi`.** A feature above `hi` co-fires at near-1 under *any*
  pairing, so its chance co-activation dominates and the contrast that the
  standardized statistic needs collapses. This is the DEC-027 second failure: the
  raw-rate cutoff was dominated by high-firing features whose chance
  co-activation was ~0.37 no matter what was injected.

**Rule (frozen):** with the measured firing-rate histogram per domain,
`lo` = the smallest rate at which the 10 %-prevalent plant is expressible, and
`hi` = the rate above which the feature's permutation-null co-activation exceeds
0.5 in the majority of pairings. Both values and the histogram are recorded at
probe time.

**Hard constructibility gate (DEC-019).** The feature the planted token drives
must fall **inside** `[lo, hi]` in both domains. If it does not, the band is wrong
and the probe is invalid — the rung-2 `pct95` arm failed exactly here. The probe
must not be read until this check passes.

**Why re-derivation is required rather than optional.** A 16k-width layer-12 SAE
on a 2B model has a different width, depth, and training distribution than a
32k-width layer-3 SAE on a 70M model. The firing distribution is a property of the
SAE, not of the method, so the band — which is a quantile of that distribution —
does not transfer.

---

## 3. Family size and multiplicity correction

**Family definition.** Features inside `[lo, hi]` in *both* domains — the same
bounded, pre-specified family as rung 2 (DEC-024), not the full feature × pair
product. At 70M this gave |family| = 793 of 32,768 (2.4 %). At 16k the absolute
count is measured at probe time; it is **not assumed** to scale down linearly,
because band membership is a property of the trained SAE.

**Correction (frozen): family-wise max-statistic on the standardized statistic.**
For each family feature the observed co-activation rate is standardized against
the mean/sd of that same rate over shuffled pairings; the cutoff is the **95th
percentile, over permutations, of the maximum per-feature z**; survivors are
features whose z exceeds that cutoff. **BH-FDR is not used.**

**Why not BH (the DEC-016/018 arithmetic, checked, not assumed).**
- A permutation null at `N_PERM=100` has a p-value floor of `p = 0.01`. BH over a
  family of `m ≈ 6e4` needs `p ≤ q/m = 1.6e-6` — a 6250× gap. The correction
  cannot fire. (DEC-016.)
- DEC-018's *analytic* null has no such floor, so BH does fire there and is the
  binding constraint for dense signals. That dissociates "correction cannot fire"
  from "detector cannot see" — but it is a different null model, and rung 2
  (and therefore rung 3, for comparability) uses the permutation null.

**N_PERM (frozen): 400**, identical to the rung-2 probe. The DEC-016 floor applies
to *p-values counted from permutations*, not to the **percentile of the permutation
maxima** used here. The 95th percentile of 400 permutation maxima is resolved by
the number of maxima (400), not by `1/N_PERM` used as a p-value floor. Keeping
`N_PERM=400` means the cutoff construction is byte-for-byte the rung-2 one, so a
change in the result is attributable to scale, not to the correction.

---

## 4. Statistic

**Pre-registered:**

```
z_feature = (observed_coactivation_rate − perm_mean) / perm_sd
cutoff    = 95th percentile, over permutations, of max_feature(z)
survivor  = z_feature > cutoff
```

**Why standardized (the whole point).** A raw co-activation rate with a family-max
cutoff is retired: its cutoff is set by whichever high-firing feature has the
largest *chance* co-activation, so a sparse injected signal can never clear it
(DEC-027: injection gave best rate 0.3417 vs cutoff 0.3750; the same control
recovered at z 11.30 after standardizing). Standardizing per feature puts every
feature on one scale regardless of firing rate, which is what makes the family-max
cutoff meaningful.

**Firing rule (frozen): `gt0` — positive activation — is primary.** `pct95` is
computed and reported alongside as the secondary, for comparability with rung 2.
Reason: the planted signal has 10 % prevalence, and a per-feature 95th-percentile
threshold excludes the low support such a signal lives in (DEC-027). This is the
"wrong tool for a 10 %-prevalence feature" failure, not a claim that `pct95` is
wrong in general.

---

## 5. Positive control and constructibility check

Run **before** the real result is read (the rung-2 rule, and DEC-019).

**Construction (frozen, same as rung 2).** Append the rare token
`PLANT_TOKEN = "Zorblat"` to a **planted fraction of paired passages in BOTH
domains** — the same paired indices, so the injected co-occurrence is by
construction. `PLANT_RATE = 0.10`.

**Injection grid (frozen, DEC-016/018):**
`rate ∈ [0.0, 0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.40]`, so the recovery
curve is a result rather than a reshaping of one chosen rate.

**Two checks, both required:**

1. **Constructibility (DEC-019).** The planted token must be shown to raise the
   target feature's activation in *both* domains — `mean(activation | injected) −
   mean(activation | not injected) > 0` in each domain — before recovery is read.
   A control not shown constructible does not count.
2. **Band membership.** The feature the plant drives must be inside `[lo, hi]` in
   both domains (§2 hard gate).

**Recovery (frozen).** The statistic must recover the planted feature — that
feature's z above the family-wise cutoff — at an injected rate at or below the
grid's mid-range, exactly as rung 2 recovered z 11.30 vs cutoff 4.47. If the
control does not recover, the detector is not viable at this scale and rung 3
ends here (rung-0 logic re-applied at 2B), independent of the real-run result.

---

## 6. Falsifier

The pre-registration is falsified — that is, a negative outcome *is* a result —
by any of:

1. **Control not recoverable.** The positive control fails to recover at every
   injected rate. → The detector is not viable at 2B; the ladder ends at rung 3.
2. **Control not constructible.** No feature the plant drives can be placed
   inside the band; or the plant does not raise a feature in both domains. → The
   measurement is invalid, not negative.
3. **Empty family.** The band rule yields no feature firing in both domains. →
   The probe is mis-specified; the band rule must be revisited (a specification
   failure, not a model result).
4. **Reconstruction not comparable.** The reconstruction error cannot be made
   comparable to DEC-020's 0.362 (see §8: official checkpoint + intended input
   normalization unavailable). → The quantity rung 3 is *about* is not measured;
   do not report the recon number as a rung-3 verdict.

And, positively: if the control recovers and the real run shows `0 survivors` at
the family-wise cutoff, that is a **clean null at 2B** — a materially stronger
negative than rung 2, and the outcome the ladder expects. A reproduction at larger
scale is stronger evidence than rung 2, not a failure.

---

## 7. Probe inputs and environment (frozen for comparability)

- **Model:** `gemma-2-2b` (`n_layers=26`, `d_model=2304`, `d_vocab=256000`).
  `google/gemma-2-2b` is **gated** (401 without `HF_TOKEN`); #39 loaded the
  architecture-identical public mirror `unsloth/gemma-2-2b` instead. The probe
  must record which checkpoint it used, because §8's reconstruction comparison
  depends on it.
- **Precision:** #39 measured in **bf16** (bf16 weights, fp32 compute) — the fp32
  path OOMs at batch 64. The probe inherits bf16 and must record the precision
  caveat: the recon figure is not directly comparable to the 70M fp32 figure
  across dtypes.
- **Corpus:** the same 120 cooking / 120 astronomy passages, zero shared tokenizer
  ids, each domain with its own glue tokens (DEC-011 input gate). The passages are
  wrapped in a shared carrier so only the rendering differs (DEC-023).
- **Context:** passage-length context (70M median 18–19 tokens; usable features
  rise with context — DEC-023).
- **Cost, measured (#39):** load 114.5 s / 3.31 GB RSS; forward 358 ms single
  prompt, 163 ms/prompt at batch 64; SAE load 17.9 s; peak RSS 6.95 GB of ~15 GiB.
  Size any sweep on the **batch-64** number, not the single-prompt one (they differ
  ~2×, and sizing on the single number is the mistake `SANDBOX_BASELINE.md` warns
  about).

---

## 8. Open preconditions the probe must resolve first

These are carried from #39's measured caveat and are **not** papered over:

1. **Reconstruction comparability (the number rung 3 is about).** #39 measured
   relative reconstruction error **2.6005**, cosine 0.4560, L0 659 — far from a
   working 16k canonical SAE (~0.36, L0 ~80). A bounded diagnostic showed the
   cause is input scaling: this SAE has `normalize_activations = none` with
   `‖b_dec‖ = 85.1` and an identity input-norm fn, and synthetic activations at
   matched norm swing the metric from 1.12 to 8.20 purely with input scale. **The
   load is real; the recon number is not a rung-3 verdict.** A comparable figure
   requires (a) the official checkpoint, and (b) the release's intended input
   normalization. Until both are settled, §6 item 4 applies.
2. **Checkpoint provenance.** Whether the probe uses the gated official weights
   (needs `HF_TOKEN`) or the mirror, and the consequence for the recon
   comparison, must be stated in the probe's header.
3. **Dtype caveat.** bf16 is forced by RAM; the recon comparison to the 70M fp32
   figure must record it.

These are **probe preconditions, not blockers on this document.** The
pre-registration is complete without them; the probe is not.

---

## 9. References

- `docs/ROADMAP.md` § Rung 3 — the ladder and the scale rationale.
- `docs/NEXT_STEPS.md` §3 (the two prerequisites), §7 (verification recipe).
- DEC-005 (freeze method before the run) · DEC-011 (input-disjointness gate) ·
  DEC-014 (query availability, never assume) · DEC-016 (p-value floor — the
  correction that could not fire) · DEC-018 (analytic-null replication) ·
  DEC-019 (constructibility before reading) · DEC-020 (the 0.362 reconstruction
  error at 70M) · DEC-023 (per-feature thresholds + context) · DEC-024 (bounded
  family) · DEC-027 (the standardized statistic + the recurring-bug rule) ·
  DEC-039 (gate-count single-sourcing).
- #39 (feasibility, closed) · #23 (detector-contract registry — coordinate, do not
  duplicate) · #3 (the rung-2 probe this mirrors).
- `experiments/2026-09-19-cross-domain-probe.py` — the implementation these
  parameters mirror.
- `docs/reference/SANDBOX_BASELINE.md` — measurement discipline and the 70M
  figures.
