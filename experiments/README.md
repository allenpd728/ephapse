# experiments

One file per experiment, named `<YYYY-MM-DD>-<slug>.py` (or `.ipynb`).

Every experiment file starts with a header comment stating:

- **Model** — exact model id and dtype
- **Inputs** — what prompt sets are used, and where they come from
- **Question** — what is being tested, in one sentence
- **Null** — the null model the result will be compared against
- **Correction** — the multiplicity correction applied
- **Issue** — the GitHub issue this belongs to

A file without those five header fields is not runnable as evidence.

---

## Infrastructure / baseline measurements

Files whose purpose is measuring the environment rather than testing a
scientific question (`sandbox-baseline-*`, `latency-*`) are exempt from the
`Null` and `Correction` header fields — there is no hypothesis under test.
They must still state **Model**, **Question**, and **Issue**, and their
results land in `docs/reference/SANDBOX_BASELINE.md` rather than
`findings.jsonl`.

---

## Run log

| Date | File | Issue | What it measured |
|---|---|---|---|
| 2026-09-18 | `2026-09-18-sandbox-baseline-hooked.py` | #1 | Peak RSS for a hooked run (`run_with_cache`) vs bare forward pass; cache size per prompt |
| 2026-09-18 | `2026-09-18-latency-vs-batch.py` | #1 | Amortized latency across batch sizes; resolves the 207 ms (batch 1) vs 21 ms (batch 64) discrepancy |

Note: these two are the pre-existing exceptions to the naming convention above
(they omit the `null`/`correction` headers deliberately). Future files should
carry the full header.
