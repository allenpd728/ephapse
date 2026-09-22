#!/usr/bin/env python3
"""G-R1, G-R2, G-R5 — experiment-artifact gates (issue #11).

Over `experiments/*.py` and `experiments/README.md`. These are the gates for the
two mechanical defects from the repo's first two sessions: a file loading a
model the target DEC does not authorize, and a run log that omits rows.

| ID   | Check |
|------|-------|
| G-R1 | Six mandatory header fields for hypothesis-test files; the documented three-field exemption for infrastructure files |
| G-R2 | Model id matches the authorized target unless a DEC authorizes otherwise — read from one machine-readable source, not hardcoded |
| G-R5 | Every `experiments/*.py` has a row in the `experiments/README.md` run log |

TWO FALSE-NEGATIVE HOLES CLOSED (issue #24). Both were reachable by editing a
docstring, and both let a violating file pass:

* **Hole 2 — the exemption was self-granted by prose.** `_is_infra` accepted a
  line-leading "infrastructure file" declaration from *any* file, so a
  hypothesis-test file could drop `Null`/`Correction` by adding one sentence.
  The exemption is now **filename-based**; a bare declaration no longer excuses
  a file. The declaration is still recorded and cross-checked, but it cannot
  grant the exemption on its own. Closing this hole is what exposes the real
  tree's `gen_cross_domain.py`, which relied on the prose route; the correct
  response is a header, not a new exemption pattern — whether a genuinely
  infrastructure file belongs in the enumerated set is #16's README/exemption
  reconciliation.
* **Hole 1 — no attribution escape.** `check_model_authorized` flagged any
  non-target id unconditionally, so #15 could not honestly repair the tree: it
  had to falsify the superseded 160M measurements or delete them. A non-target
  id is now accepted when the file carries a line-leading
  `**Supersedes: <decision-id>**` naming the decision that *is* the model
  decision (read from `target_model.txt`, not hardcoded). An unrelated DEC
  citation does not qualify — the earlier bare `DEC-<n>` draft failed exactly
  that way, per #24's method constraint.

Two entry points, deliberately:

    python3 tooling/gates/validate_experiments.py     # over the REAL tree
    (or) run via run_all.py                            # over FIXTURES

The first is issue #11's Definition of Done: it must exit non-zero on the tree
as of #11, naming the files. The second is the harness contract: a fixture
directory that passes and one that fails. Repairing the real artifacts is #15.

**G-R2 fails closed.** A file whose model cannot be determined is flagged, not
skipped. "Cannot determine" is exactly the state in which a substitution would
go unnoticed, so accepting it would defeat the gate.

THE MODEL SOURCE (the "single machine-readable source" the issue asks for).
`docs/decisions/LOG.md` is prose and deriving a model id from it is brittle, so
the authorized target is declared in `tooling/gates/target_model.txt`. That file
is the one place this gate reads the target from. Issue #11's method constraint
phrased this as "one machine-readable source shared with #12", but that reference
does not resolve — #12 is dependency pinning over `requirements.txt` and has no
model dimension, so `validate_deps.py` reads no target file. A DEC authorizing a
different model adds a line to `target_model.txt` *and* records the DEC; the gate
does not parse the decision log.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from run_all import Gate, register           # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
EXPERIMENTS = REPO / "experiments"
TARGET_FILE = Path(__file__).resolve().parent / "target_model.txt"

FULL_FIELDS = ("Model", "Inputs", "Question", "Null", "Correction", "Issue")
REDUCED_FIELDS = ("Model", "Question", "Issue")

# The exemption is a filename pattern, never "whose purpose is measuring the
# environment" — that phrasing is not enumerable, so it cannot be checked
# (issue #11 method constraint). The enumerated patterns are the whole
# exemption: `_is_infra` is a function of the filename alone. An earlier
# version also accepted a line-leading "infrastructure file" declaration from
# any file; issue #24 hole 2 showed that let a hypothesis-test file excuse
# itself by editing its docstring, so the declaration no longer grants the
# exemption. INFRA_DECL_RE is retained only to report a declaration on a
# non-exempt name (a likely prose-vs-name mismatch for a later issue). The
# enumerated set is the README's (`experiments/README.md` §Infrastructure);
# whether other genuinely-infrastructural names should join it is #16's
# README/exemption reconciliation, not this hole-closure.
INFRA_PATTERNS = ("sandbox-baseline-*", "latency-*")
INFRA_DECL_RE = re.compile(
    r"^\s*\**\s*infrastructure\s*(?:/|\band\b)?\s*(?:baseline\s*)?file\b",
    re.MULTILINE | re.IGNORECASE)

FIELD_RE = re.compile(r"^\s*\**\s*(Model|Inputs|Question|Null|Correction|Issue)\b",
                      re.MULTILINE | re.IGNORECASE)
HEADER_MODEL_RE = re.compile(
    r"^\s*\**\s*Model\s*\**\s*:?\s*(.+)$", re.MULTILINE | re.IGNORECASE)

MODEL_ASSIGN_RE = re.compile(r'^\s*MODEL\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
FROM_PRETRAINED_RE = re.compile(r'from_pretrained\(\s*["\']([^"\']+)["\']')
# Recognisable model ids, so "a model we can see but which is not the target" is
# distinguishable from "no model id at all" (which fails closed).
ANY_MODEL_RE = re.compile(
    r'["\']((?:pythia|gpt2|EleutherAI)[A-Za-z0-9._/-]*)["\']')
# An id-shaped token in prose/header text.
ID_IN_TEXT_RE = re.compile(r"\b((?:pythia|gpt2|EleutherAI)[A-Za-z0-9._/-]*)")

SAE_SUFFIXES = ("-res-sm", "-res-jb", "-res-mid", "-res-post", "-res-mid")

# G-R2 attribution policy (issue #24 hole 1). Line-leading `model-decision:`
# entries in target_model.txt enumerate the decision id(s) that ARE the model
# decision; a file may carry a non-target model only by declaring a
# line-leading `**Supersedes: <one of those>**`. Reading the policy from the
# same source file keeps the escape from silently drifting from the target.
MODEL_DECISION_LINE_RE = re.compile(
    r"^model-decision:\s*(\S+)\s*$", re.MULTILINE | re.IGNORECASE)
SUPERSEDES_RE = re.compile(
    r"^\s*\**\s*supersedes\s*\**\s*:?\s*\**\s*([A-Za-z0-9._-]+)",
    re.MULTILINE | re.IGNORECASE)
DECISION_MENTION_RE = re.compile(r"\bDEC-\d+\b", re.IGNORECASE)


def _experiment_files(root: Path) -> list[Path]:
    if root.is_dir():
        return sorted(root.glob("*.py"))
    return [root] if root.exists() else []


def normalize_model_id(mid: str) -> str:
    """Strip an SAE-release suffix so the base model id is comparable."""
    for suffix in SAE_SUFFIXES:
        if mid.endswith(suffix):
            return mid[: -len(suffix)]
    return mid


def _is_infra(name: str, text: str) -> bool:
    """Infrastructure exemption: an enumerated **filename** pattern.

    The pattern is matched against the filename **with any leading date stripped**.
    The naming convention is `<YYYY-MM-DD>-<slug>.py`, so the README's patterns
    (`sandbox-baseline-*`, `latency-*`) can never match a raw filename — every
    one begins with a date. Found by running G-R1 over the real tree, where the
    two infrastructure files the README names were reported as full-header
    violations because the pattern silently never applied. Recorded rather than
    patched silently: a documented pattern that matches nothing is the same class
    of defect as a gate with no failing fixture.

    `text` is accepted for signature compatibility but deliberately **ignored**.
    Issue #24 hole 2: the previous version returned True for any file carrying a
    line-leading "infrastructure file" declaration, so a hypothesis-test file
    could drop `Null`/`Correction` with a docstring edit. A file cannot grant
    itself an exemption by describing itself, so the exemption is name-only.
    """
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name)
    for pat in INFRA_PATTERNS:
        if pat.endswith("*"):
            if slug.startswith(pat[:-1]) or name.startswith(pat[:-1]):
                return True
        elif slug == pat or name == pat:
            return True
    return False


def _present_fields(text: str) -> set[str]:
    return {m.group(1).capitalize() for m in FIELD_RE.finditer(text[:4000])}


def load_target_models() -> list[str]:
    """Authorized model ids, from the single machine-readable source."""
    if not TARGET_FILE.exists():
        return []
    out = []
    for line in TARGET_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not MODEL_DECISION_LINE_RE.match(line):
            out.append(line)
    return out


def load_model_decisions() -> list[str]:
    """Decision ids that ARE the model decision, per target_model.txt.

    G-R2's attribution escape only accepts a `Supersedes:` naming one of these,
    so a file cannot silence the gate by citing an unrelated decision (issue #24
    hole 1 method constraint). Empty when the policy line is absent, in which
    case no supersession is accepted — fail closed.
    """
    if not TARGET_FILE.exists():
        return []
    return MODEL_DECISION_LINE_RE.findall(
        TARGET_FILE.read_text(encoding="utf-8"))


def supersession_declared(text: str, decisions: list[str]) -> bool:
    """A line-leading `Supersedes: <decision>` naming a model decision."""
    for m in SUPERSEDES_RE.finditer(text):
        cited = m.group(1)
        if any(cited.lower() == d.lower() for d in decisions):
            return True
    return False


def _authorized(mid: str, targets: list[str]) -> bool:
    m = normalize_model_id(mid)
    return any(m == t or m.startswith(t + "-") or t.startswith(m + "-")
               for t in targets)


# ------------------------------------------------------------------- G-R1
def check_header_completeness(path: Path) -> list[str]:
    findings: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    present = _present_fields(text)
    infra = _is_infra(path.name, text)
    required = REDUCED_FIELDS if infra else FULL_FIELDS
    missing = [f for f in required if f not in present]
    if missing:
        kind = "infrastructure" if infra else "full"
        findings.append(f"{path.name}: G-R1 {kind} header missing "
                        f"{len(missing)} field(s): {', '.join(missing)}")
    return findings


def gate_r1(root: Path) -> list[str]:
    findings: list[str] = []
    for f in _experiment_files(root):
        findings.extend(check_header_completeness(f))
    return findings


# ------------------------------------------------------------------- G-R2
def extract_models(path: Path) -> tuple[set[str], str | None]:
    """Model ids visible in a file, plus the id named in its Model header."""
    text = path.read_text(encoding="utf-8", errors="replace")
    ids: set[str] = set()
    ids.update(MODEL_ASSIGN_RE.findall(text))
    ids.update(FROM_PRETRAINED_RE.findall(text))
    ids.update(ANY_MODEL_RE.findall(text))
    norm = {normalize_model_id(i) for i in ids}

    header: str | None = None
    m = HEADER_MODEL_RE.search(text[:4000])
    if m:
        header = m.group(1).strip().rstrip(".,")
    return norm, header


def check_model_authorized(path: Path, targets: list[str],
                           decisions: list[str] | None = None) -> list[str]:
    """G-R2 for one file. Fails closed when no model can be determined.

    A non-target model is accepted only when the file declares a line-leading
    `Supersedes: <model-decision>` (issue #24 hole 1). `decisions` defaults to
    the policy read from `target_model.txt`; pass `[]` to disable the escape
    (fixtures that assert it is absent).
    """
    findings: list[str] = []
    ids, header = extract_models(path)

    # A header that names no *recognisable model id* is not a determination.
    # The first version of this gate treated any non-empty Model line as
    # "determined", so a header reading "(unstated)" or "TODO" silently passed —
    # the exact hole the fail-closed rule exists to close. A header only counts
    # when it yields at least one id-shaped token.
    header_ids = set(ID_IN_TEXT_RE.findall(header)) if header else set()
    determined = bool(ids) or bool(header_ids)

    if not determined:
        findings.append(f"{path.name}: G-R2 cannot determine a model id "
                        f"(fails closed — a substitution could go unnoticed)")
        return findings

    decisions = load_model_decisions() if decisions is None else decisions
    text = path.read_text(encoding="utf-8", errors="replace")
    superseded = supersession_declared(text, decisions)

    def finding(verb: str, mid: str, suffix: str = "") -> str | None:
        """A finding, or None when the id is authorized or validly superseded.

        A valid `Supersedes:` yields **no** finding: acceptance is silence, so a
        correctly-attributed superseded file leaves the gate green.
        """
        if _authorized(mid, targets):
            return None
        if superseded:
            return None
        return (f"{path.name}: G-R2 {verb} model {mid!r}, which is not "
                f"an authorized target {targets} (no valid `Supersedes:` "
                f"declaration){suffix}")

    for h in sorted(header_ids):
        f = finding("header names", h)
        if f:
            findings.append(f)

    for i in sorted(ids):
        f = finding("loads", i, " (DEC-014)")
        if f:
            findings.append(f)
    return findings


def gate_r2(root: Path) -> list[str]:
    targets = load_target_models()
    if not targets:
        return [f"G-R2 cannot read the authorized target list from "
                f"{TARGET_FILE.name} — cannot check model authorization"]
    decisions = load_model_decisions()
    findings: list[str] = []
    for f in _experiment_files(root):
        findings.extend(check_model_authorized(f, targets, decisions))
    return findings


# ------------------------------------------------------------------- G-R5
RUN_LOG_ROW_RE = re.compile(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|")


def _logged_filenames(run_log: Path) -> set[str]:
    names: set[str] = set()
    for line in run_log.read_text(encoding="utf-8").splitlines():
        if not RUN_LOG_ROW_RE.match(line):
            continue
        for m in re.finditer(r"`([^`]+)`", line):
            names.add(Path(m.group(1)).name)
    return names


def check_run_log_currency(experiments_dir: Path, run_log: Path) -> list[str]:
    if not run_log.exists():
        return [f"G-R5 run log missing: {run_log.name}"]
    logged = _logged_filenames(run_log)
    return [f"{p.name}: G-R5 has no row in the run log"
            for p in sorted(experiments_dir.glob("*.py"))
            if p.name not in logged]


def gate_r5(root: Path) -> list[str]:
    exp_dir = root if root.is_dir() else root.parent
    return check_run_log_currency(exp_dir, exp_dir / "README.md")


# ------------------------------------------------------------- registration
# The registered checks operate on a fixture *directory* of experiment files, so
# the harness's clean/failing pair is a directory tree rather than one file.
register(Gate(
    id="G-R1", name="experiment header completeness", tier=0, check=gate_r1,
    clean_fixture="experiments_clean",
    failing_fixture="experiments_r1_missing_field",
    traces_to="experiments/README.md; spec §3",
    description="Six mandatory header fields, or the documented three-field "
                "infrastructure exemption (filename-enumerated; issue #24).",
))

register(Gate(
    id="G-R2", name="experiment model authorization", tier=0, check=gate_r2,
    clean_fixture="experiments_clean",
    failing_fixture="experiments_r2_unrelated_decision",
    traces_to="DEC-014; spec §1 defect #1",
    description="Model id matches the authorized target. Fails closed; a "
                "non-target id is accepted only with a `Supersedes:` "
                "attribution naming the model decision (issue #24).",
))

register(Gate(
    id="G-R5", name="experiment run-log currency", tier=0, check=gate_r5,
    clean_fixture="experiments_clean",
    failing_fixture="experiments_r5_missing_log_row",
    traces_to="experiments/README.md; spec §1 defect #2",
    description="Every experiments/*.py has a row in the run log.",
))


# ------------------------------------------------------- direct entry point
def main() -> int:
    """Issue #11's DoD: run over the REAL tree and report per-file findings."""
    print("G-R1 / G-R2 / G-R5 over the real experiments tree")
    print("=" * 78)
    targets = load_target_models()
    print(f"authorized target model(s): {targets or 'NONE — cannot check G-R2'}")
    print()

    total = 0
    for gate_id, fn in (("G-R1", gate_r1), ("G-R2", gate_r2), ("G-R5", gate_r5)):
        findings = fn(EXPERIMENTS)
        total += len(findings)
        status = "FAIL" if findings else "PASS"
        print(f"[{status}] {gate_id} ({len(findings)} finding(s))")
        for f in findings:
            print(f"        - {f}")
        print()

    n_files = len(_experiment_files(EXPERIMENTS))
    print("-" * 78)
    print(f"{n_files} experiment file(s) inspected; {total} finding(s) total")
    if total:
        print("This is the EXPECTED state for issue #11 — the gate going red is "
              "the evidence it works.")
        print("Repairing the artifacts is #15, not this task.")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
