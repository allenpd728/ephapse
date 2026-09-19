"""G-R1 failing fixture: claims the infrastructure exemption without
qualifying — it tests a hypothesis but carries only three fields.

**Model:** pythia-70m-deduped, fp32, CPU.
**Question:** does the detector recover the injected correlation?
**Issue:** #11 (fixture only).
"""

MODEL = "pythia-70m-deduped"
