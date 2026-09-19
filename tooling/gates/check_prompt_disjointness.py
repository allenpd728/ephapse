#!/usr/bin/env python3
"""G-P2, G-P4 — prompt-set disjointness (issue #14).

| ID   | Check |
|------|-------|
| G-P2 | Zero shared tokens, verified **mechanically on tokenizer IDs** — the intersection size and contents are recorded |
| G-P4 | Split disjointness — no prompt string appears in both sets |

Two entry points:

    python3 tooling/gates/check_prompt_disjointness.py set_a.txt set_b.txt   # CLI
    from check_prompt_disjointness import check_disjointness                 # library

The library form matters: `docs/reference/TEST_VALIDATION_SPEC.md` §6 requires
the control to be recordable, so an experiment script calls this and writes the
result into `findings.jsonl`'s `paraphrase_controls` / `input_disjointness`
rather than restating a prose claim.

WHY IDS, NOT STRINGS (the whole point of G-P2)

String matching is not the check, in **both** directions. Measured on
`pythia-70m-deduped`'s tokenizer (the DEC-014 target):

  * **Different strings, no shared ID** — a substring test would fire, the ID
    test correctly does not:
        `"cat"` -> [8076]      `"cats"`    -> [38718]   shared: none
        `"run"` -> [6321]      `"running"` -> [24220]   shared: none
        `"seven"` -> [23587]   `"seventeen"` -> [339, 2254, 9673]   shared: none
    `"seven"` is a substring of `"seventeen"` and they share nothing.

  * **Different strings, shared ID** — a string test would miss it, the ID test
    catches it:
        `"unhappy"` -> [328, 42256]   `"happy"` -> [42256]   shared: [42256]

So a claim of "zero shared lexical items" is only a measurement once it is on
IDs. Note the issue text's own example, `"Paris"`/`"paris"` as *"different
strings with identical token IDs"*, is **wrong for this tokenizer** — they are
[36062] and [1148, 261], sharing nothing. The verified examples above are used
instead. Recorded because repeating an unverified pair as the docstring's
illustration is the same defect class as the claim the gate exists to check.

TIER (spec §10 Q2, resolved here)

G-P2 needs the target tokenizer, which is a download — but **not the model**, and
measured, tokenization works with `transformers` alone (no torch, no
TransformerLens). The resolution is therefore:

  * The **CLI** path takes a `--tokenizer` name and loads it live. That is a
    network read and does not belong in tier-0 CI.
  * The **library** path accepts pre-computed `set[int]` ID sets, so a gate
    fixture can exercise the full comparison with **no download at all** — which
    is what makes this registerable in `run_all.py` as tier 0.
  * A prompt set may also ship a committed `*.tokenids.json` alongside it; when
    present, the live tokenizer is not needed and the comparison runs offline.
    That is the "re-verify only when the prompts change" option the spec floated.

Cost of the choice, stated: the registry fixture proves the *comparison logic*,
not that any real prompt set is disjoint. Verifying a real pair needs a live
tokenizer and is done explicitly, with the numbers pasted into the done comment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from run_all import Gate, register           # noqa: E402

DEFAULT_TOKENIZER = "EleutherAI/pythia-70m-deduped"


def _split_prompts(text: str) -> list[str]:
    """One prompt per line; blank lines and `#` comments ignored."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def load_prompt_sets(path_a: Path, path_b: Path) -> tuple[list[str], list[str]]:
    return _split_prompts(path_a.read_text(encoding="utf-8")), \
           _split_prompts(path_b.read_text(encoding="utf-8"))


def check_disjointness(
    prompts_a: list[str],
    prompts_b: list[str],
    ids_a: set[int] | None = None,
    ids_b: set[int] | None = None,
    allow_token_ids: set[int] | None = None,
    allow_shared_prompts: bool = False,
) -> dict:
    """Compare two prompt sets. Returns a result dict; `findings` empty = pass.

    Pure function of its arguments: pass pre-computed `ids_a`/`ids_b` and no
    tokenizer is ever loaded, which is how the tier-0 fixture exercises it.
    """
    findings: list[str] = []

    # ---- G-P4: no prompt string appears in both sets ----------------------
    set_a, set_b = set(prompts_a), set(prompts_b)
    shared_prompts = sorted(set_a & set_b)
    if shared_prompts and not allow_shared_prompts:
        findings.append(
            f"G-P4: {len(shared_prompts)} prompt(s) appear in BOTH sets — a "
            f"split must be disjoint. e.g. {shared_prompts[0][:60]!r}")

    # ---- G-P2: token-ID intersection --------------------------------------
    if ids_a is None or ids_b is None:
        return {
            "ok": False, "findings": findings, "token_ids": None,
            "reason": "no token-ID sets supplied (needs a live tokenizer or a "
                      "committed *.tokenids.json)",
        }

    allowed = allow_token_ids or set()
    shared_ids = sorted(ids_a & ids_b)
    blocking = [i for i in shared_ids if i not in allowed]
    if blocking:
        findings.append(
            f"G-P2: {len(blocking)} shared token id(s) across the two sets — "
            f"the paraphrase control requires ZERO. ids={blocking[:20]}"
            + (" ..." if len(blocking) > 20 else ""))

    return {
        "ok": not findings,
        "findings": findings,
        "token_ids": {
            "n_a": len(ids_a), "n_b": len(ids_b),
            "n_shared": len(shared_ids),
            "shared_ids": shared_ids[:50],
            "n_allowed_exceptions": len(shared_ids) - len(blocking),
        },
        "n_shared_prompts": len(shared_prompts),
    }


def token_ids_for(prompts: list[str], tokenizer_name: str = DEFAULT_TOKENIZER) -> set[int]:
    """Live tokenizer read. Imports lazily so the tier-0 path never needs it."""
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(tokenizer_name)
    ids: set[int] = set()
    for p in prompts:
        ids.update(tok.encode(p, add_special_tokens=False))
    return ids


def load_tokenids_sidecar(prompts_path: Path) -> set[int] | None:
    """Read `<name>.tokenids.json` beside a prompt file, if committed."""
    sidecar = prompts_path.with_suffix(".tokenids.json")
    if not sidecar.exists():
        return None
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return set(data["ids"]) if "ids" in data else set(data)


# ------------------------------------------------------------------ gate hook
FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures" / "prompt_sets"


def check_fixture_dir(path: Path) -> list[str]:
    """Gate hook: the fixture tree carries pre-computed ids, so no download.

    Layout:
        <dir>/a.txt, <dir>/b.txt          the prompt sets
        <dir>/ids_a.json, <dir>/ids_b.json  their token-ID sets
    """
    base = path if path.is_dir() else path.parent
    pa, pb = base / "a.txt", base / "b.txt"
    ia, ib = base / "ids_a.json", base / "ids_b.json"
    if not (pa.exists() and pb.exists()):
        return [f"{base.name}: fixture needs a.txt and b.txt"]
    prompts_a, prompts_b = load_prompt_sets(pa, pb)
    ids_a = set(json.loads(ia.read_text())) if ia.exists() else None
    ids_b = set(json.loads(ib.read_text())) if ib.exists() else None
    r = check_disjointness(prompts_a, prompts_b, ids_a, ids_b)
    return r["findings"]


register(Gate(
    id="G-P2",
    name="prompt-set token disjointness",
    tier=0,
    check=check_fixture_dir,
    clean_fixture="prompt_sets/disjoint",
    failing_fixture="prompt_sets/shared_token",
    traces_to="DEC-011; spec §3 (G-P2, G-P4)",
    description="Two prompt sets share zero tokenizer ids and no prompt "
                "string. Compared on ids, not strings.",
))


# ------------------------------------------------------- direct entry point
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="prompt-set disjointness (G-P2/G-P4)")
    ap.add_argument("set_a", type=Path)
    ap.add_argument("set_b", type=Path)
    ap.add_argument("--tokenizer", default=DEFAULT_TOKENIZER)
    ap.add_argument("--allow-id", type=int, action="append", default=[],
                    help="token id permitted to appear in both sets")
    ap.add_argument("--allow-shared-prompts", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    prompts_a, prompts_b = load_prompt_sets(args.set_a, args.set_b)
    ids_a = load_tokenids_sidecar(args.set_a)
    ids_b = load_tokenids_sidecar(args.set_b)
    source = "committed *.tokenids.json"
    if ids_a is None or ids_b is None:
        print(f"tokenizing live with {args.tokenizer} "
              f"(no committed tokenids sidecar)", file=sys.stderr)
        ids_a = token_ids_for(prompts_a, args.tokenizer)
        ids_b = token_ids_for(prompts_b, args.tokenizer)
        source = f"live tokenizer {args.tokenizer}"

    r = check_disjointness(prompts_a, prompts_b, ids_a, ids_b,
                           allow_token_ids=set(args.allow_id),
                           allow_shared_prompts=args.allow_shared_prompts)
    if args.json:
        print(json.dumps({**r, "source": source}, indent=2))
    else:
        t = r["token_ids"] or {}
        print(f"G-P2/G-P4 prompt-set disjointness ({source})")
        print("=" * 70)
        print(f"  set A: {len(prompts_a)} prompt(s), {t.get('n_a', '?')} distinct token ids")
        print(f"  set B: {len(prompts_b)} prompt(s), {t.get('n_b', '?')} distinct token ids")
        print(f"  shared token ids : {t.get('n_shared', '?')}")
        if t.get("shared_ids"):
            print(f"    ids present in both: {t['shared_ids']}")
        print(f"  shared prompts   : {r['n_shared_prompts']}")
        print("-" * 70)
        for f in r["findings"]:
            print(f"  - {f}")
        print("PASS" if r["ok"] else "FAIL")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())