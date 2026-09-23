"""Tests for tooling/measure_footprint.py (issue: #39 OOM root cause).

Only the pure functions are exercised -- `_activation_bytes`, `param_bytes`,
`verdict`, `suggestions` and `_check_id` take plain dicts and return numbers or
strings, so the tests are deterministic and need no network or model weights.
The `plan`/`load` commands fetch real configs; their numbers are validated
against measurement in the issue, not here.

The gemma-2-2b numbers below are the real architecture (config.json, 2026-09-23)
and the expected values are the arithmetic the tool is asserting.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLING = Path(__file__).resolve().parent.parent
if str(TOOLING) not in sys.path:
    sys.path.insert(0, str(TOOLING))

import measure_footprint as mf

GEMMA = {
    "model_type": "gemma2",
    "n_params": 2_614_341_888,
    "vocab_size": 256000,
    "hidden_size": 2304,
    "n_layers": 26,
    "n_heads": 8,
    "n_kv_heads": 4,
    # gemma-2-2b config.json reports tie_word_embeddings: false, and the
    # safetensors total (2.614 B) already includes the separate output head.
    # Setting this True here would apply a correction the model does not need.
    "tie_word_embeddings": False,
    "gated": "manual",
}

PYTHIA = {
    "model_type": "gpt_neox",
    "n_params": 95_592_496,
    "vocab_size": 50304,
    "hidden_size": 512,
    "n_layers": 6,
    "n_heads": 8,
    "n_kv_heads": 8,
    "tie_word_embeddings": False,
    "gated": False,
}


class TestActivationBytes:
    def test_logits_dominate_at_gemma_batch64(self):
        """logits = batch x seq x vocab x 4 B is the largest activation term."""
        a = mf._activation_bytes(GEMMA, "fp32", 64, 32)
        assert a["logits"] == 64 * 32 * 256000 * 4
        assert a["logits"] > a["kv_cache"] > a["hidden"]

    def test_total_is_the_sum(self):
        a = mf._activation_bytes(GEMMA, "fp32", 64, 32)
        assert a["total"] == a["logits"] + a["kv_cache"] + a["hidden"]

    def test_batch_zero_is_free(self):
        """plan --batch 0 measures the load alone, with no activations."""
        a = mf._activation_bytes(GEMMA, "fp32", 0, 32)
        assert a["total"] == 0

    def test_logits_scale_linearly_with_batch(self):
        one = mf._activation_bytes(GEMMA, "fp32", 1, 32)["logits"]
        eight = mf._activation_bytes(GEMMA, "fp32", 8, 32)["logits"]
        assert eight == 8 * one

    def test_kv_cache_uses_kv_heads_not_full_heads(self):
        """gemma-2-2b has 4 kv heads against 8 heads; the cache must use 4."""
        a = mf._activation_bytes(GEMMA, "fp32", 1, 32)
        expected = 2 * 26 * 1 * 32 * 4 * (2304 // 8) * 4
        assert a["kv_cache"] == expected


class TestParamBytes:
    def test_tied_embeddings_are_double_counted_by_the_config(self):
        """When a model ties its head, `num_parameters` counts the embedding twice."""
        tied = dict(GEMMA, tie_word_embeddings=True)
        raw = tied["n_params"] * 4
        corrected = mf.param_bytes(tied, tied["n_params"])
        assert corrected < raw
        assert raw - corrected == tied["vocab_size"] * tied["hidden_size"] * 4

    def test_untied_model_is_unchanged(self):
        assert mf.param_bytes(PYTHIA, PYTHIA["n_params"]) == PYTHIA["n_params"] * 4

    def test_gemma_is_not_corrected(self):
        """gemma-2-2b is reported untied; the correction must not fire."""
        assert mf.param_bytes(GEMMA, GEMMA["n_params"]) == GEMMA["n_params"] * 4


class TestVerdict:
    def _plan(self, gb):
        return {"weights_plus_batch_gb": gb, "mem_available_gb": 13.5}

    def test_fits_with_headroom(self):
        code, _ = mf.verdict(self._plan(5.0), None)
        assert code == "FITS"

    def test_tight_between_75_and_100_percent(self):
        code, why = mf.verdict(self._plan(12.0), None)
        assert code == "TIGHT"
        assert "fragmentation" in why

    def test_exceeds_reports_the_shortfall(self):
        code, why = mf.verdict(self._plan(16.0), None)
        assert code == "EXCEEDS"
        assert "2.50 GB" in why

    def test_budget_override_beats_meminfo(self):
        """--budget-gb lets a plan run against a target other than this host."""
        code, _ = mf.verdict(self._plan(5.0), budget_gb=1.0)
        assert code == "EXCEEDS"


class TestGemmaRegression:
    """The configuration that OOM'd seven runs on #39 must not read as FITS."""

    def test_fp32_batch64_exceeds(self):
        act = mf._activation_bytes(GEMMA, "fp32", 64, 32)
        n_eff = mf.param_bytes(GEMMA, GEMMA["n_params"]) // 4
        need = (n_eff * 4 + act["total"] + mf.RUNTIME_OVERHEAD_GB * 1e9) / 1e9
        assert need == pytest.approx(14.06, abs=0.05)
        code, _ = mf.verdict({"weights_plus_batch_gb": need,
                              "mem_available_gb": 13.5}, None)
        assert code == "EXCEEDS"

    def test_bf16_batch1_fits(self):
        s = mf.suggestions(GEMMA, 13.5, 32)
        assert s and "bf16" in s[0]

    def test_suggestion_is_within_the_budget(self):
        s = mf.suggestions(GEMMA, 13.5, 32)
        assert s, "a fatal config must suggest a fitting one"
        assert mf._plan_from_cfg(GEMMA, "bf16", 1, 32)["weights_plus_batch_gb"] <= 13.5 * 0.75


class TestModelId:
    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError):
            mf._check_id("../../etc/passwd")

    def test_rejects_url_injection(self):
        with pytest.raises(ValueError):
            mf._check_id("http://evil.example/x")

    def test_accepts_org_name(self):
        assert mf._check_id("google/gemma-2-2b") == "google/gemma-2-2b"
