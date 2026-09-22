#!/usr/bin/env python3
"""Tests for program/view.py (issue #32, spec §5).

Two things must hold:

1. The five views compute against the fixture ledger — a fixture with an
   in-flight record, a completed rung, an instrument-failed record with
   findings, and a defect-found record with emergent links, so every view has
   something to render.
2. An empty or malformed ledger **fails loudly** rather than rendering an empty
   dashboard.

Run:  python3 -m pytest program/tests/ -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # import view
sys.path.insert(0, str(HERE.parent.parent))   # repo root for ledger

import view  # noqa: E402

FIXTURE_LEDGER = HERE / "fixture_ledger.jsonl"
FIXTURE_CACHE = HERE / "fixture_issue_state.json"
REGISTRY = {
    "gates": [
        {"id": "G-R1", "status": "PASS"},
        {"id": "G-M1", "status": "PASS"},
    ]
}


@pytest.fixture()
def wired(monkeypatch):
    """Point the view at the fixture ledger and cache."""
    monkeypatch.setattr(view, "LEDGER_PATH", FIXTURE_LEDGER)
    monkeypatch.setattr(view, "CACHE_PATH", FIXTURE_CACHE)
    return view.load_records(), view.load_cache()


def test_all_five_views_render_against_the_fixture(wired):
    records, cache = wired
    allviews = view.build_all(records, cache, REGISTRY)
    assert set(allviews) == {
        "program_state", "decision_queue", "health", "open_gaps"
    }

    # program_state: the four fixture records land under their kinds, with the
    # in-flight record kept distinct from the classified ones.
    by_kind = allviews["program_state"]["by_kind"]
    assert by_kind["decision"]["by_outcome"] == {"in-flight": 1}
    assert by_kind["experiment"]["by_outcome"]["phenomenon-present"] == 1
    assert by_kind["experiment"]["by_outcome"]["instrument-failed"] == 1
    assert by_kind["defect"]["by_outcome"] == {"defect-found": 1}
    # rung distribution covers only the record that carries a rung.
    assert allviews["program_state"]["rung_distribution"] == {"2": 1}

    # decision_queue: #31 is kind:decision in the fixture cache.
    assert [d["issue"] for d in allviews["decision_queue"]] == [31]

    # health: findings counted by rung from the fixture records.
    assert allviews["health"]["gates_defined"] == 2
    assert allviews["health"]["gates_wired"] == 2

    # open_gaps: the fixture cache's open kind:gap / kind:defect issues.
    gaps = {g["issue"] for g in allviews["open_gaps"]}
    assert gaps == {23, 36}


def test_traversal_carries_results_findings_decisions_and_edges(wired):
    records, cache = wired
    t = view.view_traversal(records, cache, 24)
    assert t["blocks"] == [{"issue": 15, "known": True, "state": "CLOSED", "outcome": None}]
    assert t["emergent"] == [{"issue": 23, "known": True, "state": "OPEN", "outcome": None}]
    assert t["results"] == ["docs/reference/TEST_VALIDATION_SPEC.md"]

    # A record with findings and DECs traverses them.
    t7 = view.view_traversal(records, cache, 7)
    assert t7["findings"] == [4]
    assert t7["decisions"] == ["DEC-020", "DEC-025"]


def test_empty_ledger_fails_loudly(monkeypatch, tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("# only a header comment\n", encoding="utf-8")
    monkeypatch.setattr(view, "LEDGER_PATH", empty)
    monkeypatch.setattr(view, "CACHE_PATH", FIXTURE_CACHE)
    with pytest.raises(view.ViewError, match="empty"):
        view.load_records()


def test_missing_ledger_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setattr(view, "LEDGER_PATH", tmp_path / "nope.jsonl")
    monkeypatch.setattr(view, "CACHE_PATH", FIXTURE_CACHE)
    with pytest.raises(view.ViewError, match="missing"):
        view.load_records()


def test_malformed_ledger_fails_loudly(monkeypatch, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "P-001", "ts": "x"}\n', encoding="utf-8")  # missing keys
    monkeypatch.setattr(view, "LEDGER_PATH", bad)
    monkeypatch.setattr(view, "CACHE_PATH", FIXTURE_CACHE)
    with pytest.raises(view.ViewError, match="malformed"):
        view.load_records()


def test_main_exits_nonzero_on_bad_ledger(monkeypatch, tmp_path, capsys):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json at all\n", encoding="utf-8")
    monkeypatch.setattr(view, "LEDGER_PATH", bad)
    monkeypatch.setattr(view, "CACHE_PATH", FIXTURE_CACHE)
    assert view.main([]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_json_output_is_parseable(wired, capsys):
    records, cache = wired
    # build_all is what --json serialises; assert it round-trips as JSON.
    blob = json.dumps(view.build_all(records, cache, REGISTRY))
    assert json.loads(blob)["health"]["gates_wired"] == 2
