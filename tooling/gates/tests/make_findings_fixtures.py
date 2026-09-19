"""Generate the four G-E failing fixtures from clean.jsonl.

Each derived fixture must violate EXACTLY the gate it is named for. Generating
them here (rather than hand-writing JSON) keeps them provably minimal
perturbations of the clean case, so a gate that fires can only be reacting to
the intended violation.

Run: python3 tooling/gates/tests/make_findings_fixtures.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "findings"
CLEAN = FIX / "clean.jsonl"


def load_records():
    return [json.loads(l) for l in CLEAN.read_text().splitlines()
            if l.strip() and not l.startswith("#")]


def dump(path: Path, records, header: str):
    lines = [f"# {header}", "#"]
    for r in records:
        lines.append(json.dumps(r))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path.name} ({len(records)} record(s))")


def main():
    recs = load_records()

    # G-E1: an undeclared key. Violates schema only — all required keys present,
    # all evidence non-empty, count unchanged, run_id/issue untouched.
    r = [dict(x) for x in recs]
    r[0]["surprise_field"] = "not in the schema"
    dump(FIX / "g_e1_unknown_key.jsonl", r,
         "G-E1 failing fixture: record 1 carries an undeclared key.")

    # G-E2: correction present but empty. Violates the evidence bar only.
    r = [dict(x) for x in recs]
    r[0]["correction"] = ""
    dump(FIX / "g_e2_empty_correction.jsonl", r,
         "G-E2 failing fixture: record 1 has an empty `correction`.")

    # G-E6: fewer records than the high-water mark (2). Violates append-only only.
    dump(FIX / "g_e6_shrunk.jsonl", [recs[0]],
         "G-E6 failing fixture: 1 record where the mark is 2 — looks like a deletion.")

    # G-E7: malformed run_id. Violates the format check only; the issue half
    # still resolves against the cache.
    r = [dict(x) for x in recs]
    r[0]["run_id"] = "not-a-run-id"
    dump(FIX / "g_e7_bad_runid.jsonl", r,
         "G-E7 failing fixture: record 1 has a malformed run_id.")

    # G-E7, second violation path: cites an issue that is not closed-done.
    r = [dict(x) for x in recs]
    r[0]["issue"] = 999
    dump(FIX / "g_e7_open_issue.jsonl", r,
         "G-E7 failing fixture: record 1 cites issue #999, which the cache "
         "reports as OPEN.")


if __name__ == "__main__":
    main()
