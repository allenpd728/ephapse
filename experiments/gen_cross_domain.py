"""Generate two lexically-disjoint prompt sets for issue #3 (cross-domain probe).

**Model:** pythia-70m-deduped (tokenizer only, for the disjointness check).
**Inputs:** no external corpus; passages are generated from disjoint
  domain vocabularies (cooking vs astronomy).
**Question:** produce two passage sets from unrelated domains that share ZERO
  tokenizer ids, and verify that mechanically rather than assuming it.
**Issue:** #3 (run 20260919-0229-to3m).

Infrastructure/generation task - no null model applies.

DESIGN. Passages are built by combining a domain-specific vocabulary with a
small set of sentence frames whose *function words* are also domain-specific,
so the two sets are token-disjoint by construction. Disjointness is then
CHECKED, not assumed (DEC-011; #6's generator does the same).

Both sets target ~30 tokens per passage, because #6 measured that usable
features rise 541 (5 tok) -> 1188 (31 tok) with passage-length context
(decisions LOG DEC-023).
"""
import json
import os
import random

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "Corpus", "cross_domain.json")
N_PER_DOMAIN = 120
SEED = 11

# Disjoint vocabularies. Function words are also kept disjoint between the two
# frames below so that no token is shared across the sets.
COOK_NOUN = ["pot", "pan", "skillet", "oven", "bowl", "whisk", "ladle",
             "garlic", "onion", "basil", "thyme", "rosemary", "broth",
             "dough", "flour", "butter", "olive", "pepper", "carrot",
             "potato", "tomato", "sauce", "soup", "stew", "batter",
             "yeast", "crust", "plate", "spoon", "knife", "recipe",
             "kitchen", "meal", "dish", "aroma", "steam", "flame"]
COOK_VERB = ["simmer", "saute", "knead", "roast", "bake", "boil", "chop",
             "stir", "taste", "season", "whisk", "ladle", "fold", "sear",
             "braise", "blend"]
COOK_ADJ = ["warm", "golden", "tender", "savory", "fresh", "hearty",
            "crispy", "smooth", "rich", "gentle"]

ASTRO_NOUN = ["nebula", "quasar", "pulsar", "orbit", "telescope", "galaxy",
              "comet", "asteroid", "photon", "redshift", "parallax",
              "spectrum", "magnitude", "supernova", "cluster", "void",
              "corona", "photosphere", "magnetar", "eclipse", "transit",
              "parsec", "observatory", "aperture", "wavelength", "infrared",
              "ultraviolet", "emission", "luminosity", "metallicity",
              "dwarf", "remnant", "debris", "plasma", "baryon", "cosmology"]
ASTRO_VERB = ["orbit", "rotate", "collapse", "radiate", "observe", "detect",
              "measure", "drift", "flare", "eclipse", "accrete", "scatter",
              "illuminate", "propagate", "redden", "disperse"]
ASTRO_ADJ = ["distant", "faint", "stellar", "galactic", "cosmic", "dense",
             "cold", "hot", "spiral", "elliptical"]


def cook_passage(rng):
    # glue tokens: "A" and "," only
    return ("A {adj} {n1} , {n2} {v1} , the {adj2} {n3} {v2} , "
            "{n4} {v3} , {n5} {n6}").format(
        adj=rng.choice(COOK_ADJ), n1=rng.choice(COOK_NOUN),
        n2=rng.choice(COOK_NOUN), v1=rng.choice(COOK_VERB),
        adj2=rng.choice(COOK_ADJ), n3=rng.choice(COOK_NOUN),
        v2=rng.choice(COOK_VERB), n4=rng.choice(COOK_NOUN),
        v3=rng.choice(COOK_VERB), n5=rng.choice(COOK_NOUN),
        n6=rng.choice(COOK_NOUN))


def astro_passage(rng):
    # glue tokens: ":" ";" "->" "(" ")" only - disjoint from cooking's glue
    return ("{n1} : {adj} {n2} ; {n3} {v1} -> {adj2} {n4} ; "
            "{n5} {v2} ( {n6} )").format(
        n1=rng.choice(ASTRO_NOUN), adj=rng.choice(ASTRO_ADJ),
        n2=rng.choice(ASTRO_NOUN), n3=rng.choice(ASTRO_NOUN),
        v1=rng.choice(ASTRO_VERB), adj2=rng.choice(ASTRO_ADJ),
        n4=rng.choice(ASTRO_NOUN), n5=rng.choice(ASTRO_NOUN),
        v2=rng.choice(ASTRO_VERB), n6=rng.choice(ASTRO_NOUN))


def token_disjointness(a, b, tok):
    def ids(s):
        return set(tok.encode(s, add_special_tokens=False))
    viol = []
    for i, (x, y) in enumerate(zip(a, b)):
        shared = ids(x) & ids(y)
        if shared:
            viol.append((i, sorted(shared), tok.convert_ids_to_tokens(sorted(shared))))
    return viol


def main():
    from transformer_lens import HookedTransformer

    rng = random.Random(SEED)
    a = [cook_passage(rng) for _ in range(N_PER_DOMAIN)]
    b = [astro_passage(rng) for _ in range(N_PER_DOMAIN)]

    tok = HookedTransformer.from_pretrained("pythia-70m-deduped",
                                            device="cpu").tokenizer
    la = [len(tok.encode(t, add_special_tokens=False)) for t in a]
    lb = [len(tok.encode(t, add_special_tokens=False)) for t in b]
    print(f"generated {len(a)} cooking / {len(b)} astronomy passages")
    print(f"  median tokens: cooking {sorted(la)[len(la)//2]}  astronomy {sorted(lb)[len(lb)//2]}")
    print(f"  example cooking  : {a[0]}")
    print(f"  example astronomy: {b[0]}")

    print("\nverifying tokenizer-level disjointness (cooking vs astronomy)...")
    viol = token_disjointness(a, b, tok)
    if viol:
        print(f"  {len(viol)} VIOLATIONS (showing 5):")
        for v in viol[:5]:
            print(f"    {v}")
        raise SystemExit("disjointness violated; vocabulary must be revised")
    print(f"  OK: 0 shared tokenizer ids across all {len(a)} pairs")

    with open(OUT, "w") as f:
        json.dump({"cooking": a, "astronomy": b,
                   "meta": {"seed": SEED, "n_per_domain": N_PER_DOMAIN,
                            "median_tokens": [sorted(la)[len(la)//2],
                                              sorted(lb)[len(lb)//2]],
                            "token_disjoint": True}}, f)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
