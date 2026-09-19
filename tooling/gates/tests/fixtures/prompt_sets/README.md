# prompt-set disjointness fixtures (G-P2, G-P4)

Each directory holds a pair of prompt sets and their **pre-computed tokenizer
ID sets**, so the tier-0 gate exercises the comparison with no network access
and no model — `ids_a.json` / `ids_b.json` are the same numbers
`transformers` would return for `a.txt` / `b.txt` on the DEC-014 target
tokenizer (`EleutherAI/pythia-70m-deduped`).

Regenerate after changing any prompt text:

```python
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("EleutherAI/pythia-70m-deduped")
ids = sorted({i for p in prompts for i in tok.encode(p, add_special_tokens=False)})
```

| Directory | Behaviour | Why this case |
|---|---|---|
| `disjoint/` | **PASS** — zero shared ids, zero shared prompts | The clean direction. Vocabulary chosen to avoid the usual leaks (articles, punctuation). |
| `shared_token/` | **FIRE (G-P2)** — one shared id | The near miss. Both sets are otherwise disjoint; `unhappy` = `[328, 42256]` and `happy` = `[42256]` leak id 42256. A substring check would **not** see this, and neither would a claim of "unrelated topics". |
| `shared_prompt/` | **FIRE (G-P4)** — one prompt string in both sets | Split disjointness, independent of tokenization. Also leaks ids, so it fires both gates. |

## Why `unhappy` / `happy` is the right near miss

It is the case that shows why the check is on IDs rather than strings: the two
strings do **not** contain one another, and they share a token. The mirror case —
`seven` is a substring of `seventeen` yet they share **no** ids — is asserted in
`tests/test_gates.py` so the gate is shown to be right in both directions.

## Note on the target tokenizer's behaviour

The issue text that specified this gate gave `Paris`/`paris` as an example of
"different strings, identical token ids". Measured on the target tokenizer they
are `[36062]` and `[1148, 261]` — sharing nothing — so that example does not hold
and is not used. The verified pairs above are.