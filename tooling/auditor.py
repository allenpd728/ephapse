#!/usr/bin/env python3
"""auditor.py — daily repo health & drift audit. Read-only.

See docs/AUDITOR.md for the full contract. Summary of the rules that matter:

  * This tool NEVER edits code, never closes/merges anything, and never adds a
    claimable-status label. Its only writes are (a) GitHub issues/comments/labels
    and (b) one appended line in this repo's own status_log.jsonl.
  * Every finding is held for human review via the ``on-hold`` label plus
    ``auditor:proposed`` or ``auditor:revise``. Nothing is auto-actioned.
  * The run is idempotent and checkpointed: it exits silently if HEAD has not
    moved since the last successful run, and on failure it does not advance the
    checkpoint so the same range is retried.
  * Analysis is deterministic (no LLM). That is a deliberate choice: every check
    below is a mechanical fact about the tree, and a deterministic run costs no
    tokens, cannot hallucinate, and is safe to re-trigger. The single exception is
    one read-only POST to the public OSV.dev advisory API, which sends package
    names/versions only and whose failure is *reported* rather than swallowed.

Design note: findings are computed in full BEFORE anything is written, and the
GitHub writes only begin once every check has completed. That gives the
"either complete the run's output or produce nothing" property required by the
spec for the common failure mode (a check crashing mid-run).

Usage:
    python3 tooling/auditor.py --repo philipdallen/Maith --dry-run
    python3 tooling/auditor.py --repo philipdallen/Maith
    python3 tooling/auditor.py --repo philipdallen/Maith --force   # ignore checkpoint

Exit codes: 0 = ran or skipped cleanly; 1 = real error (checkpoint not advanced).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
STATE_PATH = "status/auditor_state.json"
STATUS_LOG = "status_log.jsonl"

LABEL_PROPOSED = "auditor:proposed"
LABEL_REVISE = "auditor:revise"
LABEL_HOLD = "on-hold"

# Labels this repo's task protocol uses to mark work claimable by agents.
# The auditor must never add one of these -- only the human does, after review.
CLAIMABLE_LABELS = {"status:available", "status:claimed"}

# A TODO older than this many days is reported.
TODO_MAX_AGE_DAYS = 120

# Cap so a repo with a large backlog produces a readable digest.
MAX_TODOS_REPORTED = 8

CATEGORY_ARCH = "Architecture & drift"
CATEGORY_BUGS = "Bugs & hygiene"
CATEGORY_SECURITY = "Security"
CATEGORY_CATCHALL = "Catch-all"

# --- security & consistency -------------------------------------------------

# Retired account/repo slugs. A slug listed here is a *contradiction* when it
# survives outside the frozen record: prose or a command that says the project
# lives somewhere it no longer does. Only slugs known to have been retired are
# listed -- flagging "any slug that is not the current owner" would fire on the
# third-party projects these docs legitimately cite (actions/checkout, and so on).
RETIRED_OWNER_SLUGS = ("allenpd728",)

# Frozen logs record the slug as it was at the time and rewriting them would make
# them false; test files carry fixtures that must be able to fire every check.
# Both are out of scope by design.
STALE_OWNER_EXCLUDE = ("docs/decisions/", "docs/history/", "tools/tests/",
                       "tooling/tests/", "tests/")

# High-confidence credential shapes only. A check that fires on prose, example
# keys, or vendored lockfiles is a check that gets ignored, so every pattern below
# is one that essentially cannot occur by accident.
SECRET_PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("github-fine-grained-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe-live-key", re.compile(r"\bsk_live_[A-Za-z0-9]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{20,}\b")),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
]
SECRET_EXCLUDE_NAMES = {"package-lock.json", "poetry.lock", "uv.lock", "yarn.lock",
                        "Cargo.lock", "pnpm-lock.yaml", "go.sum"}
MAX_SECRET_FINDINGS = 5

# Files larger than this are skipped by the byte-scanning checks: a vendored blob
# is not where a credential is introduced, and reading it only slows the audit.
MAX_SCANNED_BYTES = 2_000_000

WORKFLOW_DIR = ".github/workflows"

# Triggers that either can write, or run with a token in a context where untrusted
# input is present. A workflow using one of these is expected to declare an
# explicit, least-privilege `permissions:` block.
WRITE_TRIGGERS = ("push", "pull_request_target", "workflow_run", "issue_comment",
                  "release", "schedule", "workflow_dispatch")

# Top-level `permissions:` -- column 0 only. A step-scoped `permissions:` does not
# satisfy this: it is the job-level default that decides what the token may do.
TOP_LEVEL_PERMISSIONS_RE = re.compile(r"^permissions\s*:", re.M)
# Untrusted, attacker-influenced expressions. `github.repository` and
# `secrets.*` are deliberately absent: they are not attacker-controlled, and
# flagging them would make this check noise.
UNTRUSTED_INTERP_RE = re.compile(
    r"\$\{\{\s*(?:github\.event\.|github\.head_ref|inputs\.)[^}]*\}\}")
CHECKOUT_RE = re.compile(r"uses\s*:\s*[\"']?actions/checkout@")
PR_HEAD_REF_RE = re.compile(r"github\.event\.pull_request\.head|refs/pull/")

OSV_API = "https://api.osv.dev/v1/querybatch"
OSV_ECOSYSTEM = "PyPI"
REQUIREMENTS_FILE = "requirements.txt"


# --------------------------------------------------------------------------
# GitHub client
# --------------------------------------------------------------------------

class GitHub:
    def __init__(self, token: str | None):
        self.token = token

    def _req(self, method: str, path: str, body=None):
        url = path if path.startswith("http") else API + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "repo-auditor"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}

    def get(self, path: str):
        return self._req("GET", path)

    def post(self, path: str, body):
        return self._req("POST", path, body)

    def patch(self, path: str, body):
        return self._req("PATCH", path, body)

    def paged(self, path: str) -> list:
        out, url = [], API + path
        while url:
            headers_probe = {"Accept": "application/vnd.github+json", "User-Agent": "repo-auditor"}
            if self.token:
                headers_probe["Authorization"] = f"Bearer {self.token}"
            req = urllib.request.Request(url, headers=headers_probe)
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode())
                link = resp.headers.get("Link", "")
            if not isinstance(data, list):
                return data
            out.extend(data)
            url = None
            for part in link.split(","):
                seg = part.split(";")
                if len(seg) >= 2 and 'rel="next"' in seg[1]:
                    url = seg[0].strip().strip("<>")
        return out


# --------------------------------------------------------------------------
# local git helpers
# --------------------------------------------------------------------------

def git(args: list[str], cwd: Path) -> str:
    p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def head_sha(root: Path) -> str:
    return git(["rev-parse", "HEAD"], root).strip()


def commits_between(root: Path, old: str, new: str) -> list[dict]:
    """Commits in (old, new].

    With no checkpoint (first run) the range is deliberately bounded to the last
    ~24h rather than "the last 200 commits": the digest's job is "what changed
    since the last run", and a first run dumping 200 commits of history buries
    the finding list a reader actually needs. The date bound degrades cleanly --
    if the repo had no commits yesterday, the digest says so honestly.
    """
    if old:
        rng = [f"{old}..{new}"]
    else:
        rng = [new, "--since=24 hours ago"]
    out = git(["log"] + rng + ["--pretty=format:%H%x1f%an%x1f%ad%x1f%s", "--date=short"], root)
    commits = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({"sha": parts[0], "author": parts[1],
                            "date": parts[2], "subject": parts[3]})
    return commits


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

class Finding:
    __slots__ = ("check", "category", "title", "body", "subject")

    def __init__(self, check: str, category: str, title: str, body: str, subject: str):
        self.check = check            # stable id, used in the dedup signature
        self.category = category
        self.title = title
        self.body = body
        self.subject = subject        # file/area the finding is about

    def signature(self) -> str:
        """Stable dedup key. Title-prefix form so it survives an edit to the body."""
        return f"[auditor:{self.check}] {self.subject}"


# Committed artifacts that should not be tracked.
CRUFT = [".DS_Store", "Thumbs.db", "__pycache__", ".pyc", ".orig", ".rej", ".pyo"]


def check_committed_artifacts(root: Path) -> list[Finding]:
    """Artifacts that are TRACKED by git and should not be.

    Deliberately queries git rather than walking the filesystem: an untracked
    ``__pycache__`` left by a local test run is normal noise, not drift, and
    reporting it would make this check cry wolf. Only committed cruft matters
    because only committed cruft is visible to everyone who clones.
    """
    tracked = git(["ls-files"], root).splitlines()
    patterns = (".DS_Store", "Thumbs.db", ".pyc", ".pyo", ".orig", ".rej", ".swp")
    hits = [p for p in tracked if p.endswith(patterns) or "__pycache__/" in p]
    out, seen = [], set()
    for rel in hits:
        kind = "pycache" if "__pycache__/" in rel or rel.endswith((".pyc", ".pyo")) \
            else Path(rel).name
        if kind in seen:
            continue
        seen.add(kind)
        out.append(Finding(
            "committed-artifact", CATEGORY_BUGS,
            f"Tracked build/OS artifact: {rel}",
            f"`{rel}` is committed but is an editor/OS/build artifact. Remove it from the "
            f"index (`git rm --cached`) and add the pattern to `.gitignore`.",
            rel))
    return out


def check_stale_todos(root: Path) -> list[Finding]:
    """TODO/FIXME older than the threshold, aged by git blame.

    Only tracked source files are scanned, and only the first N oldest are
    reported, so a legacy backlog produces a bounded digest rather than a wall.
    """
    pat = re.compile(r"\b(TODO|FIXME|XXX)\b")
    candidates: list[tuple[str, int, str]] = []
    exts = {".py", ".lean", ".sh", ".yml", ".yaml", ".js", ".html", ".md"}
    for path in root.rglob("*"):
        if ".git/" in str(path) or not path.is_file() or path.suffix not in exts:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if not pat.search(text):
            continue
        rel = str(path.relative_to(root))
        blame = git(["blame", "-l", "--porcelain", "--", rel], root)
        linemap: dict[str, str] = {}
        cur_date = None
        cur_line = None
        for bl in blame.splitlines():
            if re.match(r"^[0-9a-f]{40} ", bl):
                cur_line = bl.split()[2] if len(bl.split()) > 2 else None
            elif bl.startswith("author-time "):
                cur_date = bl.split()[1]
            elif bl.startswith("\t") and cur_line:
                linemap[cur_line] = cur_date
                cur_line = None
        for i, line in enumerate(text.splitlines(), start=1):
            m = pat.search(line)
            if not m:
                continue
            ts = linemap.get(str(i))
            if not ts:
                continue
            age = (dt.datetime.now(dt.timezone.utc)
                   - dt.datetime.fromtimestamp(int(ts), dt.timezone.utc)).days
            if age >= TODO_MAX_AGE_DAYS:
                candidates.append((rel, age, f"{m.group(1)} at line {i}: {line.strip()[:90]}"))
    candidates.sort(key=lambda c: -c[1])
    seen, out = set(), []
    for rel, age, desc in candidates[:MAX_TODOS_REPORTED]:
        if rel in seen:
            continue
        seen.add(rel)
        out.append(Finding(
            "stale-todo", CATEGORY_BUGS,
            f"Stale marker in {rel} ({age}d old)",
            f"Oldest of this file's stale markers is {age} days old:\n\n    {desc}\n\n"
            f"Resolve it, or convert it to a filed issue and remove the marker.",
            rel))
    return out


def gate_entrypoint(root: Path) -> tuple[list[str], str] | None:
    """(command, label) for the repo's own gate/test runner, or None.

    Detected rather than assumed: the four repos in this family use different
    runners, and inventing a command that does not exist would make the check
    silently vacuous.
    """
    if (root / "tooling/gates/run_all.py").exists():
        return (["python3", "tooling/gates/run_all.py", "--json"], "tooling/gates/run_all.py")
    if (root / "tools/run_tests.sh").exists():
        return (["bash", "tools/run_tests.sh"], "tools/run_tests.sh")
    if (root / "tooling/pre_push_check.py").exists():
        return (["python3", "tooling/pre_push_check.py"], "tooling/pre_push_check.py")
    return None


def check_gate_health(root: Path) -> list[Finding]:
    """Run the repo's own runner; report only genuine failures.

    A gate that reports PASS while listing findings is the expected shape for
    this family -- those findings are planted fixtures proving the gate *can*
    fire (the "a check that cannot fail is not a check" rule). Reporting them as
    repo problems would be exactly wrong, so only FAIL/BROKEN and a non-zero
    exit are surfaced.
    """
    entry = gate_entrypoint(root)
    if not entry:
        return [Finding(
            "gate-health", CATEGORY_CATCHALL,
            "No gate/test runner detected",
            "No known gate runner found (`tooling/gates/run_all.py`, `tools/run_tests.sh`, "
            "`tooling/pre_push_check.py`). Either the repo has none, or it uses a name this "
            "auditor does not know. If the latter, extend `gate_entrypoint()`.",
            "gate-runner")]

    cmd, label = entry
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=1800)
    if proc.returncode == 0:
        return []

    tail = (proc.stdout + proc.stderr).strip().splitlines()[-40:]
    return [Finding(
        "gate-health", CATEGORY_BUGS,
        f"Gate runner failed: {label}",
        f"`{' '.join(cmd)}` exited {proc.returncode}.\n\n```\n"
        + "\n".join(tail) + "\n```\n\nThis is the repo's own gate suite; its failure is the "
        f"most load-bearing finding this audit can produce.",
        f"gate-runner:{label}")]


# A reference introduced by another repo's name is a cross-repo citation
# ("Maith `EXPERIMENT_MEASUREMENT.md`"), not a path this repo ever owned.
SIBLING_REPOS = ("Maith", "PleaNP", "ephapse", "Ephapse", "muse", "rubato", "HuB",
                 "mathlib", "Mathlib", "upstream", "sibling")


def _is_cross_repo(text: str, start: int) -> bool:
    """Cross-repo attribution, checked over a generous window.

    Citations are often several lines of prose away from the attribution: a
    sub-bullet list under ``**`lean/PleaNP/Circuits/` on `dev`** contains ...``
    names the sibling repo in a heading and then lists bare filenames for the
    next eight lines. A tight window misses that and produces a false positive,
    so the window reaches back well past the start of the current line.
    """
    line_start = text.rfind("\n", 0, start) + 1
    window = text[max(0, line_start - 900):start]
    return any(name in window for name in SIBLING_REPOS)


def _is_gitignored(root: Path, target: str) -> bool:
    """Paths this repo deliberately does not track.

    A doc that references ``runs/full_run_status.json`` is describing an artifact
    produced at run time and gitignored by design -- the correct thing to write,
    not drift. Reporting it would bury the real findings.
    """
    r = subprocess.run(["git", "check-ignore", "-q", "--", target], cwd=root)
    return r.returncode == 0


def check_dangling_doc_refs(root: Path) -> list[Finding]:
    """Backticked repo paths in docs that resolve nowhere.

    Three resolution attempts per reference -- repo-root, doc-relative, and
    docs-root-relative -- because a bare ``SANDBOX_BASELINE.md`` inside
    ``docs/reference/`` means the sibling file, not a root file.

    Two false-positive classes are suppressed deliberately, because a check that
    cries wolf gets ignored and is therefore worse than no check:

      * **cross-repo citations** -- ``Maith `EXPERIMENT_MEASUREMENT.md``` names a
        file in a *sibling* repo. It will never resolve here and is not drift.
      * **external / generated paths** -- absolute paths, URLs, and the
        ``NN_thing/NN_thing.py`` shape used by vendored doc examples.
    """
    ref = re.compile(r"`([A-Za-z0-9_./-]+\.(?:md|py|lean|sh|yml|yaml|json|toml|html))`")

    # Repo-wide basename index. A doc that says ``run_all.py`` inside a table
    # describing the gates directory is naming a real file whose location the
    # prose supplies; it is not a dangling path. Requiring a *path* to resolve
    # would make this check too noisy to survive, so a matching basename
    # anywhere in the tree counts as "this file exists".
    basenames = set()
    for p in root.rglob("*"):
        if ".git/" in str(p) or not p.is_file():
            continue
        basenames.add(p.name)

    findings, seen, seen_where = [], set(), {}
    docs = list(root.glob("docs/**/*.md")) + list(root.glob("*.md"))
    for doc in docs:
        if ".git/" in str(doc):
            continue
        rel_doc = str(doc.relative_to(root))
        try:
            text = doc.read_text(errors="replace")
        except OSError:
            continue
        for m in ref.finditer(text):
            target = m.group(1)
            if "<" in target or "*" in target or target.startswith(("/", "http")):
                continue
            if re.match(r"^\d{2}_", target):        # vendored numbered-dir examples
                continue
            if _is_cross_repo(text, m.start()):
                continue
            candidates = [root / target, doc.parent / target, root / "docs" / target]
            if any(c.exists() for c in candidates):
                continue
            if Path(target).name in basenames:      # loose basename reference
                continue
            if _is_gitignored(root, target):        # run-time artifact by design
                continue
            if target in seen:
                continue
            seen.add(target)
            seen_where[target] = rel_doc
            findings.append(target)
    if not findings:
        return []
    # One aggregate finding, not one per reference. Nineteen separate issues for
    # nineteen dead paths is noise a human will stop reading; one tracking issue
    # that lists the current set keeps the digest usable and gives dedup a single
    # stable signature to comment against as the set changes.
    shown = findings[:25]
    more = len(findings) - len(shown)
    body = [f"{len(findings)} backticked path reference(s) in `docs/` resolve to no "
            f"file anywhere in the repo. Each is either a rename/removal that was not "
            f"propagated, or an aspirational path that should be marked as such.", "",
            "| reference | cited in |", "|---|---|"]
    for target, rel_doc in sorted(seen_where.items()):
        body.append(f"| `{target}` | `{rel_doc}` |")
    if more > 0:
        body.append("")
        body.append(f"_{more} more not shown._")
    body.append("")
    body.append("Suggested resolution: fix or remove each reference, or mark the "
                "aspirational ones explicitly. Suppressed by design and not listed here: "
                "cross-repo citations, gitignored run-time artifacts, wildcards, and bare "
                "basenames that exist elsewhere in the tree.")
    return [Finding(
        "dangling-doc-ref", CATEGORY_ARCH,
        f"{len(findings)} dangling docs path reference(s)",
        "\n".join(body),
        "docs")]


COUNT_CLAIM = re.compile(
    r"\b(\d{1,4})\s+(?:gates?|checks?|suites?|tests?|ids?)\b", re.IGNORECASE)


def check_doc_count_drift(root: Path) -> list[Finding]:
    """'N gates/checks' claims in docs that disagree across documents.

    The spec calls out the "37 vs 38 vs 9 wired" class explicitly. This reports
    only disagreements in *prose* about a bare count; it does not attempt to
    derive ground truth, because for several of these repos the count is
    genuinely tiered and a single number may be correct in context.
    """
    claims: dict[str, dict[int, str]] = {}
    for doc in list(root.glob("docs/**/*.md")) + list(root.glob("*.md")):
        rel = str(doc.relative_to(root))
        try:
            text = doc.read_text(errors="replace")
        except OSError:
            continue
        for m in COUNT_CLAIM.finditer(text):
            n = int(m.group(1))
            kind = m.group(0).split()[-1].lower().rstrip("s")
            claims.setdefault(kind, {}).setdefault(n, rel)
    out = []
    for kind, bycount in claims.items():
        if len(bycount) < 2:
            continue
        listing = "; ".join(f"{n} cited in `{f}`" for n, f in sorted(bycount.items()))
        out.append(Finding(
            "doc-count-drift", CATEGORY_ARCH,
            f"Inconsistent {kind} count across docs",
            f"Docs cite differing {kind} counts: {listing}. Confirm which is current and "
            f"reconcile the rest — an inconsistent count is how a stale figure survives.",
            f"{kind}-count"))
    return out


def check_status_log_contract(root: Path) -> list[Finding]:
    """This repo's own status_log.jsonl must stay parseable for the dashboard."""
    path = root / STATUS_LOG
    if not path.exists():
        return []
    bad = []
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad.append(f"line {i}: not valid JSON")
            continue
        if not isinstance(obj, dict):
            bad.append(f"line {i}: not an object")
            continue
        if "timestamp" not in obj:
            bad.append(f"line {i}: missing timestamp")
        if "trl" in obj and not isinstance(obj["trl"], dict):
            bad.append(f"line {i}: trl is not an object")
    if not bad:
        return []
    return [Finding(
        "status-log-contract", CATEGORY_ARCH,
        "status_log.jsonl violates the documented schema",
        "The shared dashboard contract (PM_STATUS_FRAMEWORK.md) requires one JSON object "
        "per line with a `timestamp`. Problems found:\n\n"
        + "\n".join(f"  - {b}" for b in bad[:15]),
        STATUS_LOG)]


# --------------------------------------------------------------------------
# security & consistency checks
#
# These add the second half of the audit's remit: code-quality/security review and
# cross-file contradiction detection, rather than repo hygiene alone. Two design
# rules carry over from the existing checks unchanged, because they are what make
# an automated finding trustworthy:
#
#   * every finding is a *mechanical fact* -- no LLM, no judgement call;
#   * a check that cannot fire is worse than no check, so each ships a fixture
#     that makes it fail (see tooling/tests/test_auditor.py).
#
# The one network call (dependency advisories) is dependency-injectable so the
# tests stay offline, and it degrades to a *reported* skip rather than a silent
# pass: a check that stops running must not look like a clean repo.
# --------------------------------------------------------------------------

def _iter_scannable_files(root: Path):
    """Tracked files that are safe and cheap to read as text.

    Deliberately git-driven, not a filesystem walk: an untracked scratch file left
    by a local run is not what the repo publishes, and reporting it would be noise.
    """
    for rel in git(["ls-files"], root).splitlines():
        if not rel:
            continue
        if Path(rel).name in SECRET_EXCLUDE_NAMES:
            continue
        path = root / rel
        try:
            if not path.is_file() or path.stat().st_size > MAX_SCANNED_BYTES:
                continue
        except OSError:
            continue
        yield rel, path


def check_stale_owner_refs(root: Path) -> list[Finding]:
    """Retired account/repo slugs surviving outside the frozen record.

    This is the contradiction class the account rename created: the project moved
    from `allenpd728` to `philipdallen`, and a clone URL, `--repo` example, or
    prose sentence that still names the old slug tells a reader (or an agent
    following the docs) to use an address that no longer exists.

    `docs/decisions/` and `docs/history/` are excluded on purpose. Those files
    record the slug as it was at the time; rewriting them would make the record
    false, which is a worse defect than the stale reference. The check reports the
    live drift only.
    """
    hits: list[tuple[str, int, str]] = []
    for rel, path in _iter_scannable_files(root):
        if rel.startswith(STALE_OWNER_EXCLUDE):
            continue
        if path.name == "auditor.py":
            continue          # this file defines the slug list and explains the ban
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for slug in RETIRED_OWNER_SLUGS:
            if slug not in text:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if slug in line:
                    hits.append((rel, i, line.strip()[:120]))
    if not hits:
        return []
    by_file: dict[str, list[tuple[int, str]]] = {}
    for rel, i, line in hits:
        by_file.setdefault(rel, []).append((i, line))
    body = [
        f"{len(hits)} reference(s) to the retired account slug "
        f"{', '.join('`' + s + '`' for s in RETIRED_OWNER_SLUGS)} survive in files "
        f"that are not part of the frozen record.",
        "",
        "Each is a live contradiction: it tells a reader or an agent to use an "
        "address that no longer resolves. Frozen logs (`docs/decisions/`, "
        "`docs/history/`) are excluded by design and are not listed here -- they "
        "record the slug as it was, and rewriting them would make them false.",
        "",
        "| file | line | reference |",
        "|---|---|---|",
    ]
    for rel in sorted(by_file):
        for i, line in by_file[rel][:6]:
            body.append(f"| `{rel}` | {i} | `{line.replace('|', '\\|')[:110]}` |")
    return [Finding(
        "stale-owner-ref", CATEGORY_ARCH,
        f"{len(hits)} reference(s) to the retired account slug",
        "\n".join(body),
        "retired-slug")]


def check_committed_secrets(root: Path) -> list[Finding]:
    """Credential-shaped strings in files git tracks.

    High-confidence shapes only (see ``SECRET_PATTERNS``). A secret scanner that
    fires on prose, or on the example keys vendored into a lockfile, produces
    findings a human learns to skip -- and a skipped check is a dead check.

    The matched value is never printed. This issue is public, and echoing a live
    credential into it would complete the leak the check exists to catch.
    """
    findings: list[Finding] = []
    for rel, path in _iter_scannable_files(root):
        if rel.startswith("tooling/tests/") or rel.startswith("tools/tests/"):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for kind, rx in SECRET_PATTERNS:
            m = rx.search(text)
            if not m:
                continue
            line_no = text[:m.start()].count("\n") + 1
            findings.append(Finding(
                "committed-secret", CATEGORY_SECURITY,
                f"Possible committed credential ({kind}) in {rel}",
                f"A {kind} pattern matches at `{rel}` line {line_no}. The value is "
                f"deliberately not reproduced here -- this issue is public.\n\n"
                f"If it is live, **rotate it first**, then remove it from the working "
                f"tree. Note that removing the line does not remove it from history: "
                f"the commit that introduced it still contains it, so the credential "
                f"must be treated as compromised until rotated.",
                f"{rel}:{kind}"))
            if len(findings) >= MAX_SECRET_FINDINGS:
                return findings
    return findings


def _triggers(text: str) -> set[str]:
    """Trigger names from the workflow's `on:` block.

    The triggers are *indented* under `on:` (``on:\\n  push:\\n  pull_request:``),
    so a column-0 scan misses every one of them -- which silently disables the
    injection check. They are parsed as a block, and the inline forms
    (``on: push``, ``on: [push, pull_request]``) are handled too.

    Only the region before ``jobs:`` is considered, so an `on:`-shaped string
    inside a step body cannot be mistaken for a trigger.
    """
    head = text.split("\njobs:", 1)[0]
    triggers: set[str] = set()
    in_on = False
    for line in head.splitlines():
        if re.match(r"^on\s*:", line):
            in_on = True
            rest = line.split(":", 1)[1].strip()
            if rest:                                  # inline scalar or list
                triggers.update(re.findall(r"[A-Za-z_]+", rest))
            continue
        if not in_on:
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^[A-Za-z_]", line):             # column 0 -> block ended
            break
        m = re.match(r"^\s+(?:-\s*)?([a-z_]+)\s*:", line)
        if m:
            triggers.add(m.group(1))
    return triggers


def _run_blocks(text: str) -> list[str]:
    """The body of every ``run:`` step in a workflow.

    The injection check must look *only* here. ``${{ ... }}`` in an ``env:`` value
    or a ``with:`` argument is data passed to the process, not shell source, and
    that is the recommended fix -- flagging it would punish the correct pattern and
    bury the real finding.
    """
    lines = text.splitlines()
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        # Indent is measured from the `run` token, not the line start: a step is
        # `- run: ...` and its sibling keys (`env:`, `with:`) sit at the *same*
        # column as `run`. Measuring from the line start would make those siblings
        # look like block body and drag `env:` values into the injection scan.
        m = re.match(r"^(\s*(?:-\s*)?)run\s*:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        rest = m.group(2).strip()
        body: list[str] = []
        if rest and rest not in ("|", ">", "|-", ">-", "|+", ">+"):
            body.append(rest)                      # inline `run: cmd`
        i += 1
        while i < len(lines):                      # indented block form
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line)
            i += 1
        blocks.append("\n".join(body))
    return blocks


def check_workflow_hardening(root: Path) -> list[Finding]:
    """GitHub Actions workflows that are under-hardened.

    Three checks, all mechanical and all with a real exploitation story:

      * **no top-level `permissions:`** -- the workflow runs with the repository's
        *default* token scope. For repos whose default is read/write, any step
        (including one running a dependency's code) inherits write access. Declaring
        `permissions:` is the least-privilege fix and is free.
      * **write-capable trigger + untrusted interpolation into `run:`** -- the
        classic script-injection path. A PR title or branch name is attacker-chosen
        text; interpolating it into a shell command executes it.
      * **`checkout` of a PR head ref then `run:`** -- the `pull_request_target`
        anti-pattern, where a privileged workflow executes untrusted code.
    """
    wf_dir = root / WORKFLOW_DIR
    if not wf_dir.is_dir():
        return []
    out: list[Finding] = []
    for path in sorted(wf_dir.glob("*.y*ml")):
        rel = str(path.relative_to(root))
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        triggers = _triggers(text)
        has_perms = bool(TOP_LEVEL_PERMISSIONS_RE.search(text))
        write_trigger = sorted(t for t in triggers if t in WRITE_TRIGGERS)

        if not has_perms:
            out.append(Finding(
                "workflow-hardening", CATEGORY_SECURITY,
                f"Workflow has no top-level `permissions:`: {rel}",
                f"`{rel}` declares no top-level `permissions:` block, so it runs with "
                f"the repository's default token scope rather than the least privilege "
                f"it actually needs. If the repository default is read/write, every "
                f"step -- including one executing a third-party action -- inherits "
                f"write access.\n\nTriggers seen: "
                f"{', '.join('`' + t + '`' for t in sorted(triggers)) or '(none)'}.\n\n"
                f"Fix: add an explicit `permissions:` block (start from "
                f"`contents: read`) and grant only what the job needs. The `auditor` "
                f"workflow in this repo already does the right thing -- copy its shape.",
                f"{rel}:permissions"))

        if write_trigger:
            injected: list[str] = []
            for block in _run_blocks(text):
                injected.extend(UNTRUSTED_INTERP_RE.findall(block))
            if injected:
                examples = sorted(set(injected))
                out.append(Finding(
                    "workflow-hardening", CATEGORY_SECURITY,
                    f"Untrusted input interpolated into `run:` in workflow: {rel}",
                    f"`{rel}` uses the write-capable trigger(s) "
                    f"{', '.join('`' + t + '`' for t in write_trigger)} and interpolates "
                    f"attacker-influenced values directly into a shell command:\n\n"
                    + "\n".join(f"  - `{e}`" for e in examples[:8])
                    + "\n\nA PR title, branch name, or workflow input is text an outside "
                    f"contributor chooses. Substituted into a `run:` block it is shell "
                    f"source, i.e. code execution -- quoting does not help, because the "
                    f"substitution happens before the shell parses the line.\n\n"
                    f"Fix: pass it through `env:` and reference `\"$VAR\"` quoted, so the "
                    f"value is data rather than source. (This check only inspects `run:` "
                    f"blocks for exactly that reason -- `env:` and `with:` usages are the "
                    f"remedy, not a finding.)",
                    f"{rel}:interpolation"))

        if CHECKOUT_RE.search(text) and PR_HEAD_REF_RE.search(text):
            out.append(Finding(
                "workflow-hardening", CATEGORY_SECURITY,
                f"Privileged checkout of a PR head ref: {rel}",
                f"`{rel}` checks out a pull-request head ref by expression while "
                f"running on a trigger that carries a privileged token. This is the "
                f"`pull_request_target` anti-pattern: the workflow executes the "
                f"contributor's code with the base repository's credentials.\n\n"
                f"Fix: check out the base ref, or split the privileged step into a "
                f"separate `workflow_run` job that never executes PR code.",
                f"{rel}:pr-head-checkout"))
    return out


def parse_requirements(root: Path) -> list[tuple[str, str]]:
    """(name, version) for each pinned requirement, best-effort.

    Unpinned or environment-marker requirements are skipped rather than guessed at:
    a wrong version would produce a wrong advisory, which is worse than a gap.
    """
    path = root / REQUIREMENTS_FILE
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*([^\s;]+)", line)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def osv_query(packages: list[tuple[str, str]]) -> dict:
    """Query OSV.dev for advisories. Free, no auth, no GHAS entitlement.

    Chosen deliberately over the GitHub advisory APIs, which are entitlement-gated
    and returned 403 for these repos. OSV is a public API with a batch endpoint, so
    one request covers the whole file.
    """
    body = {"queries": [{"package": {"name": n, "ecosystem": OSV_ECOSYSTEM},
                         "version": v} for n, v in packages]}
    req = urllib.request.Request(
        OSV_API, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "repo-auditor"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode())


def check_dependency_advisories(root: Path, query=osv_query) -> list[Finding]:
    """Known advisories against pinned requirements, via OSV.dev.

    Three outcomes, and the distinction matters:

      * advisories found   -> one finding, listed by package and advisory id;
      * queried, none found -> silent (a clean result);
      * query unavailable  -> a *Catch-all* finding, because a check that silently
        stops running looks exactly like a clean repo, and that ambiguity is the
        failure this audit exists to remove.

    The network call is injected so the tests can pin all three paths offline.
    """
    packages = parse_requirements(root)
    if not packages:
        return []
    try:
        result = query(packages)
    except Exception as exc:                          # noqa: BLE001
        return [Finding(
            "dependency-advisory", CATEGORY_CATCHALL,
            "Dependency advisory lookup did not run",
            f"OSV.dev could not be queried (`{type(exc).__name__}: {exc}`). "
            f"{len(packages)} pinned requirement(s) were therefore **not** checked for "
            f"known advisories this run. This is reported rather than skipped silently: "
            f"an unavailable check and a clean result must not look the same.",
            "osv-query")]

    rows, details = [], []
    for (name, version), res in zip(packages, result.get("results", [])):
        vulns = res.get("vulns") or []
        if not vulns:
            continue
        ids = [v.get("id", "?") for v in vulns]
        rows.append(f"| `{name}=={version}` | {len(ids)} | {', '.join(ids[:6])} |")
        for v in vulns[:6]:
            details.append(f"  - **{v.get('id')}** — {name}=={version}: "
                           f"{(v.get('summary') or '').strip()[:200]}")
    if not rows:
        return []

    body = [
        f"{len(rows)} pinned requirement(s) have known advisories:",
        "",
        "| requirement | advisories | ids |",
        "|---|---|---|",
    ] + rows + ["", "Details:", ""] + details + [
        "",
        "Fix: bump to a release outside the affected ranges (each advisory's page "
        "on osv.dev lists them), or record why the finding is not reachable here. "
        "Source: the public OSV.dev advisory database.",
    ]
    return [Finding(
        "dependency-advisory", CATEGORY_SECURITY,
        f"{len(rows)} pinned requirement(s) with known advisories",
        "\n".join(body),
        REQUIREMENTS_FILE)]


REGISTRY = [
    check_committed_artifacts,
    check_stale_todos,
    check_gate_health,
    check_dangling_doc_refs,
    check_doc_count_drift,
    check_status_log_contract,
    check_stale_owner_refs,
    check_committed_secrets,
    check_workflow_hardening,
    check_dependency_advisories,
]


def run_checks(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for fn in REGISTRY:
        try:
            findings.extend(fn(root))
        except Exception as exc:                      # noqa: BLE001
            findings.append(Finding(
                "check-crashed", CATEGORY_CATCHALL,
                f"Audit check crashed: {fn.__name__}",
                f"The check raised `{type(exc).__name__}: {exc}`. The check needs fixing; "
                f"its coverage is currently absent from this audit.",
                fn.__name__))
    return findings


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

def load_state(root: Path) -> dict:
    path = root / STATE_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(root: Path, sha: str, when: str) -> None:
    path = root / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    state = load_state(root)
    state["last_audited_sha"] = sha
    state["last_audited_at"] = when
    state["last_audited_date"] = when[:10]
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# status log (carries trl/flow forward -- see docs/AUDITOR.md)
# --------------------------------------------------------------------------

def read_last_status_entry(root: Path) -> dict | None:
    path = root / STATUS_LOG
    if not path.exists():
        return None
    last = None
    for line in path.read_text().splitlines():
        if line.strip():
            last = line
    if not last:
        return None
    try:
        return json.loads(last)
    except json.JSONDecodeError:
        return None


def build_status_entry(root: Path, when: str, sha: str, proposed: int,
                       revised: int) -> dict:
    prev = read_last_status_entry(root) or {}
    entry: dict = {
        "timestamp": when,
        "notes": (f"audit {when[:10]} @ {sha[:7]}: {proposed} proposed, "
                  f"{revised} revise"),
    }
    # Carry the previous values forward verbatim. The dashboard reads `trl`
    # from the LAST entry, so omitting it would blank the TRL panel for every
    # viewer until the next scheduled sweep -- a real regression, not a no-op.
    for key in ("trl", "flow"):
        if key in prev:
            entry[key] = prev[key]
    return entry


def append_status_entry(root: Path, entry: dict) -> None:
    path = root / STATUS_LOG
    existing = path.read_text() if path.exists() else ""
    sep = "" if (not existing or existing.endswith("\n")) else "\n"
    with path.open("a") as fh:
        fh.write(sep + json.dumps(entry, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# GitHub output
# --------------------------------------------------------------------------

def ensure_labels(gh: GitHub, repo: str, dry: bool) -> None:
    specs = {
        LABEL_PROPOSED: ("1D76DB", "Auditor: new task proposed, held for review"),
        LABEL_REVISE: ("B60205", "Auditor: proposal to revise an existing task"),
        LABEL_HOLD: ("FBCA04", "Held for human review; not claimable"),
    }
    if dry:
        return
    try:
        existing = {l["name"] for l in gh.paged(f"/repos/{repo}/labels?per_page=100")}
    except urllib.error.HTTPError:
        existing = set()
    for name, (color, desc) in specs.items():
        if name in existing:
            continue
        try:
            gh.post(f"/repos/{repo}/labels", {"name": name, "color": color,
                                              "description": desc})
        except urllib.error.HTTPError as e:
            print(f"  warning: could not create label {name}: {e}", file=sys.stderr)


def open_issues(gh: GitHub, repo: str) -> list[dict]:
    raw = gh.paged(f"/repos/{repo}/issues?state=open&per_page=100")
    return [i for i in raw if "pull_request" not in i]


def find_existing(issues: list[dict], signature: str) -> dict | None:
    for i in issues:
        if signature.lower() in (i.get("title") or "").lower():
            return i
        if signature.lower() in (i.get("body") or "").lower():
            return i
    return None


def digest_title(when: str) -> str:
    return f"Auditor digest — {when[:10]}"


def build_digest_body(when: str, sha: str, commits: list[dict],
                      findings: list[Finding], opened: list[str],
                      revised: list[str]) -> str:
    lines = [
        f"Automated daily audit. Read-only pass over `{sha[:7]}`.",
        "",
        f"**Range:** {len(commits)} commit(s) since the previous successful run.",
        "",
    ]
    if commits:
        lines.append("| commit | date | subject |")
        lines.append("|---|---|---|")
        for c in commits[:25]:
            lines.append(f"| `{c['sha'][:7]}` | {c['date']} | {c['subject'][:90]} |")
        if len(commits) > 25:
            lines.append(f"| … | | _{len(commits) - 25} more_ |")
        lines.append("")

    by_cat: dict[str, list[Finding]] = {}
    for f in findings:
        by_cat.setdefault(f.category, []).append(f)

    lines.append("## Findings")
    lines.append("")
    if not findings:
        lines.append("Nothing flagged this run.")
    for cat in (CATEGORY_ARCH, CATEGORY_SECURITY, CATEGORY_BUGS, CATEGORY_CATCHALL):
        items = by_cat.get(cat)
        if not items:
            continue
        lines.append(f"### {cat}")
        lines.append("")
        for f in items:
            lines.append(f"- **{f.title}** — {f.body.splitlines()[0][:200]}")
        lines.append("")

    lines += ["## Issues raised", ""]
    if opened:
        lines += [f"- New proposal: {t}" for t in opened]
    if revised:
        lines += [f"- Revision requested: {t}" for t in revised]
    if not opened and not revised:
        lines.append("- None — every finding either already had an open issue or needed none.")

    lines += [
        "",
        "---",
        "",
        "Nothing here is actionable by agents. Proposals carry `on-hold`; the human moves "
        "them into the real pipeline by removing `on-hold` and adding the repo's normal "
        "claimable label. See `docs/AUDITOR.md`.",
    ]
    return "\n".join(lines)


def post_comment(gh: GitHub, repo: str, number: int, body: str) -> None:
    gh.post(f"/repos/{repo}/issues/{number}/comments", {"body": body})


def create_issue(gh: GitHub, repo: str, title: str, body: str,
                 labels: list[str]) -> dict:
    return gh.post(f"/repos/{repo}/issues",
                   {"title": title, "body": body, "labels": labels})


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Daily repo health & drift audit (read-only).")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--root", default=".", help="repo checkout root")
    ap.add_argument("--token-env", default="GITHUB_TOKEN")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true",
                    help="emit findings as a machine-readable JSON object on stdout")
    ap.add_argument("--force", action="store_true",
                    help="ignore the checkpoint (still dedups against open issues)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    token = os.environ.get(args.token_env) or None
    gh = GitHub(token)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    when = now.isoformat().replace("+00:00", "Z")

    sha = head_sha(root)
    if not sha:
        print("error: not a git checkout", file=sys.stderr)
        return 1

    state = load_state(root)
    last = state.get("last_audited_sha")

    # Idempotency: nothing moved since the last SUCCESSFUL run -> produce nothing.
    # A previous run that failed did not advance the checkpoint, so this retries
    # the same range rather than skipping it.
    if last == sha and not args.force:
        print(f"no new commits since last audit ({sha[:7]}); nothing to do")
        return 0

    commits = commits_between(root, last or "", sha)
    findings = run_checks(root)

    by_cat: dict[str, int] = {}
    for f in findings:
        by_cat[f.category] = by_cat.get(f.category, 0) + 1

    # --json is a read-only inspection mode: it emits the same findings the run
    # would act on, and deliberately never writes (no issues, no labels, no status
    # line, no checkpoint), so it is always safe to call from a tool or an agent.
    if args.json:
        print(json.dumps({
            "sha": sha,
            "audited_at": when,
            "commits": len(commits),
            "finding_count": len(findings),
            "findings": [
                {"check": f.check, "category": f.category, "signature": f.signature(),
                 "title": f.title, "subject": f.subject}
                for f in findings
            ],
        }, indent=2, sort_keys=True))
        return 0

    print(f"audit {sha[:7]}: {len(commits)} commit(s), {len(findings)} finding(s) {by_cat}")

    if args.dry_run:
        for f in findings:
            print(f"  [{f.check}] {f.title}")
        print("(dry-run: no issues, comments, labels, or status-log entries written)")
        return 0

    # All writes happen only after every check has completed, so a mid-run crash
    # leaves no half-written output.
    ensure_labels(gh, args.repo, args.dry_run)
    issues = open_issues(gh, args.repo)

    opened: list[str] = []
    revised: list[str] = []

    for f in findings:
        sig = f.signature()
        existing = find_existing(issues, sig)
        if existing:
            # Dedup: same finding already tracked -> add information, never a twin.
            post_comment(gh, args.repo, existing["number"],
                         f"Auditor re-observed this on `{sha[:7]}` ({when[:10]}).\n\n{f.body}")
            continue
        body = (
            f"{f.body}\n\n"
            f"---\n\n"
            f"_Raised by the daily auditor on `{sha[:7]}` ({when[:10]}). "
            f"Held for human review: this issue is **not** claimable until the human removes "
            f"`{LABEL_HOLD}` and adds whatever status label this protocol uses._"
        )
        created = create_issue(gh, args.repo, sig, body,
                               [LABEL_PROPOSED, LABEL_HOLD])
        opened.append(created["html_url"])
        issues.append(created)

    # Digest: one running issue per day, replaced if it already exists.
    title = digest_title(when)
    dbody = build_digest_body(when, sha, commits, findings, opened, revised)
    existing_digest = find_existing(issues, title)
    if existing_digest:
        post_comment(gh, args.repo, existing_digest["number"],
                     f"Re-run for `{sha[:7]}`.\n\n{dbody}")
    else:
        create_issue(gh, args.repo, title, dbody, [LABEL_HOLD])

    append_status_entry(root, build_status_entry(root, when, sha, len(opened), len(revised)))
    save_state(root, sha, when)
    print(f"done: {len(opened)} proposal(s), {len(revised)} revision(s); checkpoint -> {sha[:7]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())