"""G-R2 clean fixture: a model-free artifact, honestly declared.

**Model:** n/a (corpus preparation; no model is loaded).
**Inputs:** fixture corpus files.
**Question:** does G-R2 accept a body-checked model-free declaration?
**Null:** fixture null model.
**Correction:** fixture correction.
**Issue:** #75 (fixture only).
"""

import json


def load(path):
    with open(path) as f:
        return json.load(f)
