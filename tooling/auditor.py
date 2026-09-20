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
    tokens, cannot hallucinate, and is safe to re-trigger.

Design note: findings are computed in full BEFORE anything is written, and the
GitHub writes only begin once every check has completed. That gives the
"either complete the run's output or produce nothing" property required by the
spec for the common failure mode (a check crashing mid-run).

Usage:
    python3 tooling/auditor.py --repo allenpd728/Maith --dry-run
    python3 tooling/auditor.py --repo allenpd728/Maith
    python3 tooling/auditor.py --repo allenpd728/Maith --force   # ignore checkpoint

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
CATEGORY_CATCHALL = "Catch-all"


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
SIBLING_REPOS = ("Maith", "PleaNP", "ephapse", "Ephapse", "muse", "HuB",
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


REGISTRY = [
    check_committed_artifacts,
    check_stale_todos,
    check_gate_health,
    check_dangling_doc_refs,
    check_doc_count_drift,
    check_status_log_contract,
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
    for cat in (CATEGORY_ARCH, CATEGORY_BUGS, CATEGORY_CATCHALL):
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