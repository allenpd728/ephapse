"""Test whether SAE feature activity depends on prompt length.

**Model:** pythia-70m-deduped, fp32, CPU, SAE `pythia-70m-deduped-res-sm`,
  hook `blocks.3.hook_resid_post`.
**Inputs:** the same 200 relations from Corpus/verbal_symbolic.json, rendered
  at three context lengths: bare (3-4 tokens), short sentence (~15 tokens),
  and a passage (~60+ tokens).
**Question:** does the near-zero feature activity in #6's first run come from
  short prompts, and at what length does the substrate become usable?
**Issue:** #6 (run 20260919-0213-tsm5). Root-cause test for the #6 saturation.

Infrastructure/diagnostic — no null model applies.

#6's first run found 32,764/32,768 features firing on ZERO prompts at a
99th-percentile threshold. Hypothesis: 3-4 token prompts give the residual
stream too little to encode, so the detector is blind by construction rather
than because there is no cross-domain structure.
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

FILLER = ("In the following statement about quantity, consider carefully "
          "what the relation asserts about the two values involved, and "
          "determine whether the claim holds: ")


def encode(model, sae, texts, batch=32):
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            _, c = model.run_with_cache(texts[i:i + batch],
                                        names_filter=lambda n: n == HOOK)
            out.append(sae.encode(c[HOOK]).amax(dim=1).cpu().numpy())
            del c
    return np.concatenate(out, axis=0)


def activity(fn, label, tok):
    n_tok = None
    print(f"\n  --- {label} ---")
    print(f"    n_features firing on >0 prompts: "
          f"{int(((fn > 0).mean(axis=0) > 0).sum())}")
    for thr_desc, thr in [(">0", 1e-6),
                          ("median of positive", float(np.percentile(fn[fn > 0], 50))),
                          ("90th pct of positive", float(np.percentile(fn[fn > 0], 90)))]:
        fire = (fn > thr).mean(axis=0)
        n_any = int((fire > 0).sum())
        n_generous = int((fire > 0.20).sum())
        print(f"    thr={thr_desc:22} ({thr:8.4f}): "
              f"{n_any:6d} fire on >=1, {n_generous:5d} fire on >=20%")


if __name__ == "__main__":
    from transformer_lens import HookedTransformer
    from sae_lens import SAE

    d = json.load(open(CORPUS))
    nar = d["narrative"]
    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    tok = model.tokenizer
    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")

    variants = {
        "bare (3-4 tokens)": nar,
        "short sentence (~20 tokens)": [f"The relation {n} is being examined." for n in nar],
        "passage (~60 tokens)": [f"{FILLER}{n}." for n in nar],
    }

    print("=== token-length check ===")
    for label, texts in variants.items():
        lens = [len(tok.encode(t, add_special_tokens=False)) for t in texts]
        print(f"  {label:32} median {int(np.median(lens)):3d} tokens "
              f"(min {min(lens)}, max {max(lens)})")

    print("\n=== feature activity by prompt length ===")
    for label, texts in variants.items():
        fn = encode(model, sae, texts)
        activity(fn, label, tok)

    print("\n=== reading ===")
    print("  If activity rises sharply with length, #6's design must use")
    print("  passages, not short prompt sets, and the near-zero activity was a")
    print("  property of the input format rather than of the relations.")