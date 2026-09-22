"""Generate the findings-gate fixtures from the clean case.

Each derived fixture must violate EXACTLY the gate it is named for. Generating
them here (rather than hand-writing JSON) keeps them provably minimal
perturbations of the clean case, so a gate that fires can only be reacting to
the intended violation.

Two clean bases:
  * `clean.jsonl`                     — G-E1/E2/E6/E7 (schema, evidence, append-only)
  * `claim_consistency_clean.jsonl`   — G-E3/E4/E5/E8 (claim consistency); its
    records are legitimately `flagged`/`null`, proving the rules do not reject
    everything, and the flagged record's `note` DISCLAIMS a mathematical claim,
    which G-E5 must pass.

Run: python3 tooling/gates/tests/make_findings_fixtures.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "findings"
CLEAN = FIX / "clean.jsonl"

# The claim-consistency clean case, written here so its failing fixtures are
# provably one-field perturbations of it. Record 0 is a genuine flagged causal
# record; record 1 is a null that attributes itself to representation limits and
# carries the absorption caveat.
CC_CLEAN = [
    {
        "ts": "2026-09-19T06:00:00Z", "issue": 7, "run_id": "20260919-0600-cccc",
        "model": "pythia-70m-deduped", "revision": None, "dtype": "float32",
        "sae": "pythia-70m-deduped-res-sm", "layer": 3, "feature_id": 1478,
        "hook": "blocks.3.hook_resid_post",
        "inputs_a": ["cooking passage"], "inputs_b": ["astronomy passage"],
        "activation_a": None, "activation_b": None,
        "null_model": "matched-norm random direction, R=200",
        "correction": "family-wise max-statistic cutoff", "n": 24,
        "statistic": "change in answer logit difference", "p_corrected": None,
        "confounds_checked": ["matched_norm_null"], "confounds_fired": [],
        "paraphrase_controls": ["zero_shared_tokens"], "paraphrase_survived": True,
        "intervention": {
            "hook": "blocks.3.hook_resid_post", "layer": 3, "method": "patching",
            "cause": 0.75, "isolate": 0.42,
            "interference_control": {"matched_protocol_rows": 240,
                                     "spurious_cause_passes": 0},
        },
        "causal_claim": True, "verdict": "flagged",
        "note": "This is not a mathematical result and no theorem is claimed: "
                "it records that feature 1478 is causally load-bearing in both "
                "domains and survived the zero-shared-token control.",
    },
    {
        "ts": "2026-09-19T06:01:00Z", "issue": 3, "run_id": "20260919-0601-dddd",
        "model": "pythia-70m-deduped", "revision": None, "dtype": "float32",
        "sae": "pythia-70m-deduped-res-sm", "layer": 3, "feature_id": None,
        "hook": "blocks.3.hook_resid_post",
        "inputs_a": ["cooking passage"], "inputs_b": ["astronomy passage"],
        "activation_a": None, "activation_b": None,
        "null_model": "pairing permutation, N_PERM=400",
        "correction": "family-wise max-statistic cutoff", "n": 793,
        "statistic": "standardized per-feature cross-domain co-activation z",
        "p_corrected": None,
        "confounds_checked": ["injected_positive_control_recovery"],
        "confounds_fired": [], "paraphrase_controls": [],
        "paraphrase_survived": None, "intervention": None,
        "causal_claim": False, "verdict": "null",
        "note": "The null may reflect SAE representational limits rather than "
                "absence of structure: feature absorption is a known source of "
                "false negatives (PRIOR_ART 4), so a null here is inconclusive, "
                "not negative.",
    },
]


def load_records():
    return [json.loads(l) for l in CLEAN.read_text().splitlines()
            if l.strip() and not l.startswith("#")]


def dump(path: Path, records, header: str):
    lines = [f"# {header}", "#"]
    for r in records:
        lines.append(json.dumps(r))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path.name} ({len(records)} record(s))")


def main():
    recs = load_records()

    # G-E1: an undeclared key. Violates schema only — all required keys present,
    # all evidence non-empty, count unchanged, run_id/issue untouched.
    r = [dict(x) for x in recs]
    r[0]["surprise_field"] = "not in the schema"
    dump(FIX / "g_e1_unknown_key.jsonl", r,
         "G-E1 failing fixture: record 1 carries an undeclared key.")

    # G-E2: correction present but empty. Violates the evidence bar only.
    r = [dict(x) for x in recs]
    r[0]["correction"] = ""
    dump(FIX / "g_e2_empty_correction.jsonl", r,
         "G-E2 failing fixture: record 1 has an empty `correction`.")

    # G-E6: fewer records than the high-water mark (2). Violates append-only only.
    dump(FIX / "g_e6_shrunk.jsonl", [recs[0]],
         "G-E6 failing fixture: 1 record where the mark is 2 — looks like a deletion.")

    # G-E7: malformed run_id. Violates the format check only; the issue half
    # still resolves against the cache.
    r = [dict(x) for x in recs]
    r[0]["run_id"] = "not-a-run-id"
    dump(FIX / "g_e7_bad_runid.jsonl", r,
         "G-E7 failing fixture: record 1 has a malformed run_id.")

    # G-E7, second violation path: cites an issue that is not closed-done.
    r = [dict(x) for x in recs]
    r[0]["issue"] = 999
    dump(FIX / "g_e7_open_issue.jsonl", r,
         "G-E7 failing fixture: record 1 cites issue #999, which the cache "
         "reports as OPEN.")

    # ---- claim-consistency clean case (G-E3/E4/E5/E8) --------------------
    dump(FIX / "claim_consistency_clean.jsonl", CC_CLEAN,
         "G-E3/E4/E5/E8 CLEAN fixture: a legitimate flagged causal record whose "
         "note disclaims a mathematical claim, and a null carrying the "
         "absorption caveat. All four rules must be silent here.")

    # G-E3: causal_claim true but intervention is null. Violates G-E3 only.
    r = [json.loads(json.dumps(x)) for x in CC_CLEAN]
    r[0]["intervention"] = None
    dump(FIX / "g_e3_causal_no_intervention.jsonl", r,
         "G-E3 failing fixture: record 1 claims causal_claim but carries no "
         "intervention.")

    # G-E4: paraphrase_survived true with no controls listed. Violates G-E4 only.
    r = [json.loads(json.dumps(x)) for x in CC_CLEAN]
    r[0]["paraphrase_controls"] = []
    dump(FIX / "g_e4_survived_no_controls.jsonl", r,
         "G-E4 failing fixture: record 1 claims paraphrase_survived with no "
         "control listed.")

    # G-E5: the note asserts a theorem. Violates G-E5 only (no negation nearby).
    r = [json.loads(json.dumps(x)) for x in CC_CLEAN]
    r[0]["note"] = ("This proves a theorem about cross-domain structure; the "
                    "feature is causally load-bearing in both domains.")
    dump(FIX / "g_e5_asserts_theorem.jsonl", r,
         "G-E5 failing fixture: record 1's note asserts a theorem.")

    # G-E8: a null attributing itself to representation limits, with the
    # absorption caveat removed. Violates G-E8 only.
    r = [json.loads(json.dumps(x)) for x in CC_CLEAN]
    r[1]["note"] = ("The null reflects SAE representational limits rather than "
                    "absence of structure.")
    dump(FIX / "g_e8_null_no_absorption.jsonl", r,
         "G-E8 failing fixture: record 2's null cites a representational limit "
         "without the absorption caveat.")


if __name__ == "__main__":
    main()
