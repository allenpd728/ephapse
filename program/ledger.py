#!/usr/bin/env python3
"""The program ledger — `program/ledger.jsonl` (issue #31).

Append-only record of what each piece of work *produced*: the outcome
classification (spec §3.2), the rung (§3.3), and the traversal links between
results, findings, and decisions. It holds only what GitHub cannot express —
issue titles, statuses, assignees, and priority are deliberately absent
(PROGRAM_MANAGEMENT_SPEC.md §4).

The four append rules from spec §4 are enforced **on append**, not merely
documented: a violating record is rejected with a non-zero exit rather than
written. That is the `candidates.py` pattern from Maith, which this repo has
already used successfully.

Usage:
    python3 program/ledger.py append --issue 31 --run-id 20260922-0431-eph3 \\
        --kind protocol --outcome requirement-emerged \\
        --result program/README.md --note "..." \\
        [--rung N] [--decision DEC-0NN] [--finding N] [--blocks N] \\
        [--emergent N]
    python3 program/ledger.py list [--json]
    python3 program/ledger.py verify

Exit codes: 0 ok, 1 rejected or invalid record, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = REPO / "program" / "ledger.jsonl"

# The kind vocabulary has one machine-readable source (DEC-035); the ledger
# reads it rather than carrying its own copy, so a value the gate accepts cannot
# be one the ledger rejects.
KIND_VOCABULARY_FILE = REPO / "tooling" / "program" / "kind_vocabulary.txt"

# Spec §3.2. The human-readable definition is PROGRAM_MANAGEMENT_SPEC.md §3.2;
# this tuple is the machine-readable list the tool reads, and the two must agree.
OUTCOME_CLASSES = (
    "instrument-validated",
    "instrument-failed",
    "phenomenon-null",
    "phenomenon-present",
    "defect-found",
    "requirement-emerged",
)

RUNG_RANGE = range(0, 6)          # spec §3.3 / TEST_VALIDATION_SPEC.md §5
RUN_ID_RE = re.compile(r"^\d{8}-\d{4}-[A-Za-z0-9]{4}$")
ISSUE_REF_RE = re.compile(r"#(\d+)")

# The exact key set from spec §4. A record carrying any other key is rejected:
# the schema is frozen, and an extra key is the drift §4 warns about.
SCHEMA_KEYS = (
    "id", "ts", "issue", "run_id", "kind", "outcome", "rung",
    "results", "decisions", "findings", "blocks", "emergent", "note",
)
LIST_KEYS = ("results", "decisions", "findings", "blocks", "emergent")


class LedgerError(Exception):
    """A record that cannot be accepted (as opposed to a usage error)."""


def load_kind_vocabulary(path: Optional[Path] = None) -> tuple[str, ...]:
    """Read the kind values from the single source (DEC-035), prefix stripped."""
    if path is None:
        path = KIND_VOCABULARY_FILE
    if not path.exists():
        raise LedgerError(
            f"kind vocabulary missing: {path} — refusing to write a kind the "
            f"ledger cannot validate against (DEC-035)")
    values = tuple(
        line.strip()[len("kind:"):]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not values:
        raise LedgerError(f"kind vocabulary is empty: {path}")
    return values


def next_record_id(existing: "list[LedgerRecord]") -> str:
    """Sequential `P-001`, `P-002`, … — stable, orderable, unique."""
    n = 0
    for r in existing:
        if r.id.startswith("P-"):
            try:
                n = max(n, int(r.id[2:]))
            except ValueError:
                pass
    return f"P-{n + 1:03d}"


@dataclass
class LedgerRecord:
    """One ledger record. `outcome` is null while the work is in flight."""

    id: str
    ts: str
    issue: int
    run_id: str
    kind: str
    outcome: Optional[str] = None
    rung: Optional[int] = None
    results: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    emergent: list = field(default_factory=list)
    note: str = ""

    # ------------------------------------------------------------ validation
    def validate(self, kind_vocabulary: Optional[tuple[str, ...]] = None) -> None:
        """Enforce spec §4's four rules plus the schema. Raises LedgerError."""
        if not self.id:
            raise LedgerError("id is required")
        if not self.ts:
            raise LedgerError("ts is required")
        if not isinstance(self.issue, int) or self.issue <= 0:
            raise LedgerError(f"issue must be a positive integer, got {self.issue!r}")
        if not RUN_ID_RE.match(self.run_id or ""):
            raise LedgerError(
                f"run_id {self.run_id!r} does not match <YYYYMMDD-HHMM>-<4 alnum>")
        if self.kind not in (kind_vocabulary if kind_vocabulary is not None
                             else load_kind_vocabulary()):
            raise LedgerError(f"unknown kind {self.kind!r}")
        if self.outcome is not None and self.outcome not in OUTCOME_CLASSES:
            raise LedgerError(
                f"unknown outcome {self.outcome!r} — spec §3.2 values are "
                f"{', '.join(OUTCOME_CLASSES)}")
        if self.rung is not None and self.rung not in RUNG_RANGE:
            raise LedgerError(f"rung {self.rung!r} outside {list(RUNG_RANGE)}")
        for key in LIST_KEYS:
            if not isinstance(getattr(self, key), list):
                raise LedgerError(f"{key} must be a list")

        # Rule 1 — `outcome` requires `results` or `findings`. An outcome with
        # no artifact behind it is an assertion, not a record of one.
        if self.outcome is not None and not (self.results or self.findings):
            raise LedgerError(
                "rule 1: outcome set but neither `results` nor `findings` is "
                "populated — an outcome with no artifact behind it is an "
                "assertion (spec §4)")

        # Rule 2 — `rung` requires `outcome`. A rung on an in-flight record is
        # a claim about nothing.
        if self.rung is not None and self.outcome is None:
            raise LedgerError(
                "rule 2: rung set but outcome is null — a rung on an in-flight "
                "record is a claim about nothing (spec §4)")

        # Rule 3 — `emergent` entries must name real issues *filed by this
        # work*. "Filed by this work" is not offline-checkable, so the checkable
        # half is enforced: positive integers, no duplicates, and never the
        # record's own issue (a task cannot be emergent from itself).
        for e in self.emergent:
            if not isinstance(e, int) or e <= 0:
                raise LedgerError(f"rule 3: emergent entry {e!r} is not an issue number")
            if e == self.issue:
                raise LedgerError(
                    f"rule 3: emergent entry #{e} is this record's own issue — a "
                    f"record may not claim a requirement it did not surface "
                    f"(spec §4)")
        if len(set(self.emergent)) != len(self.emergent):
            raise LedgerError(f"rule 3: emergent has duplicates: {self.emergent}")

        # Rule 4 — a `defect-found` outcome must cite the issue it found the
        # defect in, in `note`, so the traversal is closed.
        if self.outcome == "defect-found" and not ISSUE_REF_RE.search(self.note):
            raise LedgerError(
                "rule 4: outcome is `defect-found` but `note` cites no issue "
                "(expected `#N`) — the traversal must be closed (spec §4)")

    # ------------------------------------------------------------ serialise
    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in SCHEMA_KEYS}

    @classmethod
    def from_json(cls, d: dict) -> "LedgerRecord":
        unknown = set(d) - set(SCHEMA_KEYS)
        if unknown:
            raise LedgerError(
                f"record carries unknown key(s) {sorted(unknown)} — the schema "
                f"is frozen to {list(SCHEMA_KEYS)} (spec §4)")
        missing = set(SCHEMA_KEYS) - set(d)
        if missing:
            raise LedgerError(f"record missing key(s) {sorted(missing)}")
        return cls(**{k: d[k] for k in SCHEMA_KEYS})


def read_ledger(path: Optional[Path] = None) -> "list[LedgerRecord]":
    """Read every record. `#` comment lines (the header) are ignored."""
    if path is None:
        path = DEFAULT_LEDGER
    if not path.exists():
        return []
    out: list[LedgerRecord] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(LedgerRecord.from_json(json.loads(line)))
        except (json.JSONDecodeError, TypeError) as e:
            raise LedgerError(f"{path}:{lineno}: unreadable record: {e}") from e
    return out


def append_record(record: LedgerRecord, path: Optional[Path] = None,
                  kind_vocabulary: Optional[tuple[str, ...]] = None) -> None:
    """Validate then append one record. Never rewrites; never writes on failure."""
    if path is None:
        path = DEFAULT_LEDGER
    record.validate(kind_vocabulary)
    existing = read_ledger(path)
    if any(r.id == record.id for r in existing):
        raise LedgerError(
            f"id {record.id!r} already present — the ledger is append-only and "
            f"ids must be unique")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_json(), sort_keys=True) + "\n")


# ------------------------------------------------------------------ CLI
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="The program ledger (issue #31).")
    p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append", help="validate and append one record")
    a.add_argument("--issue", type=int, required=True)
    a.add_argument("--run-id", required=True)
    a.add_argument("--kind", required=True)
    a.add_argument("--outcome", default=None)
    a.add_argument("--rung", type=int, default=None)
    a.add_argument("--result", action="append", default=[])
    a.add_argument("--decision", action="append", default=[])
    a.add_argument("--finding", action="append", type=int, default=[])
    a.add_argument("--blocks", action="append", type=int, default=[])
    a.add_argument("--emergent", action="append", type=int, default=[])
    a.add_argument("--note", default="")
    a.add_argument("--ts", default=None, help="UTC ISO8601; defaults to now")

    sub.add_parser("list", help="print every record")
    sub.add_parser("verify", help="re-validate every record")
    return p


def _cmd_append(args) -> int:
    path = args.ledger
    existing = read_ledger(path)
    record = LedgerRecord(
        id=next_record_id(existing),
        ts=args.ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        issue=args.issue,
        run_id=args.run_id,
        kind=args.kind,
        outcome=args.outcome,
        rung=args.rung,
        results=list(args.result),
        decisions=list(args.decision),
        findings=list(args.finding),
        blocks=list(args.blocks),
        emergent=list(args.emergent),
        note=args.note,
    )
    append_record(record, path)
    print(f"appended {record.id} (issue #{record.issue}, kind {record.kind}, "
          f"outcome {record.outcome})")
    return 0


def _cmd_list(args) -> int:
    records = read_ledger(args.ledger)
    print(json.dumps([r.to_json() for r in records], indent=2))
    return 0


def _cmd_verify(args) -> int:
    records = read_ledger(args.ledger)
    kinds = load_kind_vocabulary()
    ids = [r.id for r in records]
    if len(set(ids)) != len(ids):
        raise LedgerError(f"duplicate ids in the ledger: {ids}")
    for r in records:
        r.validate(kinds)
    print(f"verified {len(records)} record(s); ids unique")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {"append": _cmd_append, "list": _cmd_list, "verify": _cmd_verify}
    try:
        return handlers[args.cmd](args)
    except LedgerError as e:
        print(f"REJECTED: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
