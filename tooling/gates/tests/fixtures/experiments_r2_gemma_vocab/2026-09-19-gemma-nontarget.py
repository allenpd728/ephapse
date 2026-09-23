"""G-R2 failing fixture: a non-target model in the gemma family.

**Model:** google/gemma-2-9b, bf16, CPU.
**Inputs:** fixture prompt sets.
**Question:** does G-R2 still fire on gemma-2-9b after DEC-040?
**Null:** fixture null model.
**Correction:** fixture correction.
**Issue:** #74 (fixture only).
"""

MODEL = "google/gemma-2-9b"
