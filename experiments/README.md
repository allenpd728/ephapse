# Experiments

One file per experiment, named `<YYYY-MM-DD>-<slug>.py` (or `.ipynb`).

Every experiment file starts with a header comment stating:

- **Model** — exact model id and dtype
- **Inputs** — what prompt sets are used, and where they come from
- **Question** — what is being tested, in one sentence
- **Null** — the null model the result will be compared against
- **Correction** — the multiplicity correction applied
- **Issue** — the GitHub issue this belongs to

A file without those five header fields is not runnable as evidence.
