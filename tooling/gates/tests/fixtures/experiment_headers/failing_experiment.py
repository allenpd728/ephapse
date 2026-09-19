"""Failing fixture for G-R1: a NEAR MISS — five of six fields present.

**Model:** pythia-70m-deduped, fp32, CPU.
**Inputs:** two prompt sets defined below.
**Question:** does the detector recover a correlation known to be present?
**Null:** per-pair Poisson independence, BH-FDR corrected.
**Issue:** #5 (fixture only — not a real run).

`Correction` is deliberately absent. This is the whole point of the fixture: a
gate that only fires on an empty or obviously-malformed file would satisfy the
letter of the fixture rule and none of its purpose. The realistic defect is a
header that looks complete and omits one mandatory field.

Note the file does NOT declare itself an infrastructure file, so the full
six-field set applies — omitting `Correction` is a genuine violation, not a
reduced-header exemption.
"""

PROMPTS_A = ["alpha", "beta"]
PROMPTS_B = ["gamma", "delta"]
