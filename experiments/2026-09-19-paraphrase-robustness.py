"""Issue #6 (re-run): paraphrase / non-verbal robustness control.

**Model:** pythia-70m-deduped, fp32, CPU, SAE `pythia-70m-deduped-res-sm`,
  hook `blocks.3.hook_resid_post` (d_in=512, d_sae=32768).
**Inputs:** `Corpus/verbal_symbolic.json` — 200 instances of 8 mathematical
  relations, each rendered (a) verbal/narrative, (b) symbolic (digits and
  operators), (c) paraphrase. Each rendering is wrapped in a shared carrier
  passage so the model has enough context (see FIXES below).
**Question:** does an SAE feature that fires on a relation's verbal rendering
  also fire on the lexically-disjoint symbolic rendering of *the same*
  relation? Equivalently: is a flagged co-activation reading meaning or
  surface form?
**Null:** pairing permutation (N_PERM=200). Matched pairs (verb_i, sym_i) are
  compared against shuffled pairs (verb_i, sym_j, i != j) — equally
  lexically disjoint but asserting different relations.
**Correction:** max-statistic permutation (DEC-016). BH-FDR is NOT used.
**Issue:** #6 (run 20260919-0213-tsm5), re-run after DEC-018.

FIXES applied since the first run (both found by diagnostic, DEC-018):

  1. **PER-FEATURE thresholds, not a pooled percentile.** The first run used
     the 99th percentile of positive activations pooled across *all* features
     (11.08), which is dominated by a few extreme features. At that threshold
     **32,764 of 32,768 features fired on ZERO prompts** — the detector was
     switched off, not discriminating. Now each feature gets its own threshold
     from its own positive-activation distribution, plus a selectivity band so
     features that fire on ~everything (bridge saturates to 1.0 under any
     pairing) are excluded.

  2. **Carrier passage, not bare prompts.** Median prompt length was 5 tokens
     in the first run, which starves the residual stream. Measured usable
     features (firing on >=20% of prompts): 541 bare (5 tok) vs 909 at
     sentence length (10 tok) vs 1188 at passage length (31 tok). All
     renderings are now embedded in a shared carrier passage, and *only the
     rendering differs*, so the comparison stays clean.

STATISTIC:
  `bridge(f)` = P(f fires in A AND B) on the given pairing, restricted to
  features whose firing rate lies in [SEL_LO, SEL_HI]. Compared against the
  same quantity under permuted pairing.
"""
import json
import os

import numpy as np
import torch

MODEL = "pythia-70m-deduped"
SAE_RELEASE = "pythia-70m-deduped-res-sm"
HOOK = "blocks.3.hook_resid_post"

BATCH = 32
N_PERM = 200
SEED = 0
SEL_LO = 0.05
SEL_HI = 0.60
PER_FEATURE_PCT = 95

CARRIER = ("Consider the following arithmetic claim stated in a certain form, "
           "and note carefully what relation it asserts between the two "
           "quantities involved. Claim: {claim} End of claim.")

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "Corpus", "verbal_symbolic.json")


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
    """Threshold each feature on its OWN positive activations."""
    thr = np.full(fn.shape[1], np.inf)
    for j in range(fn.shape[1]):
        col = fn[:, j]
        pos = col[col > 0]
        if pos.size >= 5:
            thr[j] = np.percentile(pos, pct)
    return fn > thr[None, :], thr


def bridge(bin_a, bin_b, perm, sel):
    aligned = bin_b[perm]
    return (bin_a[:, sel] & aligned[:, sel]).mean(axis=0)


def main():
    from transformer_lens import HookedTransformer
    from sae_lens import SAE

    print("=== issue #6 re-run: non-verbal robustness (bug fixes applied) ===")
    d = json.load(open(CORPUS))
    verb, sym, par = d["narrative"], d["symbolic"], d["paraphrase"]
    n = min(len(verb), len(sym), len(par))
    verb, sym, par = verb[:n], sym[:n], par[:n]

    av = [CARRIER.format(claim=x) for x in verb]
    asy = [CARRIER.format(claim=x) for x in sym]
    ap = [CARRIER.format(claim=x) for x in par]

    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    tok = model.tokenizer
    lens = [len(tok.encode(t, add_special_tokens=False)) for t in av]
    print(f"pairs: n={n}  carrier passage median {int(np.median(lens))} tokens")
    print(f"  verbal tail  : {av[0][-38:]!r}")
    print(f"  symbolic tail: {asy[0][-38:]!r}")

    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")

    print("\nencoding verbal...")
    fv = encode(model, sae, av)
    print("encoding symbolic...")
    fs = encode(model, sae, asy)
    print("encoding paraphrase...")
    fp = encode(model, sae, ap)

    bv, thr_v = per_feature_binarize(fv)
    bs, _ = per_feature_binarize(fs)
    bp, _ = per_feature_binarize(fp)

    print(f"\nfeatures receiving a finite per-feature threshold: "
          f"{int(np.isfinite(thr_v).sum())}")
    print(f"verbal: features firing on >=1 prompt: "
          f"{int(((bv).mean(axis=0) > 0).sum())}")

    rng = np.random.default_rng(SEED)

    def run(bin_a, bin_b, label):
        ra, rb = bin_a.mean(axis=0), bin_b.mean(axis=0)
        sel = np.where((ra >= SEL_LO) & (ra <= SEL_HI) &
                       (rb >= SEL_LO) & (rb <= SEL_HI))[0]
        if sel.size == 0:
            print(f"  {label:28} no features in selectivity band "
                  f"[{SEL_LO},{SEL_HI}]")
            return {"label": label, "n_selected": 0}
        matched = bridge(bin_a, bin_b, np.arange(n), sel)
        perm_max = np.empty(N_PERM)
        for p in range(N_PERM):
            perm_max[p] = bridge(bin_a, bin_b, rng.permutation(n), sel).max()
        cutoff = float(np.percentile(perm_max, 95))
        best = float(matched.max())
        surv = int((matched > cutoff).sum())
        print(f"  {label:28} selected={sel.size:5d} best={best:.4f} "
              f"cutoff={cutoff:.4f} survivors={surv}")
        return {"label": label, "n_selected": int(sel.size), "best": best,
                "cutoff": cutoff, "survivors": surv}

    print("\n=== arm 1: MATCHED (same relation, verbal vs symbolic) ===")
    a1 = run(bv, bs, "matched verbal-symbolic")
    print("=== arm 2: NULL (different relation) ===")
    shuf = rng.permutation(n)
    a2 = run(bv, bs[shuf], "shuffled (null)")
    print("=== arm 3: PARAPHRASE (same relation, reworded) ===")
    a3 = run(bv, bp, "paraphrase within-words")

    print("\n=== summary ===")
    print(json.dumps({"n_pairs": n, "sel_band": [SEL_LO, SEL_HI],
                      "per_feature_pct": PER_FEATURE_PCT, "arms": [a1, a2, a3]},
                     indent=2))


if __name__ == "__main__":
    main()