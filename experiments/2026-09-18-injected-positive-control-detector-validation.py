"""Issue #5 — Validate the co-activation detector with an injected positive control.

**Model:** pythia-70m-deduped (TransformerLens), fp32, CPU.
**Inputs:** background corpus = NeelNanda/pile-10k indices 0..1999 (N=2000),
  unmodified text truncated to 400 chars, tokenized to CTX=64. Signal texts =
  pile-10k indices 8000 and 8001, held out from the background slice.
**Question:** does the NPMI + semantic-distance detector, BH-FDR corrected,
  recover a known injected cross-group co-activation — and over what injection
  range does recovery hold?
**Null:** binary feature activations independent. Per-pair p-value is the upper
  tail of Poisson(lambda_ij = s_i*s_j/N) at the observed co-occurrence count.
**Correction:** Benjamini-Hochberg FDR at q=0.05 over the full pair family.
**Issue:** #5 (run 20260918-2332-e7c4). Pre-registered in DEC-016/017.

WHY THIS IS NOT #3. Issue #5 validates the *detector's sensitivity* to a
correlation known by construction to be present. Whether a recovered pair is
cross-*domain* in any interesting sense is issue #3's question, not this one.

HOW THE PLANTED SIGNAL IS BUILT (this took three attempts; see DEC-017).

The naive construction — take the top-activating features on the signal text —
does not produce a detectable signal, for two independent reasons that both
produce a *false* negative:

  1. **Catch-all features.** Top-activation at pythia-70m selects features that
     fire on nearly every input (measured background support ~2000/2000).
     Injecting them into more rows cannot raise a marginal that is already 1.0,
     so NPMI stays structurally near zero no matter the injection rate.
  2. **Non-activating group members.** Restricting to a low-support "band" and
     still ranking by activation selects features the signal text does not
     actually fire, so the planted row activates nothing.

The construction below satisfies the arithmetic NPMI requires. If the groups
fire *only* on injected rows, then pA = pB = pXY = rate, and

    NPMI = log(rate / rate^2) / (-log rate) = log(1/rate) / log(1/rate) = 1.0

which clears the 0.8 threshold at every rate. So groups are chosen as:

  * **active on the planted row** — guarantees the injection is real, and
  * **ranked by ASCENDING background support** — guarantees the marginal is
    movable and the correlation is genuinely surprising.

A control that cannot fire is not a control; the runs that could not fire are
reported in DEC-017 rather than discarded.

PRE-REGISTERED PARAMETERS (fixed before the run; see DEC-016):
  N              = 2000 background samples
  CTX            = 64 tokens
  GROUP_SIZE     = 20 per group
  INJECT_RATES   = [0.0, 0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.40]
  FDR_Q          = 0.05
  NPMI_THRESHOLD = 0.8
  SEM_SIM_MAX    = 0.2   (cosine on raw decoder directions -- PRIOR_ART section 9
                          notes this geometry is an assumption, stated not hidden)
  CLUSTER_COS    = 0.6   (decoder cosine above this unions two features)
  DETECTION      = BH-significant AND NPMI > 0.8 AND semantic cosine < 0.2
  RECOVERY       = |flagged pairs in A x B| / (|A| * |B|), plus binary ">=1"
  NAIVE BASELINE = top-M pairs by raw co-occurrence, M matched to the detector's
                   flag count (falls back to M=1 at zero), since ranking by
                   raw count is the obvious alternative to the NPMI screen

Run:  python3 experiments/2026-09-18-injected-positive-control-detector-validation.py
"""
from __future__ import annotations

import json
import time

import numpy as np
import torch
from datasets import load_dataset

from scipy.stats import poisson
from sae_lens import SAE
from transformer_lens import HookedTransformer

# ---------------------------------------------------------------- parameters
MODEL = "pythia-70m-deduped"
HOOK = "blocks.3.hook_resid_post"
SAE_RELEASE = "pythia-70m-deduped-res-sm"
RUN_ID = "20260918-2332-e7c4"
ISSUE = 5

N = 2000
CTX = 64
GROUP_SIZE = 20
INJECT_RATES = [0.0, 0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.40]
FDR_Q = 0.05
NPMI_THRESHOLD = 0.8
SEM_SIM_MAX = 0.2
CLUSTER_COS = 0.6
SIGNAL_IDX = (8000, 8001)
SEPARATORS = (" ", ". ", " and ", " -- ")
BATCH = 64
OUT = "experiments/2026-09-18-injected-positive-control-results.json"


# ------------------------------------------------------------------ encoding
def encode_texts(model, sae, texts, label):
    """Per-sample max SAE feature activation over the token axis. Returns (n, d_sae)."""
    toks = model.to_tokens(texts, truncate=True)[:, :CTX]
    acc = []
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(texts), BATCH):
            _, cache = model.run_with_cache(
                toks[i:i + BATCH], names_filter=lambda n: n == HOOK)
            acc.append(sae.encode(cache[HOOK]).amax(dim=1))
    out = torch.cat(acc, 0).numpy()
    print(f"  encoded {label}: {out.shape} in {time.time()-t0:.1f}s", flush=True)
    return out


def bh_fdr(pvals, q):
    """Benjamini-Hochberg. Returns (largest significant p, count significant)."""
    m = pvals.size
    order = np.argsort(pvals, kind="stable")
    ranked = pvals[order]
    thresh = q * (np.arange(1, m + 1) / m)
    ok = ranked <= thresh
    if not ok.any():
        return -1.0, 0
    k = int(np.max(np.nonzero(ok)[0]))
    return float(ranked[k]), k + 1


def cluster_features(cos_block, threshold):
    """Union-find over features whose decoder cosine exceeds `threshold`."""
    n = cos_block.shape[0]
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    iu, ju = np.nonzero(np.triu(cos_block >= threshold, k=1))
    for a, b in zip(iu.tolist(), ju.tolist()):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(n)])


# ---------------------------------------------------------------------- main
def main():
    t_start = time.time()
    results = {"run_id": RUN_ID, "issue": ISSUE, "model": MODEL, "hook": HOOK,
               "sae": SAE_RELEASE, "N": N, "ctx": CTX,
               "group_size": GROUP_SIZE, "fdr_q": FDR_Q,
               "npmi_threshold": NPMI_THRESHOLD, "sem_sim_max": SEM_SIM_MAX,
               "cluster_cos": CLUSTER_COS, "signal_idx": list(SIGNAL_IDX),
               "inject_rates": INJECT_RATES}

    print(f"=== issue #{ISSUE} detector validation | {MODEL} | {HOOK} ===")
    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")
    print(f"  d_sae={sae.cfg.d_sae}  d_model={model.cfg.d_model}")

    # ---- corpus --------------------------------------------------------
    ds = load_dataset("NeelNanda/pile-10k", split="train")
    bg_texts = [ds[i]["text"][:400] for i in range(N)]
    t1, t2 = (ds[i]["text"][:200] for i in SIGNAL_IDX)
    print(f"  background N={N}  signal texts from idx {SIGNAL_IDX}")

    # ---- encode: background, single-domain signal rows, planted rows ----
    # Three distinct kinds of row. The single-domain rows are what let the two
    # groups have separately estimable marginals; the planted rows are what
    # carry the correlation. Using concatenations for all rows (as the first
    # two attempts did) makes the groups inseparable -- DEC-017.
    bg = encode_texts(model, sae, bg_texts, "background")
    sig_a = encode_texts(model, sae, [t1], "signal A")
    sig_b = encode_texts(model, sae, [t2], "signal B")
    planted = encode_texts(model, sae, [t1 + sep + t2 for sep in SEPARATORS],
                           "planted (A+B)")

    # ---- feature universe ----------------------------------------------
    # A feature is in play if it fires anywhere -- on the background OR on a
    # planted row. The planted rows must be included, otherwise a feature that
    # fires only on injected rows is filtered out before it can be a group
    # member. (That omission is what made attempt 3 select 0-activating groups.)
    fires_bg = (bg > 0).any(0)
    fires_planted = (planted > 0).any(0)
    keep = np.nonzero(fires_bg | fires_planted)[0]
    support = (bg > 0).sum(0)                 # background support, for ranking
    print(f"  feature universe: {keep.size} (fires in background "
          f"{int(fires_bg.sum())}, on planted rows {int(fires_planted.sum())})")
    results["n_features_tested"] = int(keep.size)
    results["n_features_firing_bg"] = int(fires_bg.sum())
    results["n_features_firing_planted"] = int(fires_planted.sum())

    # ---- pick groups: active on the planted row, lowest background support --
    # All group members come from ONE fixed planted row, and that same row is
    # the one injected. This matters: with several rotating variants, different
    # injected rows fire different subsets, so a given A-B pair co-occurs on
    # fewer rows than were injected and NPMI is diluted below its analytic
    # value. A positive control plants one fixed correlation, so one row.
    Bg = (bg > 0)[:, keep]
    inj_bin = (planted > 0)[:, keep]
    s = Bg.sum(0).astype(np.float64)
    planted_row = inj_bin[0]                   # the single planted row

    cand = np.nonzero(planted_row)[0]
    # Ascending background support: the least-used features give the most
    # movable marginal and the most surprising correlation. Ties broken by
    # feature index for determinism.
    order = sorted(cand.tolist(), key=lambda i: (s[i], i))
    n_low = int((s[order] <= 50).sum())
    print(f"  planted-active features: {len(order)}; "
          f"with background support <= 50: {n_low}")
    results["n_planted_active"] = int(len(order))
    results["n_planted_active_low_support"] = n_low
    if len(order) < 2 * GROUP_SIZE:
        print(f"  WARNING: only {len(order)} planted-active features; "
              f"cannot form two disjoint groups of {GROUP_SIZE} (recorded)")
    A = np.array(order[:GROUP_SIZE])
    B = np.array(order[GROUP_SIZE:2 * GROUP_SIZE])
    print(f"  group A: {A.size} features (bg support {int(s[A].min())}"
          f"-{int(s[A].max())})")
    print(f"  group B: {B.size} features (bg support {int(s[B].min())}"
          f"-{int(s[B].max())})")
    results["group_a_size"] = int(A.size)
    results["group_b_size"] = int(B.size)
    results["group_a_features"] = [int(keep[i]) for i in A]
    results["group_b_features"] = [int(keep[i]) for i in B]
    results["group_a_bg_support"] = [int(s[i]) for i in A]
    results["group_b_bg_support"] = [int(s[i]) for i in B]

    # ---- constructibility check (the one whose absence hid two broken runs) --
    results["planted_activates_A"] = int(inj_bin[0][A].sum())
    results["planted_activates_B"] = int(inj_bin[0][B].sum())
    print(f"  PLANTED row activates {results['planted_activates_A']}/{A.size} "
          f"of A and {results['planted_activates_B']}/{B.size} of B")
    if results["planted_activates_A"] < A.size or \
            results["planted_activates_B"] < B.size:
        print("  WARNING: planted row does not fully activate both groups -- "
              "control not constructible as specified (recorded)")
    else:
        print("  constructibility OK: planted row fires both groups")

    # ---- decoder-vector geometry (once) -------------------------------
    Wd = sae.W_dec.detach().cpu().numpy()[keep]
    Wd = Wd / np.linalg.norm(Wd, axis=1, keepdims=True)
    print("  computing decoder-vector cosine matrix ...", flush=True)
    t0 = time.time()
    cos = Wd @ Wd.T
    np.fill_diagonal(cos, 1.0)
    print(f"    done {time.time()-t0:.1f}s")
    clusters = cluster_features(cos, CLUSTER_COS)
    n_clusters = int(np.unique(clusters).size)
    print(f"  clusters at cosine >= {CLUSTER_COS}: {n_clusters} "
          f"(from {keep.size} features)")
    results["n_clusters"] = n_clusters

    # ---- recovery-curve sweep -----------------------------------------
    k = keep.size
    tri = np.triu_indices(k, k=1)
    ai, bi = tri
    pairs_A = np.isin(ai, A) | np.isin(bi, A)
    pairs_B = np.isin(ai, B) | np.isin(bi, B)
    cross = pairs_A & pairs_B
    n_cross = int(cross.sum())
    results["n_cross_pairs"] = n_cross
    print(f"  cross pairs under test: {n_cross} "
          f"(family size {tri[0].size})")

    curve = []
    for rate in INJECT_RATES:
        n_inj = int(round(rate * N))
        print(f"\n--- injection rate {rate} ({n_inj}/{N} samples) ---", flush=True)

        M = Bg.copy()
        if n_inj:
            # Plant ONE fixed row, repeated -- so every injected row carries the
            # same A-B correlation and co-occurrence equals the injection count.
            # Rotating variants dilute NPMI below its analytic value (DEC-017).
            M[:n_inj] = inj_bin[0]

        # Observed marginals AFTER injection -- recorded, because these are what
        # determine whether NPMI can clear the threshold at all (DEC-017).
        si_new = M.sum(0).astype(np.float64)

        t0 = time.time()
        Bf = M.astype(np.float64)
        cooc = Bf.T @ Bf
        cooc = cooc - np.diag(cooc.diagonal())        # exclude self-pairs
        lam = np.outer(si_new, si_new) / N
        # Correct upper tail P(X >= k) for X ~ Poisson(lambda) is the survival
        # function at k-1. The earlier gammaincc(k, lam) form is the regularized
        # *lower* incomplete gamma with the arguments swapped -- it returns 1.0
        # for every pair, so no pair could ever be significant. That single bug
        # produced a clean-looking non-detection across four runs (DEC-017).
        k_obs = np.maximum(cooc, 1.0)
        p = np.where(cooc >= 1, poisson.sf(k_obs - 1.0, lam), 1.0)
        np.fill_diagonal(p, 1.0)
        p = np.clip(p, 1e-300, 1.0)
        pv = p[tri]
        crit, n_sig = bh_fdr(pv, FDR_Q)

        co = cooc[tri]
        with np.errstate(divide="ignore", invalid="ignore"):
            num = np.log((co / N) / ((si_new[ai] / N) * (si_new[bi] / N)))
            den = -np.log(co / N)
            npmi = np.where((co > 0) & (den > 0), num / den, -1.0)
        passes_npmi = npmi > NPMI_THRESHOLD
        passes_sem = cos[tri] < SEM_SIM_MAX
        sig = pv <= crit if crit > 0 else np.zeros_like(pv, dtype=bool)
        flagged = sig & passes_npmi & passes_sem

        fam = {"fdr": int(sig.sum()), "npmi": int(passes_npmi.sum()),
               "sem": int(passes_sem.sum()), "all3": int(flagged.sum())}
        hit = int((flagged & cross).sum())
        rec = hit / n_cross if n_cross else 0.0

        # Cross-pair breakdown: which condition rejects the planted pairs?
        # Without this, a bug in any single mask is indistinguishable from a
        # genuine detector miss (DEC-017).
        dbg = {
            "cross_fdr": int((sig & cross).sum()),
            "cross_npmi": int((passes_npmi & cross).sum()),
            "cross_sem": int((passes_sem & cross).sum()),
            "cross_fdr_npmi": int((sig & passes_npmi & cross).sum()),
            "cross_fdr_sem": int((sig & passes_sem & cross).sum()),
            "cross_npmi_sem": int((passes_npmi & passes_sem & cross).sum()),
            "cross_all3": int((sig & passes_npmi & passes_sem & cross).sum()),
            "cross_max_co": int(co[cross].max()) if n_cross else 0,
            "cross_min_p": float(pv[cross].min()) if n_cross else None,
        }
        print(f"  cross breakdown: fdr={dbg['cross_fdr']} npmi={dbg['cross_npmi']} "
              f"sem={dbg['cross_sem']} fdr&npmi={dbg['cross_fdr_npmi']} "
              f"all3={dbg['cross_all3']}")

        cross_npmi = npmi[cross]
        budget = max(int(flagged.sum()), 1)
        top = np.argpartition(-co, min(budget, co.size - 1))[:budget]
        naive_hit = int((np.isin(top, np.nonzero(cross)[0])).sum())

        row = {
            "rate": rate, "n_injected": n_inj,
            "group_a_marginal_min": float(si_new[A].min() / N),
            "group_a_marginal_max": float(si_new[A].max() / N),
            "group_b_marginal_min": float(si_new[B].min() / N),
            "group_b_marginal_max": float(si_new[B].max() / N),
            "cross_npmi_median": float(np.median(cross_npmi)),
            "cross_npmi_max": float(cross_npmi.max()),
            "bh_critical_p": crit, "n_significant": n_sig,
            "funnel": fam, "cross_debug": dbg,
            "recovered_hits": hit, "recovery_rate": rec,
            "recovered_binary": bool(hit > 0),
            "n_cross_pairs_passing_sem": int((cos[tri][cross] < SEM_SIM_MAX).sum()),
            "naive_budget": budget, "naive_hits": naive_hit,
            "naive_recovery": naive_hit / n_cross if n_cross else 0.0,
            "flagged_in_same_cluster": int(
                (flagged & (clusters[ai] == clusters[bi])).sum()),
            "seconds": round(time.time() - t0, 1),
        }
        curve.append(row)
        print(f"  group marginals: A {row['group_a_marginal_min']:.3f}-"
              f"{row['group_a_marginal_max']:.3f}  "
              f"B {row['group_b_marginal_min']:.3f}-"
              f"{row['group_b_marginal_max']:.3f}")
        print(f"  cross-pair NPMI: median {row['cross_npmi_median']:.3f} "
              f"max {row['cross_npmi_max']:.3f} (threshold {NPMI_THRESHOLD})")
        print(f"  family: fdr={fam['fdr']} npmi={fam['npmi']} sem={fam['sem']} "
              f"all3={fam['all3']}")
        print(f"  RECOVERED {hit}/{n_cross} = {rec:.3f}   "
              f"naive(budget {budget}): {naive_hit}   [{row['seconds']}s]")

    results["curve"] = curve
    results["total_seconds"] = round(time.time() - t_start, 1)

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n=== wrote {OUT} in {results['total_seconds']}s ===")

    print("\n=== recovery curve (detector) vs naive ===")
    print(f"{'rate':>7} {'n_inj':>6} {'npmi_med':>9} {'det_hits':>9} "
          f"{'det_rec':>8} {'naive_rec':>10} {'flagged':>8}")
    for r in curve:
        print(f"{r['rate']:>7} {r['n_injected']:>6} "
              f"{r['cross_npmi_median']:>9.3f} {r['recovered_hits']:>9} "
              f"{r['recovery_rate']:>8.3f} {r['naive_recovery']:>10.3f} "
              f"{r['funnel']['all3']:>8}")


if __name__ == "__main__":
    main()
