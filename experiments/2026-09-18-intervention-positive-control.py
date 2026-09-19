"""Issue #7 — Causal positive control via interchange intervention (ablation).

**Model:** pythia-70m-deduped (TransformerLens), fp32, CPU.
**Inputs:** paired prompts with different target continuations (below). Base
  prompt carries the target attribute to be moved; source prompt carries the
  alternative. All prompts are in-distribution natural text (DEC-008).
**Question:** for an SAE feature active in both domains, does intervening on it
  (a) **Cause** the target attribute to change, and (b) **Isolate** the change
  to that attribute — per RAVEL (Huang et al., ACL 2024, arXiv:2402.17700)?
**Null:** full-residual-stream swap is the known-positive (see below); the
  negative is a feature with zero activation in both prompts, which must move
  nothing. Per DEC-019 a known-positive is mandatory before the result means
  anything.
**Correction:** not applicable — this is a per-feature causal measurement on a
  fixed prompt set, not a family of significance tests. N is stated.
**Issue:** #7 (run 20260918-2332-e7c4).

WHAT THIS ESTABLISHES, AND WHAT IT DOES NOT.

The claim this repo can support is: *feature F is causally load-bearing in both
domains A and B*. This harness measures "causally load-bearing" for a single
prompt pair, using RAVEL's two properties. It does NOT establish that the two
domains are semantically related — that is #6's job. And per DEC-008 a *failed*
intervention is **inconclusive, not negative**: some concepts are effectively
anti-steerable, so a null here does not count against a feature.

THE KNOWN-POSITIVE (DEC-019, applied to this harness first).

Before any feature is scored, the harness must show its intervention mechanics
can move the output at all. The check is a **full residual-stream interchange**:
write the source prompt's residual at the hook into the base prompt. If that
does not move the output toward the source's target, the harness is broken and
no feature-level result is interpretable. This is the intervention analogue of
the constructibility check DEC-019 now requires of every positive control.

INTERVENTION MECHANIC (ablation preferred over steering, DEC-008).

The hook is `blocks.3.hook_resid_post`, activation a in R^d_model.
  f      = SAE.encode(a)                    (d_sae, non-negative)
  ablate = a - f_j * W_dec[j]               remove feature j's own direction
  patch  = a - f_j^base * W_dec[j] + f_j^src * W_dec[j]
Subtracting f_j * W_dec[j] removes exactly that feature's contribution without
depending on whether the SAE's full reconstruction equals a. Additive steering
is deliberately not used: the unreliability results cluster there (DEC-008).

Run: python3 experiments/2026-09-18-intervention-positive-control.py
"""
from __future__ import annotations

import json
import time

import numpy as np
import torch
from sae_lens import SAE
from transformer_lens import HookedTransformer

MODEL = "pythia-70m-deduped"
HOOK = "blocks.3.hook_resid_post"
SAE_RELEASE = "pythia-70m-deduped-res-sm"
RUN_ID = "20260918-2332-e7c4"
ISSUE = 7
TOP_K = 10
OUT = "experiments/2026-09-18-intervention-positive-control-results.json"

# Base/source pairs: same sentence frame, different target continuation.
# Both chosen from the task probe where pythia-70m is correct and confident.
PAIRS = [
    {"name": "open/happy",
     "base": "She opened the", "base_target": " door",
     "source": "Happy birthday to", "source_target": " you"},
    {"name": "counting/birthday",
     "base": "one, two,", "base_target": " three",
     "source": "Happy birthday to", "source_target": " you"},
    {"name": "door/counting",
     "base": "She opened the", "base_target": " door",
     "source": "one, two,", "source_target": " three"},
    {"name": "shakespeare/red",
     "base": "Romeo and Juliet is a play by William",
     "base_target": " Shakespeare",
     "source": "red, green,", "source_target": " blue"},
    {"name": "tobe/door",
     "base": "To be or not to", "base_target": " be",
     "source": "She opened the", "source_target": " door"},
]

# RAVEL ceiling, carried for calibration (PRIOR_ART section 11 Q1): SAE scored
# 48.6 (entity) / 46.8 (context) disentanglement vs 60.1 / 65.6 for supervised.
RAVEL_SAE_CEILING = {"entity": 48.6, "context": 46.8}
RAVEL_SUPERVISED = {"entity": 60.1, "context": 65.6}


def first_target_id(model, text):
    return int(model.to_tokens(text, prepend_bos=False)[0, 0])


def top_tokens(model, logits, k=5):
    probs = torch.softmax(logits, dim=-1)
    idx = torch.argsort(probs, descending=True)[:k]
    return [(int(i), model.to_string(int(i)).strip(), float(probs[i])) for i in idx]


def main():
    t_start = time.time()
    results = {"run_id": RUN_ID, "issue": ISSUE, "model": MODEL, "hook": HOOK,
               "sae": SAE_RELEASE, "top_k": TOP_K, "n_pairs": len(PAIRS),
               "ravel_ceiling": RAVEL_SAE_CEILING,
               "ravel_supervised": RAVEL_SUPERVISED}

    print(f"=== issue #{ISSUE} intervention harness | {MODEL} | {HOOK} ===")
    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")
    W_dec = sae.W_dec.detach().cpu()          # (d_sae, d_model)
    print(f"  d_sae={sae.cfg.d_sae}  d_model={model.cfg.d_model}")

    def run_with_resid(tokens, resid_override=None):
        """Forward pass; optionally replace the residual at the final position.

        The override applies at the LAST position only, which is where the
        next-token prediction is read from.
        """
        def hook(resid, hook=None):
            if resid_override is not None:
                resid = resid.clone()
                resid[:, -1, :] = resid_override
            return resid
        with torch.no_grad():
            logits = model.run_with_hooks(
                tokens, fwd_hooks=[(HOOK, hook)])
        return logits[0, -1]

    # ---------------------------------------------------------------- pairs
    pair_results = []
    all_known_positive_pass = True

    for pair in PAIRS:
        name = pair["name"]
        print(f"\n--- pair '{name}' ---")
        base_toks = model.to_tokens(pair["base"])
        src_toks = model.to_tokens(pair["source"])
        base_tid = first_target_id(model, pair["base_target"])
        src_tid = first_target_id(model, pair["source_target"])

        base_logits = run_with_resid(base_toks)
        src_logits = run_with_resid(src_toks)
        base_p = float(torch.softmax(base_logits, -1)[base_tid])
        src_p = float(torch.softmax(src_logits, -1)[src_tid])
        print(f"  base  '{pair['base']}' -> target p={base_p:.3f}  "
              f"(top: {top_tokens(model, base_logits, 3)})")
        print(f"  source '{pair['source']}' -> target p={src_p:.3f}  "
              f"(top: {top_tokens(model, src_logits, 3)})")

        # residual activations at the final position
        _, base_cache = model.run_with_cache(
            base_toks, names_filter=lambda n: n == HOOK)
        _, src_cache = model.run_with_cache(
            src_toks, names_filter=lambda n: n == HOOK)
        base_resid = base_cache[HOOK][0, -1]      # (d_model,)
        src_resid = src_cache[HOOK][0, -1]
        base_f = sae.encode(base_resid[None, None, :])[0, 0]   # (d_sae,)
        src_f = sae.encode(src_resid[None, None, :])[0, 0]

        # -----------------------------------------------------------
        # KNOWN-POSITIVE (DEC-019): full residual interchange.
        # Write the source residual into the base at the last position.
        # If this does not move the output toward the source target, the
        # harness is broken and nothing below is interpretable.
        # -----------------------------------------------------------
        patched_logits = run_with_resid(base_toks, resid_override=src_resid)
        patched_p_src = float(torch.softmax(patched_logits, -1)[src_tid])
        patched_p_base = float(torch.softmax(patched_logits, -1)[base_tid])
        kp_moved = (patched_p_src > base_p) or (patched_p_base < base_p)
        print(f"  KNOWN-POSITIVE (full resid swap): base target p "
              f"{base_p:.3f} -> {patched_p_base:.3f}; "
              f"source target p {float(torch.softmax(base_logits,-1)[src_tid]):.3f}"
              f" -> {patched_p_src:.3f}  "
              f"{'PASS' if kp_moved else 'FAIL'}")
        if not kp_moved:
            all_known_positive_pass = False

        # candidate features: active in the SOURCE (the attribute we patch in)
        top_feats = torch.argsort(src_f, descending=True)[:TOP_K]
        feats = []
        for j in top_feats:
            j = int(j)
            caveat = "" if float(src_f[j]) > 0 else " (zero activation)"
            # ---- ablation on the base: remove feature j's contribution ----
            ablated_resid = base_resid - float(base_f[j]) * W_dec[j]
            abl_logits = run_with_resid(base_toks, resid_override=ablated_resid)
            abl_p_base = float(torch.softmax(abl_logits, -1)[base_tid])

            # ---- patch source->base for feature j ----
            patched_resid = (base_resid - float(base_f[j]) * W_dec[j]
                             + float(src_f[j]) * W_dec[j])
            pat_logits = run_with_resid(base_toks, resid_override=patched_resid)
            pat_p_src = float(torch.softmax(pat_logits, -1)[src_tid])
            pat_p_base = float(torch.softmax(pat_logits, -1)[base_tid])

            # Cause: did the target attribute move toward the source?
            cause_abl = base_p - abl_p_base          # drop in base target
            cause_pat = pat_p_src                    # rise in source target
            cause = max(cause_abl, cause_pat)
            # Isolate: did OTHER top tokens change? Measure change in the
            # base's original top-3 excluding the two targets.
            orig_top = [t for t, _, _ in top_tokens(model, base_logits, 5)]
            others = [t for t in orig_top if t not in (base_tid, src_tid)][:3]
            orig_probs = torch.softmax(base_logits, -1)
            pat_probs = torch.softmax(pat_logits, -1)
            other_shift = max(
                (abs(float(pat_probs[t]) - float(orig_probs[t])) for t in others),
                default=0.0)
            # A high isolate score is VACUOUS when cause is ~0: if nothing
            # moved, "other attributes untouched" is trivially true. Report it
            # only when the feature actually did something (DEC-019: a check
            # that cannot fail is not a check).
            MEANINGFUL = 0.01
            isolate_valid = cause > MEANINGFUL
            isolate = (1.0 - other_shift) if isolate_valid else None

            feats.append({
                "feature_id": j,
                "activation_base": float(base_f[j]),
                "activation_source": float(src_f[j]),
                "cause_ablation_drop": cause_abl,
                "cause_patch_rise": cause_pat,
                "cause": cause,
                "isolate_score": isolate,
                "isolate_valid": bool(isolate_valid),
                "other_attribute_shift_max": other_shift,
                "causally_load_bearing": bool(cause > MEANINGFUL),
                "note": caveat,
            })
            iso_s = f"{isolate:.3f}" if isolate is not None else "n/a (cause~0)"
            print(f"    feat {j:>6}  a_base={float(base_f[j]):.3f} "
                  f"a_src={float(src_f[j]):.3f}  "
                  f"cause_abl={cause_abl:+.3f} cause_pat={cause_pat:+.3f}  "
                  f"isolate={iso_s}{caveat}")

        a_hat_base = sae.decode(base_f[None, None, :])[0, 0]
        recon_rel = float((base_resid - a_hat_base).norm()
                          / base_resid.norm())
        recon_cos = float(torch.nn.functional.cosine_similarity(
            base_resid, a_hat_base, dim=0))

        # ---------------------------------------------------------------
        # DOSE-RESPONSE LADDER. The single-feature scores are mostly at the
        # noise floor at this scale, so a per-feature null is uninformative on
        # its own (DEC-019: it could be the harness, not the model). Cumulatively
        # ablating the top-k features is the known-positive for the *ablation
        # mechanic*: if the output does not move as k grows, ablation is not
        # reaching the output at all and no per-feature claim is interpretable.
        # ---------------------------------------------------------------
        order = torch.argsort(base_f, descending=True)
        ladder = []
        for k in (1, 5, 10, 25, 50, 100, 200):
            idx = order[:k]
            delta = (base_f[idx][:, None] * W_dec[idx]).sum(0)
            lg = run_with_resid(base_toks, resid_override=base_resid - delta)
            p_k = float(torch.softmax(lg, -1)[base_tid])
            ladder.append({"k": int(k), "base_target_prob": p_k})
        ladder_moves = (ladder[-1]["base_target_prob"]
                        < ladder[0]["base_target_prob"] - 0.05)
        print(f"  SAE reconstruction: rel_err={recon_rel:.3f} "
              f"cos={recon_cos:.3f}")
        print(f"  ablation dose-response: k=1 {ladder[0]['base_target_prob']:.3f}"
              f" -> k=200 {ladder[-1]['base_target_prob']:.3f}  "
              f"{'MOVES' if ladder_moves else 'FLAT (ablation not reaching output)'}")

        # ---- interference control: features active in NEITHER prompt ----
        inactive = torch.nonzero((base_f <= 0) & (src_f <= 0)).flatten()
        ctrl = int(inactive[len(inactive) // 2]) if len(inactive) else None
        if ctrl is not None:
            ctrl_resid = base_resid - 0.0 * W_dec[ctrl]
            ctrl_logits = run_with_resid(base_toks, resid_override=ctrl_resid)
            ctrl_shift = float(torch.max(torch.abs(
                torch.softmax(ctrl_logits, -1) - torch.softmax(base_logits, -1))))
            print(f"    interference control (inactive feat {ctrl}): "
                  f"max prob shift {ctrl_shift:.2e}")
        else:
            ctrl_shift = None

        pair_results.append({
            "pair": name, "base": pair["base"], "source": pair["source"],
            "base_target_prob": base_p, "source_target_prob": src_p,
            "sae_reconstruction_rel_error": recon_rel,
            "sae_reconstruction_cosine": recon_cos,
            "ablation_ladder": ladder,
            "ablation_ladder_moves": bool(ladder_moves),
            "known_positive_pass": bool(kp_moved),
            "known_positive_detail": {
                "patched_base_target_p": patched_p_base,
                "patched_source_target_p": patched_p_src,
            },
            "features": feats,
            "interference_control_feature": ctrl,
            "interference_control_shift": ctrl_shift,
        })

    # ------------------------------------------------------------- summary
    n_lb = sum(1 for p in pair_results for f in p["features"]
               if f["causally_load_bearing"])
    n_feat = sum(len(p["features"]) for p in pair_results)
    # Only count isolate where it is non-vacuous (cause > threshold). Averaging
    # in the ~1.0 values from zero-cause features would report a confident-
    # looking number computed entirely from cases where nothing happened.
    iso = [f["isolate_score"] for p in pair_results for f in p["features"]
           if f["isolate_valid"] and f["isolate_score"] is not None]
    n_ladders_move = sum(1 for p in pair_results if p["ablation_ladder_moves"])
    recon = [p["sae_reconstruction_rel_error"] for p in pair_results]
    results["pairs"] = pair_results
    results["all_known_positive_pass"] = bool(all_known_positive_pass)
    results["n_features_scored"] = n_feat
    results["n_causally_load_bearing"] = n_lb
    results["n_isolate_valid"] = len(iso)
    results["isolate_mean"] = float(np.mean(iso)) if iso else None
    results["isolate_median"] = float(np.median(iso)) if iso else None
    results["n_pairs_ladder_moves"] = n_ladders_move
    results["sae_reconstruction_rel_error_mean"] = float(np.mean(recon))
    results["total_seconds"] = round(time.time() - t_start, 1)

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2)

    print("\n=== summary ===")
    print(f"  known-positive (full resid swap) passed on all pairs: "
          f"{all_known_positive_pass}")
    print(f"  ablation dose-response moved the output on "
          f"{n_ladders_move}/{len(pair_results)} pairs")
    print(f"  SAE reconstruction rel. error: "
          f"{results['sae_reconstruction_rel_error_mean']:.3f} (mean)")
    print(f"  features scored: {n_feat}; causally load-bearing: {n_lb}")
    if iso:
        print(f"  isolate score (non-vacuous only, n={len(iso)}): "
              f"mean {results['isolate_mean']:.3f} "
              f"median {results['isolate_median']:.3f}")
    else:
        print("  isolate score: NOT REPORTABLE — no feature reached the cause "
              "threshold, so every 'others untouched' reading would be vacuous")
    print(f"  RAVEL SAE ceiling for calibration: {RAVEL_SAE_CEILING} "
          f"vs supervised {RAVEL_SUPERVISED}")
    print(f"\n=== wrote {OUT} in {results['total_seconds']}s ===")

    if not all_known_positive_pass:
        print("\n  ** KNOWN-POSITIVE FAILED: the harness could not move the "
              "output by residual interchange. Per DEC-019 no feature-level "
              "result here is interpretable. **")
    elif n_lb == 0:
        print("\n  ** Zero single-feature interventions exceeded the cause "
              "threshold. Per DEC-008 this is INCONCLUSIVE, not negative: it "
              "does not count against any feature. Read alongside the "
              "dose-response ladder and the reconstruction error above. **")


if __name__ == "__main__":
    main()
