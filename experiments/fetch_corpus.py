"""Fetch the paired cross-domain background corpus.

Reusable artifact for issues #6, #7, #3 (and #5 used an equivalent inline
version). Checked in rather than kept in /tmp, because /tmp does not survive
between sessions and every experiment below needs the same corpus defined the
same way.

Two hard-won constraints, both from executing against the live API:

1. The datasets-server `/rows` endpoint **hard-caps at 100 rows per request**
   (HTTP 422 above that). Asking for 1000 fails; hammering it yields HTTP 429
   and backoff does not always clear it. Pace at 100 with a delay.
2. `codeparrot-clean` returns **whole source files** (0.9k-100k+ chars), so a
   passage-length filter rejects all of them. They must be split at line
   boundaries to match the prose side's passage length.

Writes `Corpus/paired.json` (gitignored). Run: `python3 experiments/fetch_corpus.py`

**Model:** n/a (corpus preparation; no model is loaded).
**Inputs:** Salesforce/wikitext (wikitext-2-raw-v1) and
  codeparrot/codeparrot-clean-valid, via the HF datasets-server API.
**Question:** produce N paired passages per domain of comparable length, for
  use as the background corpus in cross-domain co-activation experiments.
**Issue:** #6 (run 20260919-0213-tsm5); shared by #3, #4, #7.

Infrastructure/verification task — no null model applies (see
experiments/README.md exemption).
"""
import json
import os
import time
import urllib.request

N_PAIRED = 1500
MAX_LEN = 100          # server-enforced cap
DELAY = 1.5
TARGET_LO, TARGET_HI = 80, 400

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "Corpus")
OUT = os.path.join(OUT_DIR, "paired.json")


def fetch(dataset, config, split, offset, length, tries=6):
    url = (f"https://datasets-server.huggingface.co/rows?dataset={dataset}"
           f"&config={config}&split={split}&offset={offset}&length={length}")
    for t in range(tries):
        try:
            r = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "ephapse-research/0.1",
            })
            with urllib.request.urlopen(r, timeout=90) as x:
                return json.load(x)["rows"]
        except urllib.error.HTTPError as e:
            if e.code == 422:
                raise                       # hard error; retrying will not help
            wait = 4 * (2 ** t)
            print(f"      retry {t + 1}/{tries} in {wait}s (HTTP {e.code})")
            time.sleep(wait)
        except Exception as e:
            wait = 4 * (2 ** t)
            print(f"      retry {t + 1}/{tries} in {wait}s ({type(e).__name__})")
            time.sleep(wait)
    raise RuntimeError(f"fetch failed: {dataset} offset={offset}")


def collect_prose(want):
    out, off = [], 0
    while len(out) < want and off < 12000:
        rows = fetch("Salesforce/wikitext", "wikitext-2-raw-v1", "train",
                     off, MAX_LEN)
        if not rows:
            break
        for r in rows:
            t = (r["row"].get("text") or "").strip()
            if TARGET_LO <= len(t) <= TARGET_HI:
                out.append(t)
        off += len(rows)
        time.sleep(DELAY)
    return out[:want]


def chunk_code(text, lo=TARGET_LO, hi=TARGET_HI):
    """Split a source file into passages at line boundaries."""
    chunks, cur = [], ""
    for line in text.splitlines(keepends=True):
        if len(cur) + len(line) > hi and len(cur) >= lo:
            chunks.append(cur.strip())
            cur = ""
        cur += line
        if len(cur) > hi * 3:               # pathological long line
            chunks.append(cur[:hi].strip())
            cur = cur[hi:]
    if lo <= len(cur) <= hi * 2:
        chunks.append(cur.strip())
    return [c for c in chunks if lo <= len(c) <= hi]


def collect_code(want):
    out, off = [], 0
    while len(out) < want and off < 4000:
        rows = fetch("codeparrot/codeparrot-clean-valid", "default", "train",
                     off, MAX_LEN)
        if not rows:
            break
        for r in rows:
            out.extend(chunk_code(r["row"].get("content") or ""))
            if len(out) >= want * 2:
                break
        off += len(rows)
        print(f"      codeparrot: {len(out)} chunks (offset {off})")
        time.sleep(DELAY)
    return out[:want]


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT):
        with open(OUT) as f:
            c = json.load(f)
        if len(c.get("A", [])) >= 500 and len(c.get("B", [])) >= 500:
            print(f"corpus OK: A={len(c['A'])} B={len(c['B'])} -> {OUT}")
            raise SystemExit(0)
        print("cache incomplete; refetching")

    print("fetching prose (wikitext-2-raw-v1)...")
    a = collect_prose(N_PAIRED)
    print(f"  -> {len(a)} prose passages")

    print("fetching + chunking code (codeparrot-clean-valid)...")
    b = collect_code(N_PAIRED)
    print(f"  -> {len(b)} code chunks")

    if len(a) < 500 or len(b) < 500:
        raise SystemExit(f"insufficient corpus: prose={len(a)} code={len(b)}")

    n = min(len(a), len(b))
    corpus = {"A": a[:n], "B": b[:n],
              "meta": {"A_source": "Salesforce/wikitext wikitext-2-raw-v1",
                       "B_source": "codeparrot/codeparrot-clean-valid (line-chunked)",
                       "A_domain": "english_prose", "B_domain": "python_code",
                       "paired_n": n, "length_range": [TARGET_LO, TARGET_HI]}}
    with open(OUT, "w") as f:
        json.dump(corpus, f)
    print(f"wrote {OUT}: {n} paired passages/domain")
    print(f"  A[0] ({len(corpus['A'][0])} chars): {corpus['A'][0][:60]!r}")
    print(f"  B[0] ({len(corpus['B'][0])} chars): {corpus['B'][0][:60]!r}")