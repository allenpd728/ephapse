"""G-R2 clean fixture: the DEC-040 gemma-2-2b target, org-prefixed.

**Model:** google/gemma-2-2b, bf16, CPU.
**Inputs:** fixture prompt sets.
**Question:** does G-R2 accept an org-prefixed DEC-authorized target?
**Null:** fixture null model.
**Correction:** fixture correction.
**Issue:** #74 (fixture only).
"""

import os

MODEL = os.environ.get("EPHAPSE_GEMMA_MODEL", "google/gemma-2-2b")
MIRROR = os.environ.get("EPHAPSE_GEMMA_MIRROR", "unsloth/gemma-2-2b")
# Not a model: the SAE release name must not be read as one.
SAE_RELEASE = "gemma-scope-2b-pt-res-canonical"
