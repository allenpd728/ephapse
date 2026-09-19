"""Clean fixture for G-R1: a full six-field header.

**Model:** pythia-70m-deduped, fp32, CPU.
**Inputs:** two prompt sets defined below.
**Question:** does the detector recover a correlation known to be present?
**Null:** per-pair Poisson independence, BH-FDR corrected.
**Correction:** Benjamini-Hochberg at q=0.05.
**Issue:** #5 (fixture only — not a real run).

This file exists only to be the clean case for the header-completeness gate.
It is not executed by anything.
"""

PROMPTS_A = ["alpha", "beta"]
PROMPTS_B = ["gamma", "delta"]
