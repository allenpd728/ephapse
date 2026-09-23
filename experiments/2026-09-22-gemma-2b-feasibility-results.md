# ephapse #39 — gemma-2-2b CPU feasibility (raw result)

Run `20260923-0523-ez4n`, 2026-09-23. Reproduced with:

```
python3 experiments/2026-09-22-gemma-2b-feasibility.py 2>&1 | tee /tmp/g2b.txt
```

Verdict: **feasible, with a caveat.** gemma-2-2b loads and runs forward on CPU,
and a Gemma Scope residual SAE loads and encodes. The binding constraint is
latency / RAM headroom, not load failure. One number — reconstruction error — is
**not comparable** to the DEC-020 0.362 baseline; see caveat below.

## Environment

| | |
|---|---|
| torch | 2.14.0+cpu |
| torch threads | 2 |
| weights dtype | bf16 (bf16 weights, fp32 compute) |
| host RAM | 15 GiB total, no cgroup cap exported |
| HF token | absent |

## 1. Model load

- TransformerLens path (`google/gemma-2-2b`) **failed** after 4.0s:
  `OSError: You are trying to access a gated repo.` — 401, no HF_TOKEN. (Gated,
  as expected.)
- Fallback `unsloth/gemma-2-2b` (architecture-identical public mirror) via plain
  `transformers`, `dtype=bf16`:
  - **LOADED wall = 114.5s**, params = **2.614B**
  - cfg: n_layers=26, d_model=2304, d_vocab=256000
  - **peak RSS after load = 3.31 GB**

## 2. Forward pass (CPU)

- single prompt (~10 tok), median of 5: **358 ms**
- batch 64: **10.44s = 163 ms/prompt**
- ratio batch64/single = **0.5x** (batch helps; single-prompt latency is not the sweep cost)
- **peak RSS after forward = 6.95 GB**

## 3. SAE load

- release `gemma-scope-2b-pt-res-canonical`, sae_id `layer_12/width_16k/canonical`
- **LOADED wall = 17.9s**
- d_in=2304, d_sae=16384, hook=`blocks.12.hook_resid_post`
- arch=`jumprelu`, model_name=`gemma-2-2b`
- neuronpedia_id=`gemma-2-2b/12-gemmascope-res-16k`

## 4. Reconstruction error

- activations sourced from the mirror's residual stream (block 12), shape (88, 2304)
- **relative error = 2.6005** (DEC-020 at pythia-70m: 0.362)
- cosine = **0.4560**
- mean L0 active = **659**

**FINAL peak RSS = 6.95 GB** (of 15 GiB; ~8 GB headroom).

## Caveat — the recon figure is not comparable to 0.362

The 2.60 is far above the value a working 16k canonical SAE should produce, and
the L0 (659) is far above the release's typical ~80. Two diagnostics point at a
scaling mismatch rather than a broken SAE load:

- This canonical SAE carries a large learned bias (`‖b_dec‖ = 85.1`) and reports
  `normalize_activations = none`; `run_time_activation_norm_fn_in` is an identity.
  Gemma Scope canonical SAEs are trained on inputs whose scale the loader is
  expected to match, and here it is not.
- Re-running encode/decode on synthetic activations of matched norm (row-norm 40)
  shows relative error swinging from 1.12 to 8.20 as the input scale is varied,
  with L0 changing from 203 to 23 — i.e. the metric is dominated by input scale,
  not by SAE quality.

The mirror is also bf16 and architecture-identical but **not** the official
checkpoint, so its residual geometry is not bit-identical to the gated weights.
Conclusion: **gemma-2-2b is CPU-usable and its SAEs load**, but the recon number
recorded here must not be read as "this SAE reconstructs worse than the 70M one."
Establishing a comparable recon figure needs the official checkpoint plus the
release's intended input-normalization step — that is a follow-up, not this
prerequisite.
