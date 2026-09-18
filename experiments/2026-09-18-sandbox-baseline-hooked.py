"""Issue #1 gap 3: peak RSS for a *real* probe (hooks caching activations),
not a bare forward pass. Also confirms SAELens encode path and CDN download.

Run: python3 experiments/2026-09-18-sandbox-baseline-hooked.py
"""
import os
import resource
import time

import torch
from transformer_lens import HookedTransformer

MODEL = "pythia-160m"
N_PROMPTS = 64
SEQ_LEN = 32
LAYERS = [3, 6, 9]


def rss_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def log(tag):
    print(f"  [{tag:34}] peak RSS {rss_gb():.2f} GB")


prompts = [
    "The Eiffel Tower is located in the city of Paris",
    "Photosynthesis converts light into chemical energy",
    "The prime minister announced a new policy on",
    "Integers form a ring under addition and",
    "Mitochondria are the powerhouse of the",
    "The stock market fell sharply after the",
    "Water boils at one hundred degrees",
    "Recursion is when a function calls",
]
batch = [prompts[i % len(prompts)] for i in range(N_PROMPTS)]

print(f"=== {MODEL}, {N_PROMPTS} prompts, hooks on layers {LAYERS} ===")
log("interpreter start")

t0 = time.time()
model = HookedTransformer.from_pretrained(MODEL, device="cpu")
print(f"  load: {time.time() - t0:.1f}s")
log("model loaded")

names = [f"blocks.{L}.hook_resid_post" for L in LAYERS]

# --- hooked run: what a real probe actually costs ---
t0 = time.time()
with torch.no_grad():
    _, cache = model.run_with_cache(
        batch,
        names_filter=lambda n: n in names,
        return_type=None,
    )
hooked_elapsed = time.time() - t0

cached = {k: tuple(v.shape) for k, v in cache.items()}
n_bytes = sum(v.numel() * v.element_size() for v in cache.values())
print(f"  hooked run: {hooked_elapsed:.1f}s over {N_PROMPTS} prompts"
      f" ({hooked_elapsed / N_PROMPTS * 1000:.0f} ms/prompt)")
print(f"  cached tensors: {cached}")
print(f"  cache size on device: {n_bytes / 1e6:.1f} MB "
      f"(fp32, {n_bytes / (1024**3) * 1000:.1f} MB)")
log("after hooked run (cache alive)")

# --- what the same probe costs with cache freed ---
del cache
log("after cache freed")

# --- SAE encode path (SAELens), the other half of the toolchain ---
sae_status = "not attempted"
try:
    from sae_lens import SAE  # noqa: F401
    sae_status = "sae_lens importable"
except Exception as e:  # pragma: no cover
    sae_status = f"sae_lens import failed: {type(e).__name__}"
print(f"  SAE path: {sae_status}")
log("after SAE import")

# --- extrapolation for later issues ---
per_prompt_cache_mb = n_bytes / N_PROMPTS / 1e6
print()
print("=== sizing for later issues ===")
print(f"  cache per prompt ({len(LAYERS)} layers): {per_prompt_cache_mb:.2f} MB")
for n in (500, 2000, 10000):
    print(f"  {n:>5} prompts -> {per_prompt_cache_mb * n:>8.1f} MB cached "
          f"({per_prompt_cache_mb * n / 1024:.2f} GB)")
print(f"  projection latency: {hooked_elapsed / N_PROMPTS * 1000:.0f} ms/prompt "
      f"-> 2000 prompts ~= {hooked_elapsed / N_PROMPTS * 2000 / 60:.1f} min")
print()
print(f"FINAL peak RSS: {rss_gb():.2f} GB")