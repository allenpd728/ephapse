"""Settle the latency discrepancy: 217 ms/call (earlier, single) vs 14 ms/prompt
(batched, this session). Measures amortized latency across batch sizes.

**Model:** pythia-160m, fp32, cpu.
**Supersedes: DEC-014** — pythia-160m is a superseded target (no Pythia-160M SAE
release; the authorized target is pythia-70m-deduped). These 160M measurements
are retained as a valid historical upper bound, not rewritten.
**Question:** How does amortized per-prompt latency scale with batch size on CPU,
and does batching explain the 217 ms single-call vs 14 ms batched discrepancy?
**Issue:** #1 (sandbox baseline / latency discrepancy).
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