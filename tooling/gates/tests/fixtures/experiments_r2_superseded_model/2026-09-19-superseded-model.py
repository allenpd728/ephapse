"""Correctly-attributed superseded-measurement fixture (issue #24 hole 1).

**Model:** pythia-160m, fp32, CPU.
**Inputs:** fixture prompt sets.
**Question:** does G-R2 stay silent on a superseded model that carries a valid
  attribution naming the model decision?
**Null:** fixture null model.
**Correction:** fixture correction.
**Issue:** #11 (fixture only).

**Supersedes: DEC-014** — the header names the superseded 160M on purpose; the
line-leading declaration attributes the substitution to the decision that
chose the 70M, so G-R2 must accept it (silence, not a finding).
"""

MODEL = "pythia-160m"
