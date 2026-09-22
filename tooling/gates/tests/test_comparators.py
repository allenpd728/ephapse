#!/usr/bin/env python3
"""pytest suite for the supervised comparator baselines (issue #37, DEC-034).

Run:  python3 -m pytest tooling/gates/tests/ -k comparator

The two mandatory fixtures of the harness contract are here, in both directions:

  * `test_all_three_agree_on_a_separable_concept` — the case where the SAE, the
    difference-in-means baseline and the linear probe all find the construct.
  * `test_probe_detects_a_bridge_the_sae_misses` — the constructible positive
    control for "the probe can see something the SAE cannot", which is the whole
    reason the comparators exist (a null that survives a non-sparse method is a
    much stronger null).

Both fixtures are built from declared arithmetic, not from a model: the point is
that the *baseline* is correct, which is checkable without torch. The AUROC
tests pin the tie handling so a constant score cannot masquerade as signal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

GATES = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GATES))

import comparators as C  # noqa: E402


def _separable(n: int = 200, d: int = 16, shift: float = 3.0, seed: int = 0):
    """Two classes separated along three shared dimensions plus noise."""
    rng = np.random.default_rng(seed)
    dirs = np.zeros(d)
    dirs[:3] = 1.0
    x = rng.normal(size=(n, d))
    y = (rng.random(n) < 0.5).astype(int)
    x += (y[:, None] * 2 - 1) * shift * dirs[None, :]
    return x, y


def test_auroc_perfect_and_inverted():
    labels = np.array([0, 0, 1, 1])
    assert C.auroc(np.array([0.1, 0.2, 0.8, 0.9]), labels) == 1.0
    assert C.auroc(np.array([0.9, 0.8, 0.2, 0.1]), labels) == 0.0


def test_auroc_constant_scores_give_exactly_half():
    """A constant score carries no ranking information; ties must give 0.5."""
    labels = np.array([0, 1, 0, 1, 0, 1])
    assert C.auroc(np.full(6, 0.7), labels) == pytest.approx(0.5)


def test_auroc_requires_both_classes():
    with pytest.raises(ValueError):
        C.auroc(np.array([0.1, 0.2]), np.array([1, 1]))


def test_difference_in_means_shape_check():
    with pytest.raises(ValueError):
        C.difference_in_means(np.zeros((4, 3)), np.zeros((4, 5)))


def test_probe_fits_separable_data():
    x, y = _separable()
    w, b = C.fit_linear_probe(x, y)
    mu, sd = x.mean(axis=0), x.std(axis=0)
    assert C.auroc(C.probe_scores(x, w, b, (mu, sd)), y) > 0.9


def test_all_three_agree_on_a_separable_concept():
    """Fixture 1 — all three substrates detect the construct."""
    x, y = _separable()
    # The SAE's own reading: a designated feature that fires exactly on class 1.
    bin_a = np.zeros_like(x, dtype=bool)
    bin_a[y == 1, 0] = True
    bins = (bin_a, bin_a.copy())

    r = C.compare_arms(x, x, labels_a=y, bins=bins, sel=np.array([0]))
    # The SAE statistic is a co-firing rate; on a class-exclusive feature it is
    # the base rate, and its evidence is that it clears the permutation null.
    assert r["sae"]["max"] == pytest.approx(0.5, abs=0.05)
    assert r["sae"]["n_selected"] == 1
    assert r["difference_in_means"]["auroc"] > 0.9
    assert r["linear_probe"]["auroc"] > 0.9
    # The SAE reading stays the primary one; the comparators travel with it.
    assert r["substrates"] == ["sae", "difference_in_means", "linear_probe"]


def test_probe_detects_a_bridge_the_sae_misses():
    """Fixture 2 — the positive control for "the probe sees what the SAE cannot".

    The concept is spread across three hook dimensions, so the supervised
    directions recover it. The SAE feature is binarised against a threshold the
    concept does not clear in arm B, so its bridge is exactly zero. That gap is
    the measurement #37 exists to make.
    """
    x, y = _separable()
    # SAE feature 0 fires in arm A but never crosses threshold in arm B.
    bin_a = np.zeros_like(x, dtype=bool)
    bin_a[y == 1, 0] = True
    bin_b = np.zeros_like(x, dtype=bool)

    r = C.compare_arms(x, x, labels_a=y, bins=(bin_a, bin_b), sel=np.array([0]))
    assert r["sae"]["max"] == 0.0
    assert r["difference_in_means"]["auroc"] > 0.9
    assert r["linear_probe"]["auroc"] > 0.9


def test_probe_labels_are_never_inferred():
    """Without labels the direction is undefined — the module must refuse."""
    x, _ = _separable(n=20)
    with pytest.raises(ValueError):
        C.compare_arms(x, x)


def test_sae_reading_is_none_without_binarisation():
    """The SAE statistic is defined on its own thresholding; no silent substitute."""
    x, y = _separable(n=40)
    r = C.compare_arms(x, x, labels_a=y)
    assert r["sae"] is None


def test_compare_arms_rejects_mismatched_arms():
    x, y = _separable(n=40)
    with pytest.raises(ValueError):
        C.compare_arms(x, x[:20], labels_a=y)
