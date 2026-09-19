"""Generate the G-R1/G-R2/G-R5 experiment fixtures (issue #11).

Each of the four fixture directories is a minimal perturbation of
`experiments_clean/`, so a gate that fires can only be reacting to the intended
violation. Generated rather than hand-written so the perturbations are provably
minimal.

Run: python3 tooling/gates/tests/make_experiment_fixtures.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"

CLEAN_HEADER = '''**Model:** pythia-70m-deduped, fp32, CPU.
**Inputs:** fixture prompt sets, defined below.
**Question:** does the fixture gate behave as specified?
**Null:** fixture null model (per-pair Poisson independence).
**Correction:** fixture correction (BH-FDR at q=0.05).
**Issue:** #11 (fixture only — not a real run).
'''

INFRA_HEADER = '''**Model:** pythia-70m-deduped, fp32, CPU.
**Question:** fixture infrastructure measurement.
**Issue:** #11 (fixture only — not a real run).

Infrastructure/baseline file: no hypothesis under test.
'''

CLEAN_BODY = '''

MODEL = "pythia-70m-deduped"


def main():
    print("fixture:", MODEL)


if __name__ == "__main__":
    main()
'''


def write(dirname: str, files: dict[str, str]):
    d = FIX / dirname
    d.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (d / name).write_text(body, encoding="utf-8")
    print(f"wrote {dirname}/ ({len(files)} file(s))")


# The run log must mention every file in the directory, or G-R5 fires. It is
# built from the file list so the clean case stays clean by construction.
def run_log(filenames: list[str]) -> str:
    rows = "\n".join(
        f"| 2026-09-19 | `{n}` | #11 | fixture row for {n} |" for n in filenames)
    return (
        "# experiments\n\n"
        "## Run log\n\n"
        "| Date | File | Issue | What it measured |\n"
        "|---|---|---|---|\n"
        f"{rows}\n"
    )


def main():
    # ---------------------------------------------------------------- clean
    clean_files = {
        "2026-09-19-hypothesis-fixture.py":
            f'"""Clean hypothesis-test fixture.\n\n{CLEAN_HEADER}"""' + CLEAN_BODY,
        # An infrastructure file with the documented reduced header AND a
        # matching filename pattern. Exercised by the clean case so the
        # exemption path is proven to pass, not just to fail correctly.
        "2026-09-19-latency-fixture.py":
            f'"""Clean infrastructure fixture.\n\n{INFRA_HEADER}"""\n\n'
            'MODEL = "pythia-70m-deduped"\n',
    }
    clean_files["README.md"] = run_log(list(clean_files))
    write("experiments_clean", clean_files)

    # ------------------------------------------------------- G-R1: missing
    # One hypothesis-test file missing `Correction` — a near miss, not an
    # empty file.
    r1_files = dict(clean_files)
    r1_files["2026-09-19-missing-correction.py"] = (
        '"""G-R1 failing fixture: full header missing the `Correction` field.\n\n'
        "**Model:** pythia-70m-deduped, fp32, CPU.\n"
        "**Inputs:** fixture prompt sets.\n"
        "**Question:** does G-R1 fire on a near-miss header?\n"
        "**Null:** fixture null model.\n"
        "**Issue:** #11 (fixture only).\n"
        '"""\n\nMODEL = "pythia-70m-deduped"\n')
    r1_files["README.md"] = run_log([n for n in r1_files if n != "README.md"])
    write("experiments_r1_missing_field", r1_files)

    # ------------------------------------------ G-R1: invalid exemption claim
    # A hypothesis-test file that *claims* the infrastructure exemption while
    # carrying only the three-field header. Must FAIL: the exemption is for
    # environment measurement, and this file has a hypothesis.
    r1b_files = dict(clean_files)
    r1b_files["2026-09-19-claims-exemption.py"] = (
        '"""G-R1 failing fixture: claims the infrastructure exemption without\n'
        "qualifying — it tests a hypothesis but carries only three fields.\n\n"
        "**Model:** pythia-70m-deduped, fp32, CPU.\n"
        "**Question:** does the detector recover the injected correlation?\n"
        "**Issue:** #11 (fixture only).\n"
        '"""\n\nMODEL = "pythia-70m-deduped"\n')
    r1b_files["README.md"] = run_log([n for n in r1b_files if n != "README.md"])
    write("experiments_r1_invalid_exemption", r1b_files)

    # -------------------------------------------------- G-R2: superseded model
    r2_files = dict(clean_files)
    r2_files["2026-09-19-superseded-model.py"] = (
        '"""G-R2 failing fixture: loads a superseded model id.\n\n'
        "**Model:** pythia-160m, fp32, CPU.\n"
        "**Inputs:** fixture prompt sets.\n"
        "**Question:** does G-R2 fire on a non-target model?\n"
        "**Null:** fixture null model.\n"
        "**Correction:** fixture correction.\n"
        "**Issue:** #11 (fixture only).\n"
        '"""\n\nMODEL = "pythia-160m"\n')
    r2_files["README.md"] = run_log([n for n in r2_files if n != "README.md"])
    write("experiments_r2_superseded_model", r2_files)

    # --------------------------------------------------- G-R2: no model at all
    # Fails closed: a file whose model cannot be determined must be flagged.
    r2b_files = dict(clean_files)
    r2b_files["2026-09-19-no-model.py"] = (
        '"""G-R2 failing fixture: no model id anywhere.\n\n'
        "**Model:** (unstated)\n"
        "**Inputs:** fixture prompt sets.\n"
        "**Question:** does G-R2 fail closed?\n"
        "**Null:** fixture null model.\n"
        "**Correction:** fixture correction.\n"
        "**Issue:** #11 (fixture only).\n"
        '"""\n\n# deliberately no MODEL assignment\n')
    r2b_files["README.md"] = run_log([n for n in r2b_files if n != "README.md"])
    write("experiments_r2_no_model", r2b_files)

    # -------------------------------------------------- G-R5: missing log row
    r5_files = dict(clean_files)
    r5_files["2026-09-19-unlogged.py"] = (
        '"""G-R5 failing fixture: absent from the run log.\n\n'
        f"{CLEAN_HEADER}" '"""\n\nMODEL = "pythia-70m-deduped"\n')
    # The run log deliberately omits the new file.
    r5_files["README.md"] = run_log(
        [n for n in r5_files if n not in ("README.md", "2026-09-19-unlogged.py")])
    write("experiments_r5_missing_log_row", r5_files)


if __name__ == "__main__":
    main()
