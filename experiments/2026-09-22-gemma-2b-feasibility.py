"""Ep#39 — Rung 3 prerequisite A: CPU feasibility for gemma-2-2b in the sandbox.

Measures, on CPU, whether gemma-2-2b is usable here and whether Gemma Scope
SAEs load. A feasibility *measurement*, not the rung-3 probe.

  load        : did gemma-2-2b load in TransformerLens on CPU; peak RSS; wall time
  forward     : single-prompt latency, and ms/prompt at batch 64
  sae         : Gemma Scope residual SAE loads/encodes; release, sae_id, d_in, d_sae, hook
  recon       : resid_post vs sae.decode(sae.encode(resid_post)) — relative error, cosine

Run: python3 experiments/2026-09-22-gemma-2b-feasibility.py 2>&1 | tee /tmp/g2b.txt

A "not feasible" outcome is a legitimate result: it retires the scale explanation
at this budget. The binding constraint is named in the output.
"""
import os
import resource
import time
import traceback

import torch

MODEL = os.environ.get("EPHAPSE_GEMMA_MODEL", "google/gemma-2-2b")
# Gated-repo fallback. The official checkpoint requires an HF login this sandbox
# has no token for; this mirror is the same architecture, so load/RSS/latency and
# the residual-stream geometry are measurable with it. Recon error from the mirror
# is architecture-comparable but not bit-identical to the official checkpoint.
MIRROR = os.environ.get("EPHAPSE_GEMMA_MIRROR", "unsloth/gemma-2-2b")
SAE_RELEASE = "gemma-scope-2b-pt-res-canonical"
SAE_ID = "layer_12/width_16k/canonical"
N_BATCH = 64
N_RECON = 16
SEQ_LEN = 32

# Weight dtype for the mirror load. The prior run (20260923-0251-r1qp) measured
# that fp32 + batch 64 OOMs in this sandbox: 11.48 GB peak RSS of 15 GiB, leaving
# 2.54 GB against the ~2.61 GB the batch-64 forward needs. bf16 weights are
# 5.23 GB, so the same batch fits with ~7 GB headroom. `plan` (measure_footprint.py)
# confirms: bf16 batch-64 = 8.84 GB vs 13.43 GB MemAvailable. Override with
# EPHAPSE_DTYPE=fp32 to reproduce the infeasible path.
_DTYPE_NAME = os.environ.get("EPHAPSE_DTYPE", "bf16")
_DTYPES = {"bf16": torch.bfloat16, "fp32": torch.float32, "fp16": torch.float16}
DTYPE = _DTYPES.get(_DTYPE_NAME, torch.bfloat16)

PROMPTS = [
    "The Eiffel Tower is located in the city of Paris",
    "Photosynthesis converts light into chemical energy",
    "The prime minister announced a new policy on",
    "Integers form a ring under addition and",
    "Mitochondria are the powerhouse of the",
    "The stock market fell sharply after the",
    "Water boils at one hundred degrees",
    "Recursion is when a function calls",
]


def rss_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def env_report():
    print("=== environment ===")
    print(f"  torch                : {torch.__version__}")
    print(f"  torch threads        : {torch.get_num_threads()}")
    print(f"  dtype                : {_DTYPE_NAME}{' (bf16 weights, fp32 compute)' if _DTYPE_NAME == 'bf16' else ''}")
    print(f"  HF_HOME              : {os.environ.get('HF_HOME', '<unset>')}")
    print(f"  HF_TOKEN present     : {bool(os.environ.get('HF_TOKEN'))}")
    print(f"  cgroup mem limit     : {os.environ.get('MEMORY_LIMIT', '<not exported>')}")
    print(f"  peak RSS at start    : {rss_gb():.2f} GB")


def load_model():
    """Load gemma-2-2b on CPU. Returns a wrapper dict, or None on failure.

    Tries TransformerLens first (the repo standard, exact SAE hook parity). The
    official checkpoint is gated and this sandbox has no HF token, so the fallback
    runs the architecture-identical public mirror through plain `transformers`.
    """
    print()
    print(f"=== 1. model load: {MODEL} ===")
    print(f"  peak RSS before load : {rss_gb():.2f} GB")
    t0 = time.time()
    try:
        from transformer_lens import HookedTransformer

        model = HookedTransformer.from_pretrained(MODEL, device="cpu")
        load_s = time.time() - t0
        n_params = sum(p.numel() for p in model.parameters())
        print("  PATH: transformer_lens (exact SAE hook parity)")
        print(f"  LOADED  wall={load_s:.1f}s  params={n_params/1e9:.3f}B")
        print(f"  cfg: n_layers={model.cfg.n_layers} d_model={model.cfg.d_model} "
              f"d_vocab={model.cfg.d_vocab}")
        print(f"  peak RSS after load  : {rss_gb():.2f} GB")
        return {"kind": "tl", "model": model, "tok": model.tokenizer, "load_s": load_s}
    except Exception as e:
        print(f"  transformer_lens path failed after {time.time() - t0:.1f}s: "
              f"{type(e).__name__}: {str(e)[:160]}")

    print(f"  --- fallback: plain transformers on mirror {MIRROR} ---")
    t0 = time.time()
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(MIRROR)
        model = AutoModelForCausalLM.from_pretrained(MIRROR, dtype=DTYPE)
        model.eval()
        load_s = time.time() - t0
        cfg = model.config
        n_params = sum(p.numel() for p in model.parameters())
        print("  PATH: transformers (mirror — architecture-identical, not official weights)")
        print(f"  LOADED  wall={load_s:.1f}s  params={n_params/1e9:.3f}B")
        print(f"  cfg: n_layers={cfg.num_hidden_layers} d_model={cfg.hidden_size} "
              f"d_vocab={cfg.vocab_size}")
        print(f"  peak RSS after load  : {rss_gb():.2f} GB")
        return {"kind": "hf", "model": model, "tok": tok, "load_s": load_s,
                "n_layers": cfg.num_hidden_layers}
    except Exception as e:
        print(f"  LOAD FAILED after {time.time() - t0:.1f}s")
        print(f"  exception: {type(e).__name__}: {str(e)[:400]}")
        return None


def _forward(modelw, prompts):
    if modelw["kind"] == "tl":
        return modelw["model"](prompts)
    enc = modelw["tok"](prompts, return_tensors="pt", padding=True)
    return modelw["model"](**enc).logits


def _resid_post(modelw, prompts, layer):
    """Residual-stream activations after block `layer`, flat to [n_tokens, d_in]."""
    if modelw["kind"] == "tl":
        hook = f"blocks.{layer}.hook_resid_post"
        with torch.no_grad():
            _, cache = modelw["model"].run_with_cache(
                prompts, names_filter=lambda n: n == hook, return_type=None
            )
        t = cache[hook]
        return t.reshape(-1, t.shape[-1])
    enc = modelw["tok"](prompts, return_tensors="pt", padding=True)
    with torch.no_grad():
        out = modelw["model"](**enc, output_hidden_states=True)
    # HF hidden_states[0] is the embedding output; hidden_states[i] is the output
    # of block i-1, so hook_resid_post of block `layer` is hidden_states[layer+1].
    # Cast to fp32: the SAE is an fp32 artefact, and bf16 residual geometry is not
    # bit-identical to fp32 (the caveat recorded by run 20260923-0251-r1qp, #40).
    t = out.hidden_states[layer + 1].float()
    return t.reshape(-1, t.shape[-1])


def forward_stage(modelw):
    print()
    print("=== 2. forward pass ===")
    modelw["model"].eval()
    prompt = PROMPTS[0]

    # warm-up, then median of 5 single-prompt passes
    with torch.no_grad():
        _forward(modelw, [prompt])
        times = []
        for _ in range(5):
            t0 = time.time()
            _forward(modelw, [prompt])
            times.append(time.time() - t0)
    times.sort()
    single_ms = times[len(times) // 2] * 1000
    print(f"  single prompt (median of 5, ~{len(prompt.split())} tok): {single_ms:.0f} ms")

    batch = [PROMPTS[i % len(PROMPTS)] for i in range(N_BATCH)]
    with torch.no_grad():
        t0 = time.time()
        _forward(modelw, batch)
        batch_s = time.time() - t0
    print(f"  batch {N_BATCH} (median-length prompts)        : {batch_s:.2f}s "
          f"({batch_s / N_BATCH * 1000:.0f} ms/prompt)")
    print(f"  ratio batch64/single                        : {batch_s / N_BATCH * 1000 / single_ms:.1f}x")
    print(f"  peak RSS after forward: {rss_gb():.2f} GB")


def sae_stage(modelw=None):
    """Load a Gemma Scope residual SAE, encode, and measure reconstruction error."""
    print()
    print(f"=== 3. SAE load: {SAE_RELEASE} / {SAE_ID} ===")
    try:
        from sae_lens import SAE
    except Exception as e:
        print(f"  sae_lens import failed: {type(e).__name__}: {e}")
        return
    t0 = time.time()
    try:
        sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=SAE_ID, device="cpu")
    except Exception as e:
        print(f"  SAE LOAD FAILED after {time.time() - t0:.1f}s")
        print(f"  exception: {type(e).__name__}: {str(e)[:400]}")
        return
    hook = sae.cfg.metadata.hook_name
    print(f"  LOADED wall={time.time() - t0:.1f}s")
    print(f"  d_in={sae.cfg.d_in} d_sae={sae.cfg.d_sae} hook={hook}")
    print(f"  arch={sae.cfg.architecture()} model_name={sae.cfg.metadata.model_name}")
    print(f"  neuronpedia_id={sae.cfg.metadata.neuronpedia_id}")

    print()
    print("=== 4. reconstruction error (resid_post vs decode(encode)) ===")
    torch.manual_seed(0)
    if modelw is not None:
        layer = int(SAE_ID.split("_")[1].split("/")[0])
        resid = _resid_post(modelw, PROMPTS[:N_RECON], layer)
        print(f"  activations sourced from the model's residual stream (block {layer})")
    else:
        # model unavailable: use the SAE's own input dimension with random activations,
        # so the encode/decode path is still exercised (recon error is not comparable
        # to the 0.362 figure, which is measured on real activations).
        print("  NOTE: gemma-2-2b unavailable — using random activations; recon error is")
        print("        NOT comparable to the DEC-020 0.362 figure.")
        resid = torch.randn(N_RECON * SEQ_LEN, sae.cfg.d_in)

    with torch.no_grad():
        feats = sae.encode(resid)
        recon = sae.decode(feats)
        rel_err = (torch.norm(resid - recon) / torch.norm(resid)).item()
        cos = torch.nn.functional.cosine_similarity(
            resid.reshape(-1), recon.reshape(-1), dim=0
        ).item()
    print(f"  activations: {tuple(resid.shape)}")
    print(f"  relative error: {rel_err:.4f}   (DEC-020 at pythia-70m: 0.362)")
    print(f"  cosine        : {cos:.4f}")
    print(f"  mean L0 active: {feats.gt(0).float().sum(-1).mean().item():.0f}")


def main():
    env_report()
    modelw = load_model()
    if modelw is not None:
        forward_stage(modelw)
    else:
        print()
        print("=== 2. forward pass: SKIPPED (model did not load) ===")
    sae_stage(modelw)
    print()
    print(f"FINAL peak RSS: {rss_gb():.2f} GB")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise