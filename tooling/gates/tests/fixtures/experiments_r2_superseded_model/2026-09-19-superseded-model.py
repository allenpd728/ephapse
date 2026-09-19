"""G-R2 failing fixture: loads a superseded model id.

**Model:** pythia-160m, fp32, CPU.
**Inputs:** fixture prompt sets.
**Question:** does G-R2 fire on a non-target model?
**Null:** fixture null model.
**Correction:** fixture correction.
**Issue:** #11 (fixture only).
"""

MODEL = "pythia-160m"
