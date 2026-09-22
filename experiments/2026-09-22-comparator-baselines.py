"""Issue #37 — supervised comparator baselines on the #6 paraphrase corpus.

**Model:** pythia-70m-deduped, fp32, CPU, SAE `pythia-70m-deduped-res-sm`,
  hook `blocks.3.hook_resid_post` (d_in=512, d_sae=32768).
**Inputs:** `Corpus/verbal_symbolic.json` — 200 instances of the 8 relation
  templates, each rendered verbal / symbolic / paraphrase, wrapped in the same
  carrier passage #6 uses so only the rendering differs.
**Question:** run the *same* inputs through all three substrates — the SAE, a
  difference-in-means baseline and a logistic-regression linear probe — and
  report the bridge/detection reading side by side on the matched (verbal vs
  symbolic), shuffled-null and paraphrase arms. Which substrate, if any, finds a
  rendering-invariant relation direction?
**Null:** pairing permutation (N_PERM=200) for the SAE bridge, exactly as #6.
  The supervised directions are fit on the verbal arm and scored on the other
  arm, so their transfer is the check, not a within-arm fit.
**Correction:** max-statistic permutation (DEC-016) for the SAE arm; the AUROC
  comparators are threshold-free and need none.
**Issue:** #37 (run 20260922-1101-k7q2), enabling DEC-034 item 1.

WHAT THIS MEASURES, AND WHAT IT DOES NOT. A probe yields a *direction*, not an
enumerable feature with a decoder vector; the SAE's justification is the feature
list, so the SAE reading stays the primary one and the comparators are a
sensitivity check on the detector (DEC-034 method constraint). Axis: each arm
reports the SAE bridge statistic alongside the two supervised AUROCs.

SUPERVISED LABEL. The construct is the relation operator; positive class is the
`>` family (75 of 200 instances, 3 of the 8 templates). A direction fit on the
*verbal* rendering that separates `>` from `<`/`=` on the *symbolic* rendering is
the rendering-invariant relation direction the #6 question is about. Geometry:
all vectors are in the raw hook basis (PRIOR_ART §9 — stated, not hidden).

Run:  python3 experiments/2026-09-22-comparator-baselines.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tooling", "gates"))

MODEL = "pythia-70m-deduped"
SAE_RELEASE = "pythia-70m-deduped-res-sm"
HOOK = "blocks.3.hook_resid_post"

BATCH = 32
N_PERM = 200
SEED = 0
SEL_LO, SEL_HI = 0.05, 0.60
PER_FEATURE_PCT = 95

CARRIER = ("Consider the following arithmetic claim stated in a certain form, "
           "and note carefully what relation it asserts between the two "
           "quantities involved. Claim: {claim} End of claim.")

CORPUS = os.path.join(REPO, "Corpus", "verbal_symbolic.json")


def encode(model, sae, texts):
    """Max-over-positions SAE feature activations, plus the raw hook resid."""
    import torch
    feats, resids = [], []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH):
            _, c = model.run_with_cache(texts[i:i + BATCH],
                                        names_filter=lambda n: n == HOOK)
            feats.append(sae.encode(c[HOOK]).amax(dim=1).cpu().numpy())
            resids.append(c[HOOK][:, -1, :].cpu().numpy())
            del c
    return np.concatenate(feats, axis=0), np.concatenate(resids, axis=0)


def per_feature_binarize(fn, pct=PER_FEATURE_PCT):
    """Threshold each feature on its OWN positive activations (the #6 fix)."""
    thr = np.full(fn.shape[1], np.inf)
    for j in range(fn.shape[1]):
        col = fn[:, j]
        pos = col[col > 0]
        if pos.size >= 5:
            thr[j] = np.percentile(pos, pct)
    return fn > thr[None, :]


def sae_bridge(bin_a, bin_b, perm, sel):
    aligned = bin_b[perm]
    return (bin_a[:, sel] & aligned[:, sel]).mean(axis=0)


def sae_arm(bin_a, bin_b, n, rng, label):
    ra, rb = bin_a.mean(axis=0), bin_b.mean(axis=0)
    sel = np.where((ra >= SEL_LO) & (ra <= SEL_HI) &
                   (rb >= SEL_LO) & (rb <= SEL_HI))[0]
    if sel.size == 0:
        return {"label": label, "n_selected": 0}
    matched = sae_bridge(bin_a, bin_b, np.arange(n), sel)
    perm_max = np.array([sae_bridge(bin_a, bin_b, rng.permutation(n), sel).max()
                         for _ in range(N_PERM)])
    cutoff = float(np.percentile(perm_max, 95))
    return {"label": label, "n_selected": int(sel.size),
            "best": float(matched.max()), "cutoff": cutoff,
            "survivors": int((matched > cutoff).sum())}


def supervised_arm(acts_train, labels_train, acts_test, labels_test):
    """Fit both comparators on the verbal arm, score AUROC on the test arm."""
    import comparators as C
    pos, neg = acts_train[labels_train == 1], acts_train[labels_train == 0]
    dim = C.difference_in_means(pos, neg)
    w, b = C.fit_linear_probe(acts_train, labels_train)
    mu, sd = acts_train.mean(axis=0), acts_train.std(axis=0)
    return {
        "difference_in_means": round(C.auroc(acts_test @ dim, labels_test), 4),
        "linear_probe": round(
            C.auroc(C.probe_scores(acts_test, w, b, (mu, sd)), labels_test), 4),
    }


def main():
    from transformer_lens import HookedTransformer
    from sae_lens import SAE

    d = json.load(open(CORPUS))
    verb, sym, par, meta = d["narrative"], d["symbolic"], d["paraphrase"], d["meta"]
    n = min(len(verb), len(sym), len(par))
    verb, sym, par, meta = verb[:n], sym[:n], par[:n], meta[:n]

    # Positive class: the `>` relation family (templates 0, 3, 6).
    labels = np.array([1 if m["relation"] in (0, 3, 6) else 0 for m in meta])
    print(f"pairs n={n}  positive class (`>` family): {int(labels.sum())}")

    av = [CARRIER.format(claim=x) for x in verb]
    asy = [CARRIER.format(claim=x) for x in sym]
    ap = [CARRIER.format(claim=x) for x in par]

    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    tok = model.tokenizer
    lens = [len(tok.encode(t, add_special_tokens=False)) for t in av]
    print(f"carrier passage median {int(np.median(lens))} tokens")

    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")

    print("encoding verbal / symbolic / paraphrase ...")
    fv, rv = encode(model, sae, av)
    fs, rs = encode(model, sae, asy)
    fp, rp = encode(model, sae, ap)

    bv = per_feature_binarize(fv)
    bs = per_feature_binarize(fs)

    rng = np.random.default_rng(SEED)
    shuf = rng.permutation(n)

    print("\n=== arm 1: MATCHED (verbal -> symbolic, same relation) ===")
    a1 = sae_arm(bv, bs, n, rng, "matched")
    print("  SAE:", a1)
    m1 = supervised_arm(rv, labels, rs, labels)
    print("  comparators:", m1)

    print("=== arm 2: SHUFFLED NULL (different relation) ===")
    a2 = sae_arm(bv, bs[shuf], n, rng, "shuffled")
    print("  SAE:", a2)
    m2 = supervised_arm(rv, labels, rs[shuf], labels)
    print("  comparators:", m2)

    print("=== arm 3: PARAPHRASE (verbal -> paraphrase, same relation) ===")
    bp = per_feature_binarize(fp)
    a3 = sae_arm(bv, bp, n, rng, "paraphrase")
    print("  SAE:", a3)
    m3 = supervised_arm(rv, labels, rp, labels)
    print("  comparators:", m3)

    record = {
        "kind": "comparator_baselines",
        "n": n,
        "positive_class": "greater-than relation family (templates 0,3,6)",
        "geometry": "raw hook basis (blocks.3.hook_resid_post), cosine not used",
        "arms": [
            {"arm": "matched", "sae": a1, **m1},
            {"arm": "shuffled_null", "sae": a2, **m2},
            {"arm": "paraphrase", "sae": a3, **m3},
        ],
        "sel_band": [SEL_LO, SEL_HI],
        "per_feature_pct": PER_FEATURE_PCT,
        "n_perm": N_PERM,
    }
    print("\n=== side by side (all three substrates) ===")
    print(json.dumps(record, indent=2))
    out = os.path.join(REPO, "experiments",
                       "2026-09-22-comparator-baselines.json")
    with open(out, "w") as f:
        json.dump(record, f, indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
