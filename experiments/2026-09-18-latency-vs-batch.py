"""Settle the latency discrepancy: 217 ms/call (earlier, single) vs 14 ms/prompt
(batched, this session). Measures amortized latency across batch sizes.
"""
import time

import torch
from transformer_lens import HookedTransformer

model = HookedTransformer.from_pretrained("pythia-160m", device="cpu")
p = "The Eiffel Tower is located in the city of Paris"

print("=== amortized latency vs batch size (pythia-160m, CPU) ===")
with torch.no_grad():
    model(p)  # warm

    # single-prompt repeated calls (what the 217 ms figure measured)
    t0 = time.time()
    for _ in range(5):
        model(p)
    single = (time.time() - t0) / 5 * 1000

    print(f"  1 prompt, 5 sequential calls   : {single:.0f} ms/call")

    for bs in (1, 8, 32, 64):
        batch = [p] * bs
        model(batch)  # warm
        t0 = time.time()
        model(batch)
        elapsed = (time.time() - t0) * 1000
        print(f"  batch of {bs:>3}, one call      : {elapsed:>7.0f} ms total"
              f"  -> {elapsed / bs:>6.1f} ms/prompt")

print()
print("reading: the 217 ms figure is per-call overhead at batch size 1;")
print("throughput amortizes in a batch. Experiment sweeps should size on")
print("the batched figure.")