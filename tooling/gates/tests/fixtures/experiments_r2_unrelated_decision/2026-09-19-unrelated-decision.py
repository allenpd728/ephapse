"""G-R2 *failing* fixture: cites an unrelated decision, not the model decision.

**Model:** pythia-160m, fp32, CPU.
**Inputs:** fixture prompt sets.
**Question:** does G-R2 refuse an attribution that names a decision which is not
  the model decision?
**Null:** fixture null model.
**Correction:** fixture correction.
**Issue:** #11 (fixture only).

**Supersedes: DEC-011** — 011 is not the decision that chose the 70M target, so
this citation does not authorize the 160M. A gate that accepted any `DEC-\d+`
would be silenced by this file, which is the hole issue #24 warns against.
"""

MODEL = "pythia-160m"
