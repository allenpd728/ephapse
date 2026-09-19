"""G-R1 failing fixture: full header missing the `Correction` field.

**Model:** pythia-70m-deduped, fp32, CPU.
**Inputs:** fixture prompt sets.
**Question:** does G-R1 fire on a near-miss header?
**Null:** fixture null model.
**Issue:** #11 (fixture only).
"""

MODEL = "pythia-70m-deduped"
