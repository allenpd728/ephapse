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
SAE_RELEASE = "gemma-scope-2b-pt-res-canonical"
SAE_ID = "layer_12/width_16k/canonical"
N_BATCH = 64
N_RECON = 16
SEQ_LEN = 32

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
    print(f"  dtype                : float32 (CPU workload)")
    print(f"  HF_HOME              : {os.environ.get('HF_HOME', '<unset>')}")
    print(f"  HF_TOKEN present     : {bool(os.environ.get('HF_TOKEN'))}")
    print(f"  cgroup mem limit     : {os.environ.get('MEMORY_LIMIT', '<not exported>')}")
    print(f"  peak RSS at start    : {rss_gb():.2f} GB")


def model_stage():
    """Load gemma-2-2b on CPU and time a forward pass. Returns (model, tok) or (None, None)."""
    print()
    print(f"=== 1. model load: {MODEL} ===")
    print(f"  peak RSS before load : {rss_gb():.2f} GB")
    t0 = time.time()
    try:
        from transformer_lens import HookedTransformer

        model = HookedTransformer.from_pretrained(MODEL, device="cpu")
        load_s = time.time() - t0
        n_params = sum(p.numel() for p in model.parameters())
        print(f"  LOADED  wall={load_s:.1f}s  params={n_params/1e9:.3f}B")
        print(f"  cfg: n_layers={model.cfg.n_layers} d_model={model.cfg.d_model} "
              f"d_vocab={model.cfg.d_vocab}")
        print(f"  peak RSS after load  : {rss_gb():.2f} GB")
        return model, load_s
    except Exception as e:
        print(f"  LOAD FAILED after {time.time() - t0:.1f}s")
        print(f"  exception: {type(e).__name__}: {str(e)[:400]}")
        return None, None


def forward_stage(model):
    print()
    print("=== 2. forward pass ===")
    model.eval()
    prompt = PROMPTS[0]

    # warm-up, then median of 5 single-prompt passes
    with torch.no_grad():
        model(prompt)
        times = []
        for _ in range(5):
            t0 = time.time()
            model(prompt)
            times.append(time.time() - t0)
    times.sort()
    single_ms = times[len(times) // 2] * 1000
    print(f"  single prompt (median of 5, ~{len(prompt.split())} tok): {single_ms:.0f} ms")

    batch = [PROMPTS[i % len(PROMPTS)] for i in range(N_BATCH)]
    with torch.no_grad():
        t0 = time.time()
        model(batch)
        batch_s = time.time() - t0
    print(f"  batch {N_BATCH} (median-length prompts)        : {batch_s:.2f}s "
          f"({batch_s / N_BATCH * 1000:.0f} ms/prompt)")
    print(f"  ratio batch64/single                        : {batch_s / N_BATCH * 1000 / single_ms:.1f}x")
    print(f"  peak RSS after forward: {rss_gb():.2f} GB")


def sae_stage(model=None):
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
    if model is not None:
        with torch.no_grad():
            _, cache = model.run_with_cache(
                PROMPTS[:N_RECON],
                names_filter=lambda n: n == hook,
                return_type=None,
            )
        resid = cache[hook].reshape(-1, sae.cfg.d_in)
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
    model, _ = model_stage()
    if model is not None:
        forward_stage(model)
    else:
        print()
        print("=== 2. forward pass: SKIPPED (model did not load) ===")
    sae_stage(model)
    print()
    print(f"FINAL peak RSS: {rss_gb():.2f} GB")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise