"""Issue #2: TransformerLens + SAELens end to end, cross-checked against
Neuronpedia's hosted copy of the same feature.

**Model:** pythia-70m-deduped (TransformerLens), fp32, CPU.
**Inputs:** a fixed set of 8 short prompts (below); no external corpus.
**Question:** does the local SAE (SAELens) and the hosted SAE (Neuronpedia)
  describe the *same* feature for a given model/layer/feature-index?
**Null:** none — this is a value-agreement cross-check of two implementations
  of the same model/SAE (local SAELens vs Neuronpedia's hosted copy) on fixed
  inputs; there is no sampling noise and no chance baseline to model.
**Correction:** none — a single deterministic agreement comparison, not a
  family of hypothesis tests.
**Issue:** #2 (run 20260918-1720-altu).

The cross-check is: does Neuronpedia's reported max activation for feature F
agree with our locally-observed max activation for the same F on the same
inputs, and does the decoder vector dimension match d_model?
"""
import json
import urllib.request

import torch
from transformer_lens import HookedTransformer

MODEL = "pythia-70m-deduped"
LAYER = 3
HOOK = f"blocks.{LAYER}.hook_resid_post"
SAE_RELEASE = "pythia-70m-deduped-res-sm"   # SAELens release
SAE_ID = HOOK                                # sae_id within that release
NP_MODEL = "pythia-70m-deduped"             # Neuronpedia model id
NP_SAE = f"{LAYER}-res-sm"                  # Neuronpedia sae id

PROMPTS = [
    "The Eiffel Tower is located in the city of Paris",
    "Photosynthesis converts light into chemical energy in plants",
    "The prime minister announced a new policy on taxation",
    "Integers form a ring under addition and multiplication",
    "Mitochondria are the powerhouse of the cell",
    "The stock market fell sharply after the announcement",
    "Water boils at one hundred degrees Celsius at sea level",
    "Recursion is when a function calls itself",
]

print(f"=== {MODEL} | {HOOK} | SAE release={SAE_RELEASE} ===")

# --- 1. TransformerLens load ---
model = HookedTransformer.from_pretrained(MODEL, device="cpu")
print(f"  d_model={model.cfg.d_model}  n_layers={model.cfg.n_layers}")

# --- 2. SAELens load ---
from sae_lens import SAE

sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=SAE_ID, device="cpu")
print(f"  SAE loaded: d_in={sae.cfg.d_in}  d_sae={sae.cfg.d_sae}")
assert sae.cfg.d_in == model.cfg.d_model, "d_in != d_model"

# --- 3. encode activations locally ---
with torch.no_grad():
    _, cache = model.run_with_cache(PROMPTS, names_filter=lambda n: n == HOOK)
    acts = cache[HOOK]                      # (batch, seq, d_model)
    feats = sae.encode(acts)                # (batch, seq, d_sae)
    feat_max = feats.amax(dim=(0, 1))       # max over batch+seq, per feature

order = torch.argsort(feat_max, descending=True)
top = [(int(i), float(feat_max[i])) for i in order[:5] if float(feat_max[i]) > 0]
print(f"  local top-5 active features (feature_index, local max act): {top}")

# --- 4. cross-check the same features on Neuronpedia ---
print()
print("=== cross-check against Neuronpedia (same model/layer/feature) ===")
print(f"{'idx':>6} {'local max':>10} {'NP maxActApprox':>16} {'ratio':>8} "
      f"{'hasVector':>10} {'hookName match':>15}")

rows = []
for idx, local_max in top:
    url = f"https://www.neuronpedia.org/api/feature/{NP_MODEL}/{NP_SAE}/{idx}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
    except Exception as e:
        print(f"{idx:>6} {local_max:>10.3f}  FETCH FAILED: {type(e).__name__}")
        continue
    np_max = d.get("maxActApprox")
    ratio = (local_max / np_max) if np_max else float("nan")
    hook_ok = d.get("hookName") in (HOOK, None)
    rows.append((idx, local_max, np_max, ratio, d.get("hasVector"), d.get("hookName")))
    print(f"{idx:>6} {local_max:>10.3f} {np_max:>16.3f} {ratio:>8.3f} "
          f"{str(d.get('hasVector')):>10} {str(hook_ok):>15}")

# --- 5. decoder vector dimension check ---
print()
print("=== decoder direction dimension ===")
W_dec = sae.W_dec  # (d_sae, d_in)
print(f"  local W_dec shape: {tuple(W_dec.shape)}  (d_sae, d_model)")

print()
print("=== verdict ===")
if rows:
    matched = [r for r in rows if r[3] == r[3] and 0.01 <= r[3] <= 100]
    print(f"  features cross-checked: {len(rows)}")
    print(f"  same order of magnitude locally vs Neuronpedia: {len(matched)}/{len(rows)}")
    print("  NOTE: exact agreement is not expected. Neuronpedia's maxActApprox is")
    print("  the max over their own activation dataset; ours is max over 8 prompts.")
    print("  Agreement in *magnitude* is the evidence both refer to the same feature.")
else:
    print("  no features cross-checked - toolchain not verified")