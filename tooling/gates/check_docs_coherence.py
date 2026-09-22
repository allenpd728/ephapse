#!/usr/bin/env python3
"""G-R4 — docs coherence over the settled facts (issue #20).

| ID   | Check |
|------|-------|
| G-R4 | README / handoff / DEC log / experiments README agree on the settled target model and the settled SAE facts |

This automates the manual docs-coherence sweep in
`docs/MULTI_AGENT_WORKFLOW.md` § Step 1b. Two entry points, mirroring
`validate_experiments.py` and `validate_deps.py`:

    python3 tooling/gates/check_docs_coherence.py            # over the REAL docs
    python3 tooling/gates/run_all.py --gate G-R4             # over FIXTURES

THE TWO FAILURE MODES THIS GATE MUST AVOID

The naive implementation ("does this string appear in all four docs?") produces
false greens, and the false-red is subtler still:

1. **False green.** Requiring a literal string in every obliged doc cannot see a
   doc that states a *contradictory current value*, which is the defect DEC-014
   and DEC-015 left behind.

2. **False red — the corrected-history case.** A decision-log entry that
   *documents* a superseded value is correct history, not a contradiction.
   DEC-010, DEC-014 and DEC-015 all record withdrawn claims, and the handoff's
   compute tables legitimately cite Pythia-160M **measurements** as upper bounds
   after the target moved to `pythia-70m-deduped`. A gate that fires on those is
   useless.

HOW THE DISTINCTION IS DRAWN

Two orthogonal signals, both required before a finding:

* **Assertion** — a line only *states a current value* when it uses an assertive
  form (`MODEL = "<id>"`, `target model is <id>`, `probed model is <id>`). A
  measurement table row (`| Pythia-160M | 2.68 GB RSS |`) or a bare mention is
  not an assertion about the settled value, so it is silent.

* **Correction cue** — an assertive line is exempt when it also carries a cue
  that the value is historical: `superseded`, `withdrawn`, `corrected`,
  `no longer`, `there is no`, `was`, `old`, `former`, `previously`. The cue must
  be on the same line as the assertion, so "records that a value was once wrong"
  is distinguished from "states a wrong current value".

An assertive line with a non-authoritative value and **no** cue is the finding.

FACTS, AND WHERE EACH IS AUTHORITATIVE

| Fact | Authoritative source |
|------|----------------------|
| target model id | `tooling/gates/target_model.txt` (the machine-readable single source, read by G-R2) |
| no Pythia-160M SAE release | `tooling/gates/target_model.txt` comment + DEC-014 (`docs/decisions/LOG.md`) |

Tier 0: pure file inspection. No network, no model, no torch.
"""
from __future__ import annotations

import re
import sys
from collections import namedtuple
from pathlib import Path

from run_all import Gate, register           # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
TARGET_MODEL = REPO / "tooling" / "gates" / "target_model.txt"

# The docs obliged to state the settled model coherently. `docs/decisions/LOG.md`
# is included because DEC-014 *resolves* the value there; the corrected-history
# rule is what keeps the older entries from tripping the gate.
OBLIGED = (
    "README.md",
    "docs/AGENT_HANDOFF.md",
    "docs/decisions/LOG.md",
    "experiments/README.md",
)

# A value is historical, not current, when the line carries one of these. Kept
# deliberately broad — a false exemption is a missed contradiction, a false
# finding is a gate nobody trusts, and the cue is only consulted on assertive
# lines.
CUE_RE = re.compile(
    r"(supersed\w*|withdrawn|withdraw\w*|correct\w*|no\s+longer|there\s+is\s+no"
    r"|not\s+the|rather\s+than|was\s+|were\s+|old\s+|former\w*|previously"
    r"|historical|unbuildable|abandon\w*)",
    re.IGNORECASE,
)

# A line *asserts* the settled model when it binds a model id to the model role.
# Two shapes cover the repo's prose and its machine-readable snippets:
#   MODEL = "pythia-70m-deduped"                      (machine-readable snippet)
#   the target model is `pythia-70m-deduped`          (prose; `is`/`:`/`=` link)
# A bare model name, or a measurement-table row, is not an assertion.
#
# The id shape requires a hyphen or a letter-digit-letter run so prose words
# ("this", "run") cannot masquerade as an id.
_MODEL_ID = r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+|[A-Za-z]+[0-9]+[A-Za-z0-9.]*"
# The link between the role and the id. `\b` is placed on the word forms only —
# a word boundary before `:` or `=` never matches, which would silently disable
# the prose form.
_LINK = r"(?:(?:is|are)\b|[:=])"
ASSERT_RE = re.compile(
    r"\bMODEL\s*=\s*[\"'`]?(?P<eq>" + _MODEL_ID + r")[\"'`]?"
    r"|\b(?:target|probed)\s+model\b[^.\n]{0,30}?" + _LINK
    + r"\s*[\s*`\"']*(?P<role>" + _MODEL_ID + r")",
    re.IGNORECASE,
)


def authoritative_models() -> set[str]:
    """The authorized target model ids, from the machine-readable source.

    Lines beginning `model-decision:` are G-R2's attribution policy, not model
    ids, so they are skipped rather than parsed as a target.
    """
    ids: set[str] = set()
    if not TARGET_MODEL.exists():
        return ids
    for line in TARGET_MODEL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("model-decision:"):
            continue
        ids.add(line)
    return ids


# A namedtuple, not a dataclass: `run_all._load_gate_modules` execs gate modules
# without registering them in `sys.modules`, and `dataclasses` reads
# `sys.modules[cls.__module__]` — which is None there and raises at import time.
# Namedtuples have no such dependency.
Fact = namedtuple("Fact", "id authoritative check_line")


def _model_id_findings(line: str, authorized: set[str]) -> list[str]:
    """Findings for the 'target model id' fact on one line."""
    m = ASSERT_RE.search(line)
    if not m:
        return []
    value = m.group("eq") or m.group("role")
    if value is None:
        return []
    # Strip a trailing prose artifact (e.g. "is pythia-70m-deduped,").
    value = value.rstrip(".,;:")
    if value in authorized:
        return []
    if CUE_RE.search(line):
        return []
    return [f"states target model `{value}`, not the authorized "
            f"{'/'.join(sorted(authorized))}"]


# A 160M SAE release is the fact DEC-014 settles *absent*. Only a line that
# *claims the artifact exists* contradicts it. Requiring all three of (a) a 160M
# reference, (b) an SAE/release noun, and (c) a positive-existence verb keeps the
# gate silent on the legitimate prose that mentions both — e.g. "a 160M target
# would require training an SAE first" (no artifact claimed) and "there is no
# Pythia-160M release" (negated). Both of those appear in the real docs, and a
# gate that fires on them is not usable.
_160M_RE = re.compile(r"\b160m\b", re.IGNORECASE)
_SAE_NOUN_RE = re.compile(r"\b(sae|release)\b", re.IGNORECASE)
_NEGATION_RE = re.compile(
    r"\b(no|not|never|none|absent|without|does\s+not|do\s+not|don't)\b", re.IGNORECASE
)
_EXISTS_VERB_RE = re.compile(
    # Note: no `releas*` here — "release" is already the noun this fact matches,
    # and counting it as the verb too makes any sentence containing the word fire.
    r"\b(exists?|exist\w*|ships?|shipp\w*|available|provid\w*"
    r"|use[sd]?|usable|works?|claim\w*|has|have)\b",
    re.IGNORECASE,
)


def _no_160m_sae_findings(line: str) -> list[str]:
    if not (_160M_RE.search(line) and _SAE_NOUN_RE.search(line)):
        return []
    if not _EXISTS_VERB_RE.search(line):
        return []
    if _NEGATION_RE.search(line) or CUE_RE.search(line):
        return []
    return ["claims a Pythia-160M SAE release, which does not exist (DEC-014)"]


def facts() -> list[Fact]:
    authorized = authoritative_models()
    return [
        Fact(
            id="target-model-id",
            authoritative="tooling/gates/target_model.txt",
            check_line=lambda line: _model_id_findings(line, authorized),
        ),
        Fact(
            id="no-pythia-160m-sae",
            authoritative="tooling/gates/target_model.txt comment; DEC-014",
            check_line=_no_160m_sae_findings,
        ),
    ]


def check_docs(path: Path, obliged: tuple[str, ...] | None = None) -> list[str]:
    """Scan a docs set for contradictory *current* statements.

    `path` is either a single doc or a directory of docs. When it is a directory
    (the fixture form) every `*.md` beneath it is scanned; on the real tree the
    `obliged` list names the four docs. Findings are prefixed with the file so
    the report is actionable.
    """
    findings: list[str] = []
    if path.is_dir():
        docs = sorted(p for p in path.rglob("*.md") if p.is_file())
        files = [(p, p.relative_to(path).as_posix()) for p in docs]
    else:
        docs = [path]
        files = [(path, path.name)]

    for fact in facts():
        for p, label in files:
            if obliged is not None and not path.is_dir() and label not in obliged:
                continue
            for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                for finding in fact.check_line(line):
                    findings.append(f"{label}:{lineno}: {fact.id}: {finding}")
    return findings


def gate_r4(path: Path) -> list[str]:
    """Fixture entry point: scan a directory of docs with no obliged filter."""
    return check_docs(path)


register(Gate(
    id="G-R4",
    name="docs coherence",
    tier=0,
    check=gate_r4,
    clean_fixture="docs_coherence/coherent",
    failing_fixture="docs_coherence/contradictory_current",
    traces_to="workflow § Step 1b; spec §3 (G-R4); DEC-014, DEC-015",
    description="The obliged docs agree on the settled target model and the "
                "settled SAE facts. Corrected-history entries pass; an assertive "
                "contradictory current value fails.",
))


# ------------------------------------------------------- direct entry point
def main() -> int:
    """Scan the REAL obliged docs and report per-file findings."""
    print("G-R4 over the real obliged docs")
    print("=" * 78)
    authorized = authoritative_models()
    print(f"authoritative target model: {', '.join(sorted(authorized)) or '<none>'}")
    findings: list[str] = []
    for fact in facts():
        for rel in OBLIGED:
            p = REPO / rel
            if not p.exists():
                findings.append(f"{rel}: missing obliged doc")
                continue
            for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                for finding in fact.check_line(line):
                    findings.append(f"{rel}:{lineno}: {fact.id}: {finding}")
    print("-" * 78)
    print(f"{len(OBLIGED)} obliged doc(s) inspected; {len(findings)} finding(s)")
    for f in findings:
        print(f"  - {f}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
