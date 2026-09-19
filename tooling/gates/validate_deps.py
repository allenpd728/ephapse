#!/usr/bin/env python3
"""G-R3 — dependency pinning over `requirements.txt` (issue #12).

| ID   | Check |
|------|-------|
| G-R3 | Every requirement carries a version specifier, or declares an inline policy exception |

Two entry points, mirroring `validate_experiments.py`:

    python3 tooling/gates/validate_deps.py   # over the REAL requirements.txt
    (or) run via run_all.py                  # over FIXTURES

THE PIN RULE, AND HOW AN EXCEPTION IS DECLARED

The default rule is the one `requirements.txt`'s header states: a requirement
must carry a version specifier (`==`, `>=`, `~=`, `<=`, `!=`, `>`, `<`).

The header also states a *policy* for one class of package: transitive deps
whose version is determined by their parent are pinned "only if a version
conflict appears". That is a defensible policy, and #21's method constraint is
explicit that the gate must **not** silently pin such a package just to go
green. So the gate recognises an explicit, per-line declaration:

    numpy  # unpinned-by-policy: <rationale>

and a requirement so marked is exempt **provided the rationale is non-empty**.
The rationale is required so the marker cannot become a blanket silence: an
empty `# unpinned-by-policy:` is a finding, not an exemption. This keeps the
exception in exactly one place — the requirement's own line — so the file and
the gate state the same rule rather than a Python set shadowing the prose.

WHAT THIS GATE DELIBERATELY DOES NOT DO

- It does not resolve versions, contact an index, or check that a pin exists
  upstream. Tier 0 is pure file inspection (issue #12 method constraint).
- It does not decide *which* packages deserve an exception. #21 reconciles the
  prose; this gate only gives the policy a checkable form.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from run_all import Gate, register           # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
REQUIREMENTS = REPO / "requirements.txt"

# Any PEP 440 version operator. `===` before `==` so the alternation is explicit
# rather than order-dependent by accident.
PIN_RE = re.compile(r"(===|==|~=|>=|<=|!=|>|<)")
# `# unpinned-by-policy: <rationale>` — the only sanctioned exemption.
EXEMPT_RE = re.compile(r"#\s*unpinned-by-policy\s*:\s*(\S.*)$", re.IGNORECASE)
# A bare marker with no rationale, which must NOT exempt.
EMPTY_EXEMPT_RE = re.compile(r"#\s*unpinned-by-policy\s*:?\s*$", re.IGNORECASE)

# `name[extras] specifier ; marker`
REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")


def _split_comment(line: str) -> tuple[str, str]:
    """Return (code, comment). A `#` starts a comment only at line start or
    after whitespace, so a URL fragment (`...#egg=foo`) is not truncated."""
    m = re.search(r"(?:^|\s)#", line)
    if not m:
        return line.strip(), ""
    idx = m.start() + (1 if m.group(0).startswith((" ", "\t")) else 0)
    return line[:idx].strip(), line[idx:].strip()


def check_deps(path: Path) -> list[str]:
    """Findings for one requirements file (empty = pass)."""
    findings: list[str] = []
    if not path.exists():
        return [f"{path}: file not found"]

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        code, comment = _split_comment(raw)
        if not code:
            continue                      # blank or comment-only
        if code.startswith("-"):
            continue                      # pip option, e.g. --extra-index-url

        m = REQ_RE.match(code)
        if not m:
            findings.append(f"{path.name}:{lineno}: unparseable requirement "
                            f"line: {code!r}")
            continue

        name, _extras, rest = m.group(1), m.group(2), m.group(3)
        # A PEP 508 direct reference (`pkg @ https://...`) carries its version in
        # the URL, not in a specifier, so it is not an unpinned requirement.
        if rest.lstrip().startswith("@"):
            continue
        # Drop an environment marker; it is not a version specifier.
        specifier = rest.split(";", 1)[0]
        if PIN_RE.search(specifier):
            continue                      # pinned — fine

        if comment and EXEMPT_RE.search(comment):
            continue                      # documented policy exception
        if comment and EMPTY_EXEMPT_RE.search(comment):
            findings.append(
                f"{path.name}:{lineno}: {name!r} declares 'unpinned-by-policy' "
                f"with no rationale — an exemption must state why")
            continue

        findings.append(
            f"{path.name}:{lineno}: {name!r} has no version specifier — pin it, "
            f"or mark the line '# unpinned-by-policy: <rationale>'")

    return findings


register(Gate(
    id="G-R3",
    name="dependency pinning",
    tier=0,
    check=check_deps,
    clean_fixture="requirements/pinned.txt",
    failing_fixture="requirements/unpinned.txt",
    traces_to="requirements.txt header; spec §3 (G-R3)",
    description="Every requirement carries a version specifier, or declares an "
                "inline policy exception with a rationale.",
))


# ------------------------------------------------------- direct entry point
def main() -> int:
    """Issue #12's DoD: run over the REAL requirements.txt, per-requirement."""
    print("G-R3 over the real requirements.txt")
    print("=" * 78)
    if not REQUIREMENTS.exists():
        print(f"requirements.txt not found at {REQUIREMENTS}")
        return 1

    text = REQUIREMENTS.read_text(encoding="utf-8")
    n_req = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        code, comment = _split_comment(raw)
        if not code or code.startswith("-"):
            continue
        m = REQ_RE.match(code)
        if not m:
            continue
        n_req += 1
        name, _e, rest = m.group(1), m.group(2), m.group(3)
        specifier = rest.split(";", 1)[0]
        if PIN_RE.search(specifier):
            status = "pinned"
        elif comment and EXEMPT_RE.search(comment):
            status = "EXEMPT (unpinned-by-policy)"
        else:
            status = "UNPINNED"
        print(f"  line {lineno:>2}  {name:<20} {status}")

    findings = check_deps(REQUIREMENTS)
    print("-" * 78)
    print(f"{n_req} requirement(s) inspected; {len(findings)} finding(s)")
    for f in findings:
        print(f"  - {f}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())