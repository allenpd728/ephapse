# `program/` — the program ledger

`ledger.jsonl` is the append-only record of what each piece of work *produced*:
the outcome classification, the rung, and the traversal links between results,
findings, and decisions. It holds only what GitHub cannot express — issue
titles, statuses, assignees, and priority are deliberately **not** here, because
copying them creates the drift the coverage-map decision warns against.

The design rationale is `docs/reference/PROGRAM_MANAGEMENT_SPEC.md` §4; this
file explains the file and its rules to a newcomer.

## The schema

Every record carries exactly these keys, one JSON object per line:

| Key | Type | Meaning |
|---|---|---|
| `id` | string | Sequential `P-001`, `P-002`, … Stable, orderable, unique |
| `ts` | string | UTC ISO8601, when the record was written |
| `issue` | integer | The GitHub issue this records the outcome of |
| `run_id` | string | The agent run that produced it (`<YYYYMMDD-HHMM>-<4 alnum>`) |
| `kind` | string | §3.1 value, without the `kind:` prefix |
| `outcome` | string \| null | §3.2 value; `null` while in flight |
| `rung` | integer \| null | §3.3 value if the outcome is a claim; else `null` |
| `results` | list[string] | Paths to result artifacts this outcome rests on, repo-relative |
| `decisions` | list[string] | `DEC-0NN` ids this outcome produced or rests on |
| `findings` | list[integer] | 1-based line numbers in `findings.jsonl`, if any |
| `blocks` | list[integer] | Issue numbers this outcome unblocks or redirects |
| `emergent` | list[integer] | Issue numbers this work **created** (the §6 path) |
| `note` | string | Short prose. Not a place for conclusions |

Lines beginning with `#` are the header comment and are ignored by the parser.

The `kind` vocabulary has one machine-readable source, `tooling/program/kind_vocabulary.txt`
(DEC-035); the ledger reads it rather than carrying its own copy, so a value the
gate accepts cannot be one the ledger rejects.

## The four append rules

Enforced **on append**, not merely documented: `program/ledger.py` rejects a
violating record with a non-zero exit rather than writing it, so the violation
cannot enter the ledger. This is the `candidates.py` pattern from Maith.

1. **`outcome` requires `results` or `findings`.** An outcome with no artifact
   behind it is an assertion. (Mirrors `findings.jsonl`'s evidence bar.)
2. **`rung` requires `outcome`.** A rung on an in-flight record is a claim about
   nothing.
3. **`emergent` entries must name real issues** that were filed *by* this work.
   A record may not claim a requirement it did not surface. "Filed by this work"
   is not offline-checkable, so the checkable half is enforced: entries are
   positive integers, unique, and never the record's own issue.
4. **A `defect-found` outcome must cite the issue it found the defect in**, in
   `note` (`#N`), so the traversal is closed. #24's record cites #11.

## `outcome` is not `verdict` (spec §10 Q3)

These two fields overlap on `null`/`flagged` but are **not the same axis**:

- `outcome` (here) is the **interpretation** of a result.
- `verdict` (in `findings.jsonl`) is its **label**.

A `flagged` verdict can be either `instrument-validated` (the #5 positive
control) or `phenomenon-present` (a real finding). Stating this once is what
stops the two being read as the same field — the distinction between
`instrument-failed` and `phenomenon-null` is the one §3.2 says will keep costing
a rediscovery otherwise.

## Usage

```bash
# append one record (rules enforced; exit 1 if rejected)
python3 program/ledger.py append --issue 31 --run-id 20260922-0431-eph3 \
    --kind protocol --outcome requirement-emerged \
    --result program/README.md --note "..." [--rung N] [--decision DEC-0NN] \
    [--finding N] [--blocks N] [--emergent N]

python3 program/ledger.py list          # every record, as JSON
python3 program/ledger.py verify        # re-validate every record
```

Exit codes: `0` ok, `1` rejected or invalid record, `2` usage error.

## Derived views

Every view is **computed**, never stored (`program/view.py`, issue #32): a stored
view would be a second source of truth that can silently disagree with the
ledger. If a view is wrong, the fix is to fix the record, not the view.
