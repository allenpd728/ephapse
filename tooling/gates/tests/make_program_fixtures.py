"""Generate the G-M1/G-M2 failing fixtures from program_clean.json (issue #30).

Each failing fixture is a minimal perturbation of the clean one, so a gate that
fires can only be reacting to the intended violation. Generated rather than
hand-written so the perturbation is provably the only difference.

Run: python3 tooling/gates/tests/make_program_fixtures.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"
CLEAN = FIX / "program_clean.json"


def load():
    raw = json.loads(CLEAN.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}, raw.get("_comment", "")


def dump(path: Path, issues: dict, header: str):
    out = {"_comment": header, "_generated": "fixture"}
    out.update(issues)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.name}")


def main():
    clean, _ = load()

    # --- G-M1 violation A: two status labels on one OPEN issue.
    # This is the exact state produced while filing #29-#34.
    r1a = json.loads(json.dumps(clean))
    r1a["29"]["labels"] = ["status:available", "status:blocked-needs-input",
                           "kind:repair"]
    dump(FIX / "program_r1_two_status.json", r1a,
         "G-M1 failing fixture: #29 carries TWO status labels — the illegal "
         "state MULTI_AGENT_WORKFLOW.md section 1a says the sweep must repair.")

    # --- G-M1 violation B: no kind label at all.
    r1b = json.loads(json.dumps(clean))
    r1b["29"]["labels"] = ["status:available"]
    dump(FIX / "program_r1_no_kind.json", r1b,
         "G-M1 failing fixture: #29 carries no kind: label.")

    # --- G-M2 violation: available while a blocker is open.
    # #29 is available; add an OPEN blocker so the label state is wrong in a
    # way cardinality cannot see.
    r2 = json.loads(json.dumps(clean))
    r2["31"] = {"state": "OPEN", "done": False,
                "labels": ["status:claimed", "kind:protocol"],
                "blocked_by": [30]}
    r2["29"]["blocked_by"] = [31]          # #31 is OPEN and not closed
    dump(FIX / "program_r2_available_blocked.json", r2,
         "G-M2 failing fixture: #29 is status:available while its blocker #31 "
         "is OPEN. Exactly one status label, so G-M1 is silent — this is the "
         "hole G-M2 exists to close.")

    # --- G-M1 violation C: an unrecognised label value.
    # A typo divides the queue silently; cardinality still reads 1.
    r1c = json.loads(json.dumps(clean))
    r1c["29"]["labels"] = ["status:availble", "kind:repair"]
    dump(FIX / "program_r1_typo_status.json", r1c,
         "G-M1 failing fixture: #29 carries a misspelled status label. "
         "Cardinality reads 1, so only a vocabulary check catches it.")


if __name__ == "__main__":
    main()
