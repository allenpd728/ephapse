#!/usr/bin/env python3
"""Tests for the program ledger (issue #31).

Two kinds of assertion, both required: the four spec §4 rules **fire** when
violated (a rule that cannot fail is not a check), and the happy path is silent.
The rule-4 case is the one worth having — a `defect-found` record with no `#N`
in its note is exactly the traversal §4 says must be closed.

Run: python3 -m pytest program/test_ledger.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import ledger as L  # noqa: E402

RUN = "20260922-0431-eph3"
TS = "2026-09-22T00:00:00Z"


def rec(**kw) -> L.LedgerRecord:
    base = dict(id="P-001", ts=TS, issue=31, run_id=RUN, kind="protocol")
    base.update(kw)
    return L.LedgerRecord(**base)


def test_committed_ledger_is_valid():
    """The ledger shipped in the repo parses and every record validates."""
    records = L.read_ledger(REPO / "program" / "ledger.jsonl")
    assert records, "the ledger must carry at least the header + seed record"
    kinds = L.load_kind_vocabulary()
    for r in records:
        r.validate(kinds)


def test_header_lines_are_ignored():
    records = L.read_ledger(REPO / "program" / "ledger.jsonl")
    assert all(not r.note.startswith("#") for r in records)


# --------------------------------------------------------------- rule 1
def test_rule1_fires_on_outcome_without_artifact():
    with pytest.raises(L.LedgerError, match="rule 1"):
        rec(outcome="phenomenon-null").validate()


def test_rule1_silent_when_results_present():
    rec(outcome="phenomenon-null", results=["experiments/x.md"]).validate()


def test_rule1_silent_when_findings_present():
    rec(outcome="phenomenon-null", findings=[3]).validate()


# --------------------------------------------------------------- rule 2
def test_rule2_fires_on_rung_without_outcome():
    with pytest.raises(L.LedgerError, match="rule 2"):
        rec(rung=2).validate()


def test_rule2_silent_with_outcome():
    rec(outcome="phenomenon-present", rung=2, results=["x"]).validate()


# --------------------------------------------------------------- rule 3
def test_rule3_fires_when_emergent_names_own_issue():
    with pytest.raises(L.LedgerError, match="rule 3"):
        rec(emergent=[31]).validate()


def test_rule3_fires_on_duplicate_emergent():
    with pytest.raises(L.LedgerError, match="rule 3"):
        rec(emergent=[40, 40]).validate()


def test_rule3_silent_on_a_real_emergent_issue():
    rec(emergent=[40]).validate()


# --------------------------------------------------------------- rule 4
def test_rule4_fires_when_defect_found_cites_no_issue():
    with pytest.raises(L.LedgerError, match="rule 4"):
        rec(outcome="defect-found", results=["x"], note="a flaw").validate()


def test_rule4_silent_when_note_cites_the_issue():
    rec(outcome="defect-found", results=["x"],
        note="found the defect in #24").validate()


# --------------------------------------------------------- schema guards
def test_unknown_key_is_rejected_on_read():
    bad = {k: None for k in L.SCHEMA_KEYS}
    bad["surprise"] = 1
    with pytest.raises(L.LedgerError, match="unknown key"):
        L.LedgerRecord.from_json(bad)


def test_missing_key_is_rejected_on_read():
    bad = {k: None for k in L.SCHEMA_KEYS if k != "note"}
    with pytest.raises(L.LedgerError, match="missing key"):
        L.LedgerRecord.from_json(bad)


def test_bad_kind_is_rejected():
    with pytest.raises(L.LedgerError, match="unknown kind"):
        rec(kind="nonsense").validate()


def test_bad_run_id_is_rejected():
    with pytest.raises(L.LedgerError, match="run_id"):
        rec(run_id="not-a-run-id").validate()


def test_bad_outcome_is_rejected():
    with pytest.raises(L.LedgerError, match="unknown outcome"):
        rec(outcome="maybe", results=["x"]).validate()


# ------------------------------------------------- append / id behaviour
def test_append_writes_nothing_on_rejection(tmp_path):
    p = tmp_path / "l.jsonl"
    with pytest.raises(L.LedgerError):
        L.append_record(rec(outcome="phenomenon-null"), p)
    assert not p.exists(), "a rejected record must not create or touch the file"


def test_append_is_append_only_and_ids_are_sequential(tmp_path):
    p = tmp_path / "l.jsonl"
    L.append_record(rec(id="P-001", outcome="phenomenon-null", results=["x"]), p)
    L.append_record(rec(id="P-002", outcome="phenomenon-null", results=["y"]), p)
    assert len(L.read_ledger(p)) == 2
    assert L.next_record_id(L.read_ledger(p)) == "P-003"


def test_duplicate_id_is_rejected(tmp_path):
    p = tmp_path / "l.jsonl"
    L.append_record(rec(id="P-001", outcome="phenomenon-null", results=["x"]), p)
    with pytest.raises(L.LedgerError, match="already present"):
        L.append_record(rec(id="P-001", outcome="phenomenon-null", results=["x"]), p)


def test_to_json_carries_exactly_the_schema_keys():
    assert set(rec().to_json()) == set(L.SCHEMA_KEYS)
