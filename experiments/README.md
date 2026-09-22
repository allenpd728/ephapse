# experiments

One file per experiment, named `<YYYY-MM-DD>-<slug>.py` (or `.ipynb`).

Every experiment file starts with a header comment carrying six mandatory
fields. Copy this block verbatim and fill it in:

```python
"""<one-line summary>

**Model:** <exact model id>, <dtype>, <device>.
**Inputs:** <what prompt sets are used, and where they come from>.
**Question:** <what is being tested, in one sentence>.
**Null:** <the null model the result is compared against>.
**Correction:** <the multiplicity correction applied>.
**Issue:** #<number> (<context>).
"""
```

A file missing any of the six fields is not runnable as evidence. The rule is
enforced by `tooling/gates/validate_experiments.py` (G-R1) — that gate's rule
definition is the single source of truth; this section describes it and is tied
to it, it does not replace it.

---

## Infrastructure / baseline measurements

The exemption is an **enumerable filename pattern**, never an intent. A file is
exempt when its name — with any leading `YYYY-MM-DD-` stripped — matches one of
the patterns enumerated in `INFRA_PATTERNS` in
`tooling/gates/validate_experiments.py`:

- `sandbox-baseline-*`
- `latency-*`

Those files measure the environment rather than testing a scientific question,
so they drop `Null` and `Correction` and carry the three reduced fields —
**Model**, **Question**, **Issue**:

```python
"""<one-line summary>

**Model:** <exact model id>, <dtype>, <device>.
**Question:** <what the environment measurement establishes>.
**Issue:** #<number> (<context>).
"""
```

Their results land in `docs/reference/SANDBOX_BASELINE.md` rather than
`findings.jsonl`.

A file cannot grant itself the exemption by describing itself as
infrastructure: a line-leading declaration is ignored, because the exemption is
a function of the filename alone. A hypothesis-test file that claims the
exemption is judged against the full six-field rule and reported — the intent
phrasing ("whose purpose is measuring the environment") is deliberately not the
rule, since no agent can apply it consistently.

---

## Run log

| Date | File | Issue | What it measured |
|---|---|---|---|
| 2026-09-18 | `2026-09-18-sandbox-baseline-hooked.py` | #1 | Peak RSS for a hooked run (`run_with_cache`) vs bare forward pass; cache size per prompt |
| 2026-09-18 | `2026-09-18-latency-vs-batch.py` | #1 | Amortized latency across batch sizes; resolves the 207 ms (batch 1) vs 21 ms (batch 64) discrepancy |
| 2026-09-18 | `2026-09-18-toolchain-neuronpedia-crosscheck.py` | #2 | End-to-end TransformerLens + SAELens, cross-checked against Neuronpedia's hosted copy of the same feature |
| 2026-09-18 | `2026-09-18-detector-positive-control.py` | #5 | Injected-correlation positive control: detector recovery vs injection rate, permutation null, negative control. **PASSES** on the max-statistic test; BH-FDR layer found broken (DEC-016) |
| 2026-09-18 | `2026-09-18-injected-positive-control-detector-validation.py` | #5 | Detector recovery vs injected-correlation rate at pythia-70m; **detector recovers 0.87 at rate 0.20 vs 0.00 for a naive raw-co-occurrence baseline**. Four prior runs (same file, preserved as `*-results-initial.json`, `-v2`, `-v3`, `-v4`) returned zero for control-side and test-side reasons documented in DEC-019 |
| 2026-09-19 | `2026-09-18-intervention-positive-control.py` | #7 | Interchange-intervention harness (ablation). **Known-positive passes 5/5** (full residual swap moves the target); cumulative ablation ladder **MOVES 5/5**; but **0/50 single features** exceed the cause threshold — per-feature claims are inconclusive at this scale, not negative (DEC-020). SAE reconstruction rel. error 0.362 |
| 2026-09-19 | `2026-09-19-interchange-intervention-positive-control.py` | #7 | Same task, two intervention **sites** x two metric **scales**. At the country token (logit scale) **mean Cause 0.75**, interference control 0/240, but mean Isolate 0.208 (3/4 features fail isolation). At the final token (probability scale, matching DEC-020) the effect is 8e-4 — invisible. Reconciles the two opposite #7 results: site and scale change the answer (DEC-025) |
| 2026-09-19 | `2026-09-19-diagnose-saturation.py` | #6 | Feature firing-rate distribution; found 32764/32768 features firing on zero prompts under a pooled threshold |
| 2026-09-19 | `2026-09-19-diagnose-length-dependence.py` | #6 | Feature activity vs prompt length; passages give 2.2x the usable-feature pool of bare prompts |
| 2026-09-19 | `2026-09-19-paraphrase-robustness.py` | #6 | Verbal-vs-symbolic bridging. Matched 6 survivors vs null 0 (weak but real); paraphrase 17 |
| 2026-09-19 | `2026-09-19-detector-positive-control-rerun.py` | #5 | #5 re-run with per-feature thresholds. **Does NOT replicate** — max-NPMI cannot separate the injected pair from noise |
| 2026-09-19 | `gen_cross_domain.py` | #3 | Generate 120 cooking / 120 astronomy passages with a **mechanically verified zero-token-id intersection** (separate vocab *and* glue tokens); median 18-19 tokens |
| 2026-09-19 | `2026-09-19-cross-domain-probe.py` | #3 | Cross-domain co-activation probe. **Positive control recovers** (planted token, best z 11.30 vs cutoff 4.47); real run **0 survivors** (best z 3.10 vs 4.41) — a clean, interpretable null. Retires the raw co-activation-rate family-max cutoff (DEC-027) |

Note: the first two are the pre-existing exceptions to the naming convention
above (they omit the `null`/`correction` headers deliberately). Future files
should carry the full header.

## Target model and SAE (settled, issue #2)

**Use `pythia-70m-deduped` with `pythia-70m-deduped-res-sm`** (7 hooks,
resid_pre + resid_post L0–L5). This is not a preference — it is the only
Pythia pair that exists in SAELens. There is no Pythia-160M release. See
DEC-014 and `docs/reference/SANDBOX_BASELINE.md`.

Working values from the verified run:

```python
MODEL      = "pythia-70m-deduped"          # TransformerLens
SAE_RELEASE = "pythia-70m-deduped-res-sm"  # SAELens
SAE_ID      = "blocks.3.hook_resid_post"   # d_in=512, d_sae=32768
NP_MODEL    = "pythia-70m-deduped"         # Neuronpedia
NP_SAE      = "3-res-sm"
```

Decoder directions come from local `sae.W_dec`. Neuronpedia does **not**
serve vectors (DEC-015).
