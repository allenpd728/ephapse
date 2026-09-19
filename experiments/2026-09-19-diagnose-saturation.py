"""Diagnose the saturated bridge statistic from issue #6's first run.

**Model:** pythia-70m-deduped, fp32, CPU, SAE `pythia-70m-deduped-res-sm`.
**Inputs:** Corpus/verbal_symbolic.json (200 narrative/symbolic/paraphrase).
**Question:** how many SAE features fire on ~every prompt (making the bridge
  statistic saturate), and what feature-selection rule gives discrimination?
**Issue:** #6 (run 20260919-0213-tsm5). Diagnostic for the saturation bug.

Infrastructure/diagnostic — no null model applies.

The first #6 run returned best=1.0=cutoff in ALL arms including the null, so
the statistic could not discriminate. Cause: bridge(f) = P(f fires in A and B);
any feature firing on >=1 token in every prompt has bridge=1.0 under any
pairing. This measures how prevalent that is and picks a fix.
"""
import json
import os

import numpy as np
import torch

MODEL = "pythia-70m-deduped"
SAE_RELEASE = "pythia-70m-deduped-res-sm"
HOOK = "blocks.3.hook_resid_post"
CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "Corpus", "verbal_symbolic.json")


def encode(model, sae, texts, batch=32):
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            _, c = model.run_with_cache(texts[i:i + batch],
                                        names_filter=lambda n: n == HOOK)
            out.append(sae.encode(c[HOOK]).amax(dim=1).cpu().numpy())
            del c
    return np.concatenate(out, axis=0)


if __name__ == "__main__":
    from transformer_lens import HookedTransformer
    from sae_lens import SAE

    d = json.load(open(CORPUS))
    nar, sym = d["narrative"], d["symbolic"]
    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")

    fn = encode(model, sae, nar)
    print(f"encoded narrative: {fn.shape}  (n_prompts, d_sae)")

    print("\n=== feature firing-rate distribution (narrative) ===")
    for pct in (50, 90, 99, 99.9):
        thr = float(np.percentile(fn[fn > 0], pct))
        fire = (fn > thr).mean(axis=0)
        print(f"  threshold at {pct:>5} pct of positive acts = {thr:8.3f} -> "
              f"{int((fire > 0.95).sum()):6d} features fire on >95% of prompts")

    print("\n=== why the original failed ===")
    thr = float(np.percentile(fn[fn > 0], 99))
    bin_n = fn > thr
    always = bin_n.mean(axis=0) > 0.95
    print(f"  original threshold {thr:.3f}: {int(always.sum())} features fire on "
          f">95% of prompts")
    print("  -> bridge(f)=1.0 for those under ANY pairing, including the null,")
    print("     so max over features saturates at 1.0 in every arm. No contrast.")
    print(f"\n  features firing on 0 prompts: {int((bin_n.mean(axis=0) == 0).sum())}")
    print(f"  features firing on >1 and <95%: "
          f"{int(((bin_n.mean(axis=0) > 0) & (~always)).sum())}")
    print("\n  FIX: require feature selectivity -- a feature must fire on a")
    print("  bounded fraction of prompts, e.g. 5% to 60%, so bridge can vary.")