#!/usr/bin/env python3
"""Supervised comparator baselines (issue #37, DEC-034).

Every detector measurement is reported alongside two supervised baselines —
**difference-in-means** and a **logistic-regression linear probe** — computed on
the *same activations the SAE reads*, at the same hook. This module is the
tier-0, numpy-only implementation of those comparators plus the plumbing that
puts all three readings into one result record.

Why this exists. `PRIOR_ART.md` § 4 carries the feature-absorption caveat: a
null may mean "the SAE cannot represent this structure" rather than "the
structure is absent." As written that caveat is a disclaimer. A comparator
converts it into a measurement: if a supervised probe detects a bridge the SAE
misses, the *instrument* — not the model scale — is the bottleneck.

What a comparator is not. A probe yields a *direction*, not an enumerable
feature with a decoder vector. The SAE's justification is the feature list; a
comparator is a **sensitivity check on the detector**, never a substrate
replacement. The writeups must say so (`PRIOR_ART.md` § 4, DEC-034).

Tier boundary. This module is numpy-only and deterministic: no torch, no model,
no network. It runs in CI at tier 0 (`run_all.py`) and in the gate test suite.
The activation *production* is tier 1 and lives in the experiment scripts.

Geometry (`PRIOR_ART.md` § 9). Both comparators operate in the raw hook basis;
where a cosine threshold does real work the caller must state which vectors and
which geometry, because cosine in the raw basis is not the geometry in which
concepts behave linearly (Park, Choe & Veitch, ICML 2024).

The comparator API is deliberately per-arm, not per-record: `compare_arms`
returns one reading per arm (matched, shuffled-null, paraphrase) so the null and
the surface-form control travel with the primary number, as G-C5 requires for
cross-run comparability.
"""
from __future__ import annotations

import numpy as np

# The three substrates, in the order the finding records them. The SAE is first
# because it remains the recorded *primary* reading — comparators are reported
# alongside, never in place of it (DEC-034 method constraint).
SUBSTRATES = ("sae", "difference_in_means", "linear_probe")

# Defaults for the probe. Full-batch gradient descent with L2; small enough to
# fit a 512-dim hook in milliseconds, deterministic given a seed. Feature
# standardisation uses the training arm's statistics only — no leakage from the
# evaluation arm.
PROBE_L2 = 1e-3
PROBE_ITERS = 400
PROBE_LR = 0.5


def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based AUROC of `scores` against binary `labels`.

    Ties contribute 0.5 each (the Mann-Whitney U form), so a constant score
    gives exactly 0.5 rather than an accident of sort order. This is the
    AxBench detection metric the comparators are reported under.
    """
    scores = np.asarray(scores, dtype=np.float64).ravel()
    labels = np.asarray(labels).ravel()
    if scores.shape != labels.shape:
        raise ValueError("scores and labels must have the same shape")
    pos, neg = labels == 1, labels == 0
    n_pos, n_neg = int(pos.sum()), int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        raise ValueError("AUROC needs both classes present")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(scores.size, dtype=np.float64)
    sorted_scores = scores[order]
    i = 0
    while i < scores.size:
        j = i
        while j + 1 < scores.size and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        # average rank for the tie group (1-based, as in the U statistic)
        avg = (i + j) / 2.0 + 1.0
        ranks[order[i:j + 1]] = avg
        i = j + 1
    u = ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0
    return float(u / (n_pos * n_neg))


def difference_in_means(positive: np.ndarray, negative: np.ndarray) -> np.ndarray:
    """The AxBench difference-in-means direction: mean(pos) - mean(neg).

    Returned unnormalised; scoring is by projection, so the magnitude is
    irrelevant and normalising would only invite a threshold reading that the
    AUROC does not need.
    """
    positive = np.asarray(positive, dtype=np.float64)
    negative = np.asarray(negative, dtype=np.float64)
    if positive.ndim != 2 or negative.ndim != 2:
        raise ValueError("activation blocks must be 2-D (n_samples, d_hook)")
    if positive.shape[1] != negative.shape[1]:
        raise ValueError("positive and negative must share the hook width")
    return positive.mean(axis=0) - negative.mean(axis=0)


def _standardise(train: np.ndarray, other: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Feature-standardise `other` with `train`'s statistics (no leakage)."""
    mu = train.mean(axis=0)
    sd = train.std(axis=0)
    sd[sd == 0] = 1.0
    return (train - mu) / sd, (other - mu) / sd


def fit_linear_probe(
    activations: np.ndarray,
    labels: np.ndarray,
    l2: float = PROBE_L2,
    iters: int = PROBE_ITERS,
    lr: float = PROBE_LR,
) -> tuple[np.ndarray, float]:
    """Logistic regression by full-batch gradient descent. Returns (w, b)."""
    x = np.asarray(activations, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64).ravel()
    if x.ndim != 2:
        raise ValueError("activations must be 2-D (n_samples, d_hook)")
    if x.shape[0] != y.size:
        raise ValueError("one label per activation row")
    x, _ = _standardise(x, x)
    n, d = x.shape
    w = np.zeros(d, dtype=np.float64)
    b = 0.0
    for _ in range(iters):
        z = x @ w + b
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))
        g = p - y
        w -= lr * (x.T @ g / n + l2 * w)
        b -= lr * float(g.mean())
    return w, b


def probe_scores(activations: np.ndarray, w: np.ndarray, b: float,
                 train_stats: tuple[np.ndarray, np.ndarray] | None = None) -> np.ndarray:
    """Project activations onto a fitted probe. `train_stats` = (mu, sd)."""
    x = np.asarray(activations, dtype=np.float64)
    if train_stats is not None:
        mu, sd = train_stats
        x = (x - mu) / np.where(sd == 0, 1.0, sd)
    return x @ w + b


def sae_bridge(bin_a: np.ndarray, bin_b: np.ndarray, perm: np.ndarray,
               sel: np.ndarray) -> np.ndarray:
    """Per-feature SAE bridge: P(feature fires in A and in B) under `perm`.

    Identical to the statistic the paraphrase experiment records, so the SAE
    reading is directly comparable across runs (G-C5).
    """
    aligned = bin_b[perm]
    return (bin_a[:, sel] & aligned[:, sel]).mean(axis=0)


def compare_arms(
    acts_a: np.ndarray,
    acts_b: np.ndarray,
    labels_a: np.ndarray | None = None,
    perm: np.ndarray | None = None,
    sel: np.ndarray | None = None,
    bins: tuple[np.ndarray, np.ndarray] | None = None,
) -> dict:
    """Run all three substrates on one pair of activation arms.

    `acts_a`/`acts_b` are the hook activations for the two arms (n, d_hook). The
    supervised comparators learn on arm A and are scored on arm B, which is what
    makes the reading a *transfer* check rather than a within-arm fit.

    `labels_a` is the arm-A class label for the concept direction. When omitted,
    arm A is split at its median activation *of the concept feature* only when
    `sel` names one; otherwise the caller must supply labels — guessing a label
    from the data would make the baseline uninterpretable.

    `bins` carries the SAE binarisation (bin_a, bin_b); when omitted the SAE
    reading is `None`, because the SAE's statistic is defined on its own
    per-feature thresholding and the comparator must not silently substitute it.
    """
    acts_a = np.asarray(acts_a, dtype=np.float64)
    acts_b = np.asarray(acts_b, dtype=np.float64)
    if acts_a.shape != acts_b.shape:
        raise ValueError("the two arms must have the same shape (paired inputs)")
    n = acts_a.shape[0]
    if perm is None:
        perm = np.arange(n)
    out: dict = {"n": n, "substrates": list(SUBSTRATES)}

    if bins is None:
        out["sae"] = None
    else:
        bin_a, bin_b = bins
        if sel is None:
            sel = np.arange(bin_a.shape[1])
        out["sae"] = {
            "statistic": "bridge(per-feature co-firing)",
            "max": float(sae_bridge(bin_a, bin_b, perm, sel).max()),
            "n_selected": int(len(sel)),
        }

    if labels_a is None:
        raise ValueError(
            "labels_a is required: the supervised direction cannot be inferred "
            "from activations without inventing a label"
        )
    labels_a = np.asarray(labels_a).ravel()
    pos, neg = acts_a[labels_a == 1], acts_a[labels_a == 0]
    if pos.size == 0 or neg.size == 0:
        raise ValueError("both classes must be present in arm A")

    dim = difference_in_means(pos, neg)
    out["difference_in_means"] = {
        "statistic": "auroc(projection on mean(pos)-mean(neg))",
        "auroc": auroc(acts_b @ dim, labels_a),
        "norm": float(np.linalg.norm(dim)),
    }

    w, b = fit_linear_probe(acts_a, labels_a)
    mu, sd = acts_a.mean(axis=0), acts_a.std(axis=0)
    out["linear_probe"] = {
        "statistic": "auroc(logistic-regression logit)",
        "auroc": auroc(probe_scores(acts_b, w, b, (mu, sd)), labels_a),
    }
    return out
