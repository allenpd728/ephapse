#!/usr/bin/env python3
"""G-R1 — experiment header completeness (worked example for the harness).

The gate: every file in `experiments/` matching `*.py` must carry the mandatory
header fields, or declare itself an infrastructure file and carry the reduced
set. The rule is normative in `experiments/README.md`:

  full header (hypothesis-testing files), six fields:
      Model, Inputs, Question, Null, Correction, Issue
  reduced header (infrastructure/baseline files), three fields:
      Model, Question, Issue

A file with none of the fields, or with a partial full header and no
infrastructure declaration, violates G-R1.

WHY THIS IS THE WORKED EXAMPLE. It is the smallest gate that still exercises
every part of the harness contract: a pure-text check, a clean fixture, and a
failing fixture that is a *near miss* (five of six fields present) rather than an
obviously-broken file. A gate that only fires on an empty file would satisfy the
letter of the fixture rule and none of its purpose.

Registered via `register()` so `run_all.py` discovers it mechanically.
"""
from __future__ import annotations

import re
from pathlib import Path

from run_all import Gate, register           # noqa: E402

FULL_FIELDS = ("Model", "Inputs", "Question", "Null", "Correction", "Issue")
REDUCED_FIELDS = ("Model", "Question", "Issue")

# A field counts as present when its label appears at the start of a line in the
# module docstring, optionally followed by ':' or '—'. Matching is case-
# insensitive on the label only.
FIELD_RE = re.compile(r"^\s*\**\s*(Model|Inputs|Question|Null|Correction|Issue)\b",
                      re.MULTILINE | re.IGNORECASE)
# The infrastructure declaration must be a *line-leading* declaration, not any
# mention. An earlier version matched the bare phrase anywhere in the docstring,
# which meant a file whose prose said "does NOT declare itself an infrastructure
# file" was silently exempted from the full header — the gate stopped firing on
# its own failing fixture. Found by the harness reporting BROKEN, which is
# exactly what that rule is for (issue #9).
INFRA_RE = re.compile(
    r"^\s*\**\s*infrastructure\s*(?:/|\band\b)?\s*(?:baseline\s*)?file\b",
    re.MULTILINE | re.IGNORECASE)


def check_experiment_header(path: Path) -> list[str]:
    """Return findings for one experiment file (empty = pass)."""
    findings: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")

    # Only the leading docstring region is searched, so a field name mentioned
    # deep in the body cannot satisfy the header.
    head = text[:4000]
    present = {m.group(1).capitalize() for m in FIELD_RE.finditer(head)}

    is_infra = bool(INFRA_RE.search(head))
    required = REDUCED_FIELDS if is_infra else FULL_FIELDS

    missing = [f for f in required if f not in present]
    if missing:
        kind = "infrastructure" if is_infra else "full"
        findings.append(
            f"{path.name}: {kind} header missing {len(missing)} field(s): "
            f"{', '.join(missing)} — see experiments/README.md")

    # A file declaring itself infrastructure while carrying the full set is not a
    # violation, but declaring infrastructure and silently omitting the reduced
    # set is — covered by `missing` above.
    return findings


register(Gate(
    id="G-R1",
    name="experiment header completeness",
    tier=0,
    check=check_experiment_header,
    clean_fixture="experiment_headers/clean_experiment.py",
    failing_fixture="experiment_headers/failing_experiment.py",
    traces_to="experiments/README.md; spec §3",
    description="Every experiment file carries its mandatory header fields.",
))
