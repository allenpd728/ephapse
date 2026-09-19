"""Re-run issue #5's positive control with per-feature thresholds.

**Model:** pythia-70m-deduped, fp32, CPU, SAE `pythia-70m-deduped-res-sm`,
  hook `blocks.3.hook_resid_post`.
**Inputs:** Corpus/paired.json — 1310 paired passages, wikitext prose (A) vs
  codeparrot Python (B); planted tokens `zorblat`/`quimble` on both sides at
  varying rates.
**Question:** does #5's positive control still pass once the per-feature
  threshold bug (DEC-018) is fixed, and how does sensitivity change?
**Null:** pairing permutation, N_PERM=100, max-statistic cutoff (DEC-016).
**Correction:** max-statistic permutation cutoff; BH-FDR unused (DEC-016).
**Issue:** #5 re-run (run 20260919-0213-tsm5), following DEC-018.

WHY RE-RUN:
  #5 used the 99th percentile of positive activations POOLED across all
  features, the same rule that disabled the detector in #6's first run
  (32,764/32,768 features firing on zero prompts). #5's pass was therefore
  achieved with a largely-off detector. This re-run applies per-feature
  thresholds so the sensitivity claim can be trusted or retracted.
"""
import json
import os

import numpy as np
import torch

MODEL = "pythia-70m-deduped"
SAE_RELEASE = "pythia-70m-deduped-res-sm"
HOOK = "blocks.3.hook_resid_post"

BATCH = 32
N_PERM = 100
SEED = 0
SEL_LO, SEL_HI = 0.01, 0.60
PER_FEATURE_PCT = 95
TOKEN_X, TOKEN_Y = "zorblat", "quimble"

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "Corpus", "paired.json")


def encode(model, sae, texts):
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH):
            _, c = model.run_with_cache(texts[i:i + BATCH],
                                        names_filter=lambda n: n == HOOK)
            out.append(sae.encode(c[HOOK]).amax(dim=1).cpu().numpy())
            del c
    return np.concatenate(out, axis=0)


def per_feature_binarize(fn, pct=PER_FEATURE_PCT):
    thr = np.full(fn.shape[1], np.inf)
    for j in range(fn.shape[1]):
        col = fn[:, j]
        pos = col[col > 0]
        if pos.size >= 5:
            thr[j] = np.percentile(pos, pct)
    return fn > thr[None, :], thr


def npmi_matrix(ba, bb):
    n = ba.shape[0]
    co = ba.T.astype(np.float64) @ bb.astype(np.float64)
    pa = ba.mean(axis=0)[:, None]
    pb = bb.mean(axis=0)[None, :]
    exp = pa * pb * n
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log(co / exp)
        denom = -np.log(co / n)
        out = np.where((co > 0) & (denom > 0), pmi / denom, 0.0)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def select(b, lo, hi):
    r = b.mean(axis=0)
    return np.where((r >= lo) & (r <= hi))[0]


def run_detector(fa, fb, label, rng):
    ba, bb = fa, fb
    ia, ib = select(ba, SEL_LO, SEL_HI), select(bb, SEL_LO, SEL_HI)
    ba, bb = ba[:, ia], bb[:, ib]
    if ba.shape[1] == 0 or bb.shape[1] == 0:
        print(f"  {label:22} no features in band")
        return {"label": label, "n_pairs": 0}
    score = npmi_matrix(ba, bb)
    flat = score.ravel()
    perm_max = np.empty(N_PERM)
    for p in range(N_PERM):
        perm_max[p] = npmi_matrix(ba[rng.permutation(ba.shape[0])], bb).max()
    cutoff = float(np.percentile(perm_max, 95))
    best = float(flat.max())
    surv = int((flat > cutoff).sum())
    print(f"  {label:22} feats=({ba.shape[1]},{bb.shape[1]}) "
          f"pairs={flat.size:6d} best={best:.4f} cutoff={cutoff:.4f} "
          f"above={surv}")
    return {"label": label, "n_pairs": int(flat.size), "best": best,
            "cutoff": cutoff, "above_cutoff": surv}


def main():
    from transformer_lens import HookedTransformer
    from sae_lens import SAE

    print("=== issue #5 re-run: positive control with per-feature thresholds ===")
    c = json.load(open(CORPUS))
    A, B = c["A"], c["B"]
    n = min(len(A), len(B))
    A, B = A[:n], B[:n]
    print(f"corpus: {n} paired passages/domain")

    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")
    rng = np.random.default_rng(SEED)

    print("\n=== negative control: no injection ===")
    bva, _ = per_feature_binarize(encode(model, sae, A))
    bvb, _ = per_feature_binarize(encode(model, sae, B))
    print(f"  features with finite threshold: A={int(np.isfinite(_).sum())}")
    neg = run_detector(bva, bvb, "no injection", rng)

    print("\n=== injection sweep ===")
    sweep = []
    for frac in (0.01, 0.02, 0.05, 0.10, 0.20):
        k = max(2, int(n * frac))
        sig = rng.choice(n, size=k, replace=False)
        aa = list(A)
        bb = list(B)
        for i in sig:
            aa[i] = aa[i] + f" {TOKEN_X} {TOKEN_Y}"
            bb[i] = bb[i] + f" {TOKEN_X} {TOKEN_Y}"
        fa, _ = per_feature_binarize(encode(model, sae, aa))
        fb, _ = per_feature_binarize(encode(model, sae, bb))
        sweep.append(run_detector(fa, fb, f"rate {frac:.2f} (k={k})", rng))

    print("\n=== summary ===")
    print(json.dumps({"sel_band": [SEL_LO, SEL_HI],
                      "per_feature_pct": PER_FEATURE_PCT,
                      "negative_control": neg, "sweep": sweep}, indent=2))


if __name__ == "__main__":
    main()