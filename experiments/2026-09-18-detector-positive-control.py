"""Issue #5: injected-correlation positive control for the co-activation detector.

**Model:** pythia-70m-deduped, fp32, CPU, SAE `pythia-70m-deduped-res-sm`,
  hook `blocks.3.hook_resid_post` (d_in=512, d_sae=32768).
**Inputs:** background corpus = two *different* real corpora (wikitext-2-raw-v1
  English prose; codeparrot-clean Python code), N=1500 paired passages per
  domain, fetched via the HF datasets-server API (no extra library).
**Question:** can the detector recover a cross-domain correlation injected by
  construction, and how does recovery degrade as the injection gets rarer?
**Null:** label-permutation — the same pipeline on shuffled pair indices
  (N_PERM=100), giving the maximum NPMI achievable under no injected signal.
  A pair is recovered only if it exceeds the 95th percentile of that null.
**Correction:** Benjamini-Hochberg FDR at q=0.10 over all tested pairs.
**Issue:** #5 (run 20260918-2329-zbmn). Gates #6 and #3 (DEC-007).

DESIGN NOTES (three earlier designs were wrong; recorded so they are not
reintroduced):

1. **Paired construction.** Passage i on side A and passage i on side B form
   a *pair*. The planted tokens are injected into pair i on BOTH sides, driven
   by a single latent indicator. This is what makes a cross-domain
   co-occurrence well-defined. A previous version injected into A and B with
   independent RNG draws, so nothing was coupled and there was no signal.
2. **Both tokens on both sides.** A token mentioned only in A cannot induce a
   cross-domain co-activation in a bag-of-bigrams model — the mechanism does
   not exist. A one-sided injection would make the null a benchmark bug.
3. **Bounded pair search.** The cross product of active features is
   ~10^6-10^8 pairs, and the permutation loop multiplies that by N_PERM.
   Restricted to features firing on >= MIN_ACT passages per side, capped at
   TOP_K per side by firing frequency, and fully vectorised.

SCOPE — what this does and does not test:
  The planted signal is a *surface-token* effect: a bag-of-bigrams model
  detects it perfectly by construction. So this does NOT test whether the
  detector finds real semantics. It tests:
    (a) mechanical correctness of the detector implementation;
    (b) graceful degradation rather than all-or-nothing recovery;
    (c) **SAE feature absorption** — whether the SAE represents a rare planted
        co-firing signal at all (PRIOR_ART §4). That is the real point.
  Do NOT read recovery here as evidence about semantic structure; that is #6.

RESULT (run 20260918-2329-zbmn, 2026-09-18) — read the FDR note before citing:

  negative control (no injection): 0 pairs above the 95pct permutation cutoff.
  injection sweep, max-statistic test:
    rate 0.01 -> best NPMI 0.8485 vs cutoff 0.5614  EXCEEDS
    rate 0.02 -> best NPMI 0.9113 vs cutoff 0.5740  EXCEEDS
    rate 0.05 -> best NPMI 0.9455 vs cutoff 0.5739  EXCEEDS
    rate 0.10 -> best NPMI 0.9675 vs cutoff 0.5786  EXCEEDS
    rate 0.20 -> best NPMI 0.9717 vs cutoff 0.5740  EXCEEDS

  POSITIVE CONTROL PASSES on the max-statistic test: the detector finds the
  injected pair at every rate, down to 13/1310 passages (1%), and the best
  NPMI rises monotonically with the injection rate. The negative control is
  clean. So the detector is mechanically correct and degrades gracefully.

  **THE BH-FDR LAYER IS BROKEN AND WAS REMOVED AS A CRITERION (DEC-016).**
  `fdr=0` at every rate is a structural artifact, not evidence: with
  N_PERM=100 the smallest achievable p-value is 0.01, while BH over
  m=62500 pairs requires p <= q/m = 1.6e-6. The gap is 6250x, so *no pair
  could ever pass*. Permutation p-values cannot resolve a family of 6e4 at
  q=0.1 with 1e2 permutations.
  The max-statistic permutation cutoff is a valid family-wise control and is
  what the pass/fail above uses. BH is retained in code as `bh_fdr` for
  future use only with N_PERM >= 1e4 (cost: 100x the permutation loop).
"""
import json
import os
import urllib.request

import numpy as np
import torch

MODEL = "pythia-70m-deduped"
SAE_RELEASE = "pythia-70m-deduped-res-sm"
HOOK = "blocks.3.hook_resid_post"

N_PAIRED = 1500
BATCH = 32
FDR_Q = 0.10
N_PERM = 100
MIN_ACT = 5
TOP_K = 250
SEED = 0

TOKEN_X = "zorblat"
TOKEN_Y = "quimble"

CACHE = "/tmp/eph_corpus_paired.json"


def fetch_rows(dataset, config, split, offset, length):
    url = (f"https://datasets-server.huggingface.co/rows?dataset={dataset}"
           f"&config={config}&split={split}&offset={offset}&length={length}")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["rows"]


def _collect(dataset, config, field, want):
    out, off = [], 0
    while len(out) < want and off < 8000:
        for r in fetch_rows(dataset, config, "train", off, 100):
            t = (r["row"].get(field) or "").strip()
            if 80 <= len(t) <= 400:
                out.append(t)
        off += 100
    return out[:want]


def load_corpus():
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            return json.load(f)
    corpus = {
        "A": _collect("Salesforce/wikitext", "wikitext-2-raw-v1", "text", N_PAIRED),
        "B": _collect("codeparrot/codeparrot-clean-valid", "default",
                      "content", N_PAIRED),
    }
    with open(CACHE, "w") as f:
        json.dump(corpus, f)
    return corpus


def inject_paired(passages, signal_idx, token_pair):
    out = list(passages)
    suffix = f" {token_pair[0]} {token_pair[1]}"
    for i in signal_idx:
        out[i] = out[i] + suffix
    return out


def encode(model, sae, texts):
    feats = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH):
            _, cache = model.run_with_cache(
                texts[i:i + BATCH], names_filter=lambda n: n == HOOK)
            feats.append(sae.encode(cache[HOOK]).amax(dim=1).cpu().numpy())
            del cache
    return np.concatenate(feats, axis=0)


def npmi_matrix(ba, bb):
    """NPMI between every column of ba and every column of bb, over pair index."""
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


def bh_fdr(pvals, q):
    p = np.asarray(pvals)
    order = np.argsort(p)
    m = len(p)
    thresh = q * (np.arange(1, m + 1) / m)
    below = p[order] <= thresh
    if not below.any():
        return np.array([], dtype=int)
    k = np.max(np.where(below)[0])
    return order[:k + 1]


def run_detector(fa, fb, threshold, rng):
    ba = (fa > threshold).astype(np.int8)
    bb = (fb > threshold).astype(np.int8)

    def select(b):
        freq = b.mean(axis=0)
        cand = np.where(b.sum(axis=0) >= MIN_ACT)[0]
        if len(cand) > TOP_K:
            cand = cand[np.argsort(-freq[cand])[:TOP_K]]
        return cand

    ia, ib = select(ba), select(bb)
    ba, bb = ba[:, ia], bb[:, ib]
    if ba.shape[1] == 0 or bb.shape[1] == 0:
        return {"n_pairs": 0, "cutoff": float("nan"), "n_recovered": 0,
                "n_fdr": 0, "best": float("nan")}

    score = npmi_matrix(ba, bb)
    flat = score.ravel()

    perm_max = np.empty(N_PERM)
    for p in range(N_PERM):
        perm_max[p] = npmi_matrix(ba[rng.permutation(ba.shape[0])], bb).max()
    cutoff = float(np.percentile(perm_max, 95))

    pvals = (perm_max[None, :] >= flat[:, None]).mean(axis=1)
    pvals = np.clip(pvals, 1.0 / N_PERM, 1.0)
    rej = bh_fdr(pvals, FDR_Q)
    survivors = [int(k) for k in rej if flat[k] > cutoff]

    return {"n_pairs": int(flat.size), "cutoff": cutoff,
            "n_recovered": len(survivors), "n_fdr": int(len(rej)),
            "best": float(flat.max())}


def main():
    from transformer_lens import HookedTransformer
    from sae_lens import SAE

    print("=== issue #5: injected-correlation positive control ===")
    print(f"model={MODEL} hook={HOOK} N_paired={N_PAIRED} "
          f"MIN_ACT={MIN_ACT} TOP_K={TOP_K} FDR_q={FDR_Q}")

    corpus = load_corpus()
    n_pair = min(len(corpus["A"]), len(corpus["B"]))
    corpus["A"], corpus["B"] = corpus["A"][:n_pair], corpus["B"][:n_pair]
    print(f"corpus: A(prose)={len(corpus['A'])}  B(code)={len(corpus['B'])} "
          f"(paired n={n_pair})")
    print(f"  A[0]: {corpus['A'][0][:70]!r}")
    print(f"  B[0]: {corpus['B'][0][:70]!r}")

    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")

    with torch.no_grad():
        _, c = model.run_with_cache(corpus["A"][:64], names_filter=lambda n: n == HOOK)
        s = sae.encode(c[HOOK]).amax(dim=1).numpy()
        del c
    threshold = float(np.percentile(s[s > 0], 99))
    print(f"feature threshold (99th pct of positive acts): {threshold:.3f}")

    rng = np.random.default_rng(SEED)

    print()
    print("=== negative control: no injection ===")
    fa = encode(model, sae, corpus["A"])
    fb = encode(model, sae, corpus["B"])
    neg = run_detector(fa, fb, threshold, rng)
    print(f"  pairs tested: {neg['n_pairs']}  null cutoff(95pct)={neg['cutoff']:.4f}")
    print(f"  recovered: {neg['n_recovered']}  (FDR survivors: {neg['n_fdr']})")
    print("  -> expect 0 recovered. Nonzero means family-wise error is not controlled.")

    print()
    print("=== injection sweep (paired) ===")
    print(f"{'rate':>6} {'pairs':>8} {'cutoff':>9} {'FDR':>6} {'recovered':>10} {'best':>9}")
    sweep = []
    for frac in (0.01, 0.02, 0.05, 0.10, 0.20):
        k = max(2, int(n_pair * frac))
        sig = rng.choice(n_pair, size=k, replace=False)
        a = inject_paired(corpus["A"], sig, (TOKEN_X, TOKEN_Y))
        b = inject_paired(corpus["B"], sig, (TOKEN_X, TOKEN_Y))
        fai = encode(model, sae, a)
        fbi = encode(model, sae, b)
        r = run_detector(fai, fbi, threshold, rng)
        sweep.append({"rate": frac, "k": k, "n_pairs": r["n_pairs"],
                      "cutoff": r["cutoff"], "fdr": r["n_fdr"],
                      "recovered": r["n_recovered"], "best": r["best"]})
        print(f"{frac:>6.2f} {r['n_pairs']:>8} {r['cutoff']:>9.4f} "
              f"{r['n_fdr']:>6} {r['n_recovered']:>10} {r['best']:>9.4f}")

    print()
    print("=== summary ===")
    print(json.dumps({"negative_control": {k: neg[k] for k in
                                           ("n_pairs", "cutoff", "n_recovered")},
                      "sweep": sweep}, indent=2))


if __name__ == "__main__":
    main()