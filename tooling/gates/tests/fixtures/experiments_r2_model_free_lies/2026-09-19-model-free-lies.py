"""G-R2 failing fixture: declares model-free but loads a model.

**Model:** none
**Inputs:** fixture prompt sets.
**Question:** does a false model-free declaration still fail?
**Null:** fixture null model.
**Correction:** fixture correction.
**Issue:** #75 (fixture only).
"""

from transformers import AutoModelForCausalLM


def load(model_id):
    return AutoModelForCausalLM.from_pretrained(model_id)
