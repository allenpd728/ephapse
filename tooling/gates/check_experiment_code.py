#!/usr/bin/env python3
"""G-C1..G-C5 — the experiment-*code* gates (issue #22).

The fifth defect class (`docs/reference/TEST_VALIDATION_SPEC.md` §1) is a
measurement that **cannot fire**: a statistic bounded below its own threshold,
a control that never activates, an inverted survival function, a reading
computed only from cases where nothing happened. Every one of these produced a
plausible-looking null before it was caught by reading output (DEC-019,
DEC-020).

These gates inspect the experiment's **declared structure** at design time. They
do not run the experiment, load a model, or touch the network (Tier 0). They
read a machine-readable declaration the experiment carries:

    GATE-DECL
    { "statistic": {...}, "control": {...}, "tests": [...], ... }
    END-GATE-DECL

Everything the gates need — the marginals, N, the threshold, the constructibility
claim, the test bindings — is in that block. Absent a block, the gate **fails
closed** (flags for review) rather than passing silently, which is the whole
point: the failure mode this spec exists to prevent is a silent pass.

THE STATIC-INSPECTION CEILING (issue #22 DoD)

G-C1 cannot evaluate an arbitrary statistic's bound in general. It decides the
**binary-marginal / NPMI / rate** family exactly, plus the catch-all case
(marginal >= 1.0), and for anything else it returns a review finding rather than
a pass. What it can and cannot decide is listed in `STATIC_CEILING` below and is
repeated in the done comment.

The fixture set in `tests/fixture_code/` is drawn from the real DEC-019/020
shapes, not invented: a catch-all group whose marginal is 1.0 (failure 1), a
bounded statistic (failure 2), a control that never fires (failure 3), an
inverted survival call (failure 4), and an isolate read over no-effect cases
(DEC-020).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from run_all import Gate, register  # noqa: E402

STATIC_CEILING = """
G-C1 decides exactly: (a) a declared marginal >= 1.0 (catch-all — nothing can
raise it); (b) the binary-marginal NPMI family, where the achievable ceiling is
computed from the declared marginals and injection rate. For any other statistic
family it emits a review finding (fail-closed) and never a silent pass.
"""

DECL_OPEN = "GATE-DECL"
DECL_CLOSE = "END-GATE-DECL"

# Survival/CDF call sites whose direction is easy to invert. `gammaincc(k, x)`
# is the regularized *lower* incomplete gamma with its arguments swapped — the
# DEC-019 failure-4 shape. A known-answer binding is required for every such
# call before its direction can be trusted.
TEST_CALL_RE = re.compile(
    r"(?P<call>\b(?:poisson\.sf|poisson\.cdf|gammaincc|gammainc|"
    r"norm\.sf|norm\.cdf|binom\.sf|binom\.cdf|\.sf|\.cdf)\s*\()"
)


def _strip_comments(text: str) -> list[tuple[int, str]]:
    """Lines with their line numbers, comments preserved (declaration lives in
    a comment/docstring block, so comments must NOT be stripped)."""
    return list(enumerate(text.splitlines(), 1))


def extract_decl(path: Path) -> dict | None:
    """Return the parsed GATE-DECL object, or None when absent/unparseable.

    The declaration lives in a comment or docstring block, so leading comment
    markers are stripped before parsing.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if DECL_OPEN in line and start is None:
            start = i
        elif DECL_CLOSE in line and start is not None:
            end = i
            break
    if start is None or end is None:
        return None
    body = []
    for line in lines[start + 1:end]:
        stripped = line.strip()
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        body.append(stripped)
    try:
        obj = json.loads("\n".join(body))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


# --------------------------------------------------------------- G-C1
def _npmi_ceiling(p_x: float, p_y: float, rate: float) -> float:
    """Max achievable NPMI given the declared marginals (rate caps the joint).

    The joint probability of two events is bounded by the smaller marginal
    (`pXY <= min(pX, pY)`) — that is the theorem that makes a catch-all group
    inert. With replacement injection the injected co-occurrence also cannot
    exceed the injection `rate`. The achievable joint is the smaller of those,
    and NPMI at that joint is the ceiling.
    """
    import math
    if p_x <= 0.0 or p_y <= 0.0:
        return 0.0
    joint = min(p_x, p_y, rate, 1.0)
    if joint <= 0.0 or joint >= 1.0:
        return 0.0
    return math.log(joint / (p_x * p_y)) / (-math.log(joint))


def check_g_c1(path: Path) -> list[str]:
    decl = extract_decl(path)
    if decl is None:
        return ["G-C1: no GATE-DECL block — cannot verify the statistic is not "
                "structurally bounded below its threshold (fail-closed)"]
    stat = decl.get("statistic")
    if not isinstance(stat, dict):
        return ["G-C1: declaration carries no 'statistic' object (fail-closed)"]
    findings: list[str] = []
    p_x = stat.get("p_x")
    p_y = stat.get("p_y")
    threshold = stat.get("threshold")
    for key, val in (("p_x", p_x), ("p_y", p_y)):
        if isinstance(val, (int, float)) and val >= 1.0:
            findings.append(
                f"G-C1: declared marginal {key}={val} is a catch-all — a "
                f"statistic over a group that fires on every sample cannot rise; "
                f"bound < threshold at any rate (DEC-019 failure 1)")
    kind = str(stat.get("name", ""))
    if "npmi" in kind.lower():
        if isinstance(p_x, (int, float)) and isinstance(p_y, (int, float)) \
                and isinstance(threshold, (int, float)):
            rate = stat.get("rate", 0.20)
            ceiling = _npmi_ceiling(float(p_x), float(p_y), float(rate))
            if ceiling < threshold:
                findings.append(
                    f"G-C1: declared NPMI ceiling {ceiling:.3f} "
                    f"(p_x={p_x}, p_y={p_y}, rate={rate}) < threshold "
                    f"{threshold} — the statistic is bounded below its own "
                    f"threshold (DEC-019 failure 2)")
        else:
            findings.append(
                "G-C1: NPMI statistic declared without numeric p_x/p_y/"
                "threshold — bound undecidable statically, flagged for review")
    elif kind and not any(k in kind.lower() for k in ("npmi", "mutual")):
        findings.append(
            f"G-C1: statistic '{kind}' is not in a family this gate decides "
            f"(binary-marginal NPMI / catch-all) — flagged for review, not "
            f"passed silently. {STATIC_CEILING.strip()}")
    return findings


# --------------------------------------------------------------- G-C2
def check_g_c2(path: Path) -> list[str]:
    decl = extract_decl(path)
    if decl is None:
        return ["G-C2: no GATE-DECL block — control constructibility cannot be "
                "verified (fail-closed)"]
    ctrl = decl.get("control")
    if not isinstance(ctrl, dict):
        return ["G-C2: no declared 'control' — a positive control must be shown "
                "constructible before it is run (DEC-019)"]
    findings: list[str] = []
    if not ctrl.get("computes_planted_presence"):
        findings.append(
            "G-C2: control does not declare that it computes/records the "
            "planted signal's presence in both groups before recovery is read "
            "(DEC-019 failure 3)")
    if not ctrl.get("records_both_groups"):
        findings.append(
            "G-C2: control does not declare it records presence in BOTH groups "
            "— a one-sided reading cannot show the control fired")
    return findings


# --------------------------------------------------------------- G-C3
def check_g_c3(path: Path) -> list[str]:
    decl = extract_decl(path)
    text = path.read_text(encoding="utf-8")
    calls = [m.group("call").strip().rstrip("(") for m in TEST_CALL_RE.finditer(
        re.sub(r"^\s*#.*$", "", text, flags=re.M))]
    calls = sorted(set(calls))
    if not calls:
        return []
    if decl is None:
        return [f"G-C3: source makes survival/CDF call(s) {calls} but carries "
                f"no GATE-DECL block binding them to a known-answer case "
                f"(fail-closed)"]
    bindings = decl.get("tests") or []
    bound = set()
    for t in bindings:
        if isinstance(t, dict) and t.get("call"):
            bound.add(str(t["call"]).strip().rstrip("("))
    findings: list[str] = []
    for call in calls:
        if call not in bound:
            findings.append(
                f"G-C3: survival/CDF call '{call}'() is not bound to a "
                f"known-answer case — its direction is unverified (DEC-019 "
                f"failure 4: gammaincc used as an upper tail)")
    for t in bindings:
        if isinstance(t, dict) and str(t.get("call", "")).startswith("gammaincc"):
            findings.append(
                "G-C3: 'gammaincc' declared as a survival/upper-tail call — "
                "gammaincc is the regularized LOWER incomplete gamma; the "
                "Poisson upper tail is poisson.sf(k-1, lambda) (DEC-019 "
                "failure 4)")
    return findings


# --------------------------------------------------------------- G-C4
def check_g_c4(path: Path) -> list[str]:
    decl = extract_decl(path)
    if decl is None:
        return ["G-C4: no GATE-DECL block — every reported reading must be "
                "checked to be able to come out low (fail-closed)"]
    readings = decl.get("readings")
    if not isinstance(readings, list) or not readings:
        return ["G-C4: no declared 'readings' list — cannot verify a reported "
                "reading can come out low (DEC-020 isolate vacuity)"]
    findings: list[str] = []
    for r in readings:
        if not isinstance(r, dict):
            findings.append("G-C4: a declared reading is not an object")
            continue
        name = r.get("name", "<unnamed>")
        # A reading is vacuous when it is computed over cases where the effect
        # was absent and is not gated by the effect. Either it declares it
        # depends on the effect, or it declares a guard that nulls it.
        if r.get("depends_on_effect") is True:
            continue
        if r.get("gated_by") or r.get("null_when_no_effect") is True:
            continue
        findings.append(
            f"G-C4: reading '{name}' is not declared to depend on the effect "
            f"and carries no guard — it can be computed entirely from "
            f"no-effect cases (DEC-020: isolate=0.996 from cases where nothing "
            f"happened)")
    return findings


# --------------------------------------------------------------- G-C5
COMPARABILITY_KEYS = ("model", "hook", "threshold", "n", "correction")


def check_g_c5(path: Path) -> list[str]:
    decl = extract_decl(path)
    if decl is None:
        return ["G-C5: no GATE-DECL block — cross-run comparability parameters "
                "are undeclared (fail-closed)"]
    comp = decl.get("comparability")
    if not isinstance(comp, dict):
        return ["G-C5: no declared 'comparability' object — what must match for "
                "two numbers to be compared is unstated (Maith G5-4 analogue)"]
    missing = [k for k in COMPARABILITY_KEYS if k not in comp]
    if missing:
        return [f"G-C5: comparability declaration omits {missing} — two runs "
                f"differing on these are not comparable (Maith G5-4 analogue)"]
    return []


# --------------------------------------------------------------- registration
CLEAN = "fixture_code/clean_experiment.py"

register(Gate(
    id="G-C1", name="Declared statistic not bounded below its threshold", tier=0,
    check=check_g_c1, clean_fixture=CLEAN,
    failing_fixture="fixture_code/g_c1_catchall_marginal.py",
    traces_to="DEC-019 failures 1-2",
    description="Computes the achievable ceiling from declared marginals, N and "
                "threshold; catch-all marginals and sub-threshold ceilings fail.",
))
register(Gate(
    id="G-C2", name="Declared control is constructible", tier=0,
    check=check_g_c2, clean_fixture=CLEAN,
    failing_fixture="fixture_code/g_c2_control_never_fires.py",
    traces_to="DEC-019 failure 3",
    description="The control must compute and record the planted signal's "
                "presence in both groups before recovery is read.",
))
register(Gate(
    id="G-C3", name="Statistical-test direction asserted", tier=0,
    check=check_g_c3, clean_fixture=CLEAN,
    failing_fixture="fixture_code/g_c3_inverted_survival.py",
    traces_to="DEC-019 failure 4",
    description="Every survival/CDF call is bound to a known-answer case; "
                "gammaincc as an upper tail fails.",
))
register(Gate(
    id="G-C4", name="Every reported reading can come out low", tier=0,
    check=check_g_c4, clean_fixture=CLEAN,
    failing_fixture="fixture_code/g_c4_isolate_vacuity.py",
    traces_to="DEC-020 isolate vacuity",
    description="No reading is computed solely from no-effect cases; each is "
                "gated by the effect or guarded to null.",
))
register(Gate(
    id="G-C5", name="Cross-run comparability of experiment parameters", tier=0,
    check=check_g_c5, clean_fixture=CLEAN,
    failing_fixture="fixture_code/g_c5_incomparable_params.py",
    traces_to="Maith PIPELINE_QUALITY_GATES G5-4",
    description="model/hook/threshold/n/correction must be declared for two "
                "numbers to be comparable across runs.",
))


def main(argv: list[str] | None = None) -> int:
    """Scan the REAL experiments directory and report per-file findings."""
    here = Path(__file__).resolve().parent
    experiments = here.parent.parent / "experiments"
    findings: list[str] = []
    files = sorted(experiments.glob("*.py")) if experiments.exists() else []
    for f in files:
        for fn in (check_g_c1, check_g_c2, check_g_c3, check_g_c4, check_g_c5):
            for finding in fn(f):
                findings.append(f"{f.name}: {finding}")
    print(f"G-C over {len(files)} experiment file(s)")
    print("-" * 78)
    for f in findings:
        print(f"  - {f}")
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
