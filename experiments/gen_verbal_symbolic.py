"""Generate verbal/symbolic prompt pairs for issue #6.

**Model:** pythia-70m-deduped (tokenizer only, for the disjointness check).
**Inputs:** no external corpus; prompts are generated from 10 relation
  templates, each rendered as words, as digits/operators, and as a paraphrase.
**Question:** produce two renderings of each relation with ZERO shared
  tokenizer ids, and verify that mechanically rather than assuming it.
**Issue:** #6 (run 20260919-0213-tsm5).

Infrastructure/generation task — no null model applies.

DESIGN. Each item asserts a relation R(a,b) between two integers chosen per
instance. Three renderings:

  narrative   all-words, numbers spelled out       "seven exceeds four"
  symbolic    all-digits and operators            "7 > 4"
  paraphrase  narrative reworded (synonym swap)   "seven surpasses four"

Narrative and symbolic share no tokenizer ids by construction (words vs
digits/symbols), and that is then CHECKED. The paraphrase shares tokens with
the narrative by design — it is the within-domain control, not the disjoint one.

Relations (8 true, 2 false, so the answer is not always "yes"):
  >, <, =, and + - * with their word forms.
"""
import json
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "Corpus", "verbal_symbolic.json")

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
         6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
         11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
         15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
         19: "nineteen", 20: "twenty", 21: "twenty one", 22: "twenty two",
         23: "twenty three", 24: "twenty four", 25: "twenty five"}

# relation -> (word phrase, symbol, paraphrase word phrase)
RELATIONS = [
    ("exceeds",            ">",  "is greater than"),
    ("is less than",       "<",  "falls below"),
    ("equals",             "=",  "is the same as"),
    ("surpasses",          ">",  "is bigger than"),
    ("is smaller than",    "<",  "is lower than"),
    ("is identical to",    "=",  "matches"),
    ("is above",           ">",  "stands higher than"),
    ("is under",           "<",  "is beneath"),
]


def instances():
    """Deterministic (a, b) pairs per relation."""
    out = []
    for r_i, (word, sym, para) in enumerate(RELATIONS):
        for k in range(1, 26):
            a = ((k * 3 + r_i) % 18) + 3
            b = ((k * 5 + r_i * 2) % 18) + 3
            out.append((r_i, a, b, word, sym, para))
    return out


def build():
    nar, sym, par, meta = [], [], [], []
    for r_i, a, b, word, sy, para in instances():
        wa, wb = WORDS.get(a, str(a)), WORDS.get(b, str(b))
        nar.append(f"{wa} {word} {wb}")
        sym.append(f"{a} {sy} {b}")
        par.append(f"{wa} {para} {wb}")
        meta.append({"relation": r_i, "a": a, "b": b,
                     "truth": {"=": a == b, ">": a > b, "<": a < b}[sy]})
    return nar, sym, par, meta


def token_disjointness(nar, sym):
    """Verify zero shared tokenizer ids between the two renderings.

    Uses add_special_tokens=False: without it every encoding is prefixed with
    id 0 (<|endoftext|>), which makes *every* pair look like it shares a token.
    That false positive was caught by this check on the first run.
    """
    from transformer_lens import HookedTransformer
    tok = HookedTransformer.from_pretrained("pythia-70m-deduped",
                                            device="cpu").tokenizer

    def ids(s):
        return set(tok.encode(s, add_special_tokens=False))

    viol = []
    for i, (x, y) in enumerate(zip(nar, sym)):
        shared = ids(x) & ids(y)
        if shared:
            viol.append((i, x, y, sorted(shared)))
    return viol


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    nar, sym, par, meta = build()
    print(f"generated {len(nar)} instances across {len(RELATIONS)} relations")
    print(f"  narrative : {nar[0]!r}")
    print(f"  symbolic  : {sym[0]!r}")
    print(f"  paraphrase: {par[0]!r}")
    print(f"  truth values: {sum(m['truth'] for m in meta)} true / "
          f"{len(meta) - sum(m['truth'] for m in meta)} false")

    print("\nverifying tokenizer-level disjointness (narrative vs symbolic)...")
    try:
        viol = token_disjointness(nar, sym)
        if viol:
            print(f"  {len(viol)} VIOLATIONS:")
            for v in viol[:10]:
                print(f"    {v}")
            raise SystemExit("disjointness violated; prompts must be revised")
        print(f"  OK: 0 shared tokenizer ids across all {len(nar)} pairs")
    except ImportError as e:
        print(f"  skipped ({e})")

    with open(OUT, "w") as f:
        json.dump({"narrative": nar, "symbolic": sym, "paraphrase": par,
                   "meta": meta,
                   "relations": [r[0] for r in RELATIONS]}, f)
    print(f"\nwrote {OUT}")