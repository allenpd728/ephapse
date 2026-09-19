"""Issue #7: causal positive control via interchange intervention (activation
patching) on SAE features, scored on RAVEL's Cause / Isolate properties.

**Model:** pythia-70m-deduped (TransformerLens), fp32, CPU, read-only.
**Inputs:** 8 short factual prompts ``The {capital|language} of {country} is``
  over countries {France, Japan, Italy, Egypt}, one answer per prompt. There is
  no external corpus: this is a *harness self-test on a task with a known
  causal structure*, not the cross-domain probe (that is #3, gated on #6).
**Question:** does patching a single SAE feature at layer 3 move the model's
  next-token answer for that country (Cause), while leaving the other
  attribute's answer alone (Isolate)? And does the answer depend on *where* in
  the sequence the patch lands and *which scale* the effect is read on?
**Null:** matched-norm random-direction control - the identical patching
  harness driven by a random d_model direction scaled to the real patch norm,
  R=200 replicates, computed separately per intervention site. This is the
  interference/no-effect null.
**Correction:** family-wise max-statistic over the direction null - a feature
  is credited only if its effect exceeds the 95th percentile of the
  *per-replicate maximum* effect across the whole family of 24 interchanges
  (DEC-016 convention; NOT BH-FDR, which is structurally impossible at this
  N_PERM - see DEC-016).
**Issue:** #7 (run 20260919-0229-to3m).

WHY THERE ARE TWO INTERVENTION SITES AND TWO METRIC SCALES
  A sibling contribution on this same issue (run 20260918-2332-e7c4, DEC-020)
  scored single-feature ablation/patching at the **final token** on a
  **probability** scale and found *0 of 50 features* causally load-bearing.
  This harness patches at the **country token** and reads a **logit
  difference**. Both are reported here so the two are directly comparable:
  the effect is real on the logit scale at the feature's own token position
  and vanishes on the probability scale at the output. See DEC-025.

WHAT IS TESTED, AND WHAT IS NOT
  This is the *causal half* of the claim the repo can support. It shows the
  instrument can turn "feature F is active" into "feature F is causally
  load-bearing", and it reports the instrument's own ceiling. It does NOT test
  cross-domain semantics: the entity features here fire on a country token,
  found on a task with a known causal ground truth. Applying this harness to a
  flagged cross-domain pair needs #6 and #3.

  DEC-008: ablation is preferred over additive steering; both an ablation and
  an interchange (patching) arm are run. A failed intervention is
  inconclusive, not evidence against a feature.

RAW NUMBERS AND EXACT COMMANDS go in the issue #7 done comment; the machine
readable dump lands in the sibling *-results.json.
"""
import json
import os

import numpy as np
import torch

MODEL = "pythia-70m-deduped"
SAE_RELEASE = "pythia-70m-deduped-res-sm"
HOOK = "blocks.3.hook_resid_post"
LAYER = 3
COUNTRY_POS = 3          # "The {attr} of {Country} is" -> index of the country token
N_NULL = 200             # random-direction replicates for the family-wise cutoff
N_INTERFERENCE = 10      # random unrelated SAE features per interchange
SEED = 7
# Both intervention sites are evaluated, because a sibling contribution on #7
# found single-feature intervention *below the noise floor* while patching at
# the country token (here) works. Location is therefore a variable, not a fixed
# choice. See DEC-025 (extends DEC-020).
SITES = {"country_token": COUNTRY_POS, "final_token": -1}

COUNTRIES = ["France", "Japan", "Italy", "Egypt"]
ANSWERS = {
    "capital": {"France": "Paris", "Japan": "Tokyo", "Italy": "Rome", "Egypt": "Cairo"},
    "language": {"France": "French", "Japan": "Japanese", "Italy": "Italian", "Egypt": "Arabic"},
}
# Entity-selective features at the country token (found by the screening pass;
# each fires only on its own country's token, in both the capital and language
# prompts). Indexed by the country whose token they encode.
ENTITY_FEATURE = {"France": 21315, "Japan": 11504, "Italy": 24019, "Egypt": 2620}
RAVEL_CEILING = {"sae_entity": 48.6, "sae_context": 46.8,
                 "mdas_entity": 60.1, "mdas_context": 65.6}


def prompt(attr, country):
    name = "capital" if attr == "capital" else "language"
    return f"The {name} of {country} is"


def build():
    texts, index = [], {}
    for attr in ANSWERS:
        for c in COUNTRIES:
            index[(attr, c)] = len(texts)
            texts.append(prompt(attr, c))
    return texts, index


def evaluate(model, texts, deltas=None, site=COUNTRY_POS):
    """Next-token logits for each prompt, optionally with a per-item delta added
    to the residual stream at ``site`` (activation patching / ablation)."""
    if deltas is None:
        with torch.no_grad():
            return model(texts)[:, -1, :]
    B = len(texts)

    def hook(act, hook, deltas=deltas, site=site):
        act = act.clone()
        act[torch.arange(B), site, :] += deltas
        return act

    with torch.no_grad():
        return model.run_with_hooks(texts, fwd_hooks=[(HOOK, hook)])[:, -1, :]


def logitdiff(logits, pid, pn):
    return float(logits[pid] - logits[pn])


def main():
    from transformer_lens import HookedTransformer
    from sae_lens import SAE

    print("=== issue #7: interchange-intervention causal positive control ===")
    print(f"model={MODEL} sae={SAE_RELEASE} hook={HOOK} country_pos={COUNTRY_POS}")
    print(f"null=matched-norm random direction, R={N_NULL}; "
          f"correction=family-wise max-statistic (95th pct of per-replicate max)")

    model = HookedTransformer.from_pretrained(MODEL, device="cpu")
    sae = SAE.from_pretrained(release=SAE_RELEASE, sae_id=HOOK, device="cpu")
    Wdec = sae.W_dec.detach()  # (d_sae, d_in)

    texts, index = build()
    tok = model.to_tokens(texts)
    assert tok.shape[0] == len(texts) and len(set(tok.shape[1:])) == 1, \
        "prompts must be equal length to batch without padding"

    answer_id = {a: int(model.to_tokens(" " + a, prepend_bos=False)[0, 0])
                 for a in set(sum([list(v.values()) for v in ANSWERS.values()], []))}
    multi = [a for a in answer_id if model.to_tokens(" " + a, prepend_bos=False).shape[1] != 1]
    assert not multi, f"answers must be single tokens, got {multi}"

    with torch.no_grad():
        _, cache = model.run_with_cache(texts, names_filter=lambda n: n == HOOK)
        R = cache[HOOK][:, COUNTRY_POS, :]        # (8, d_model) at country token
        F = sae.encode(R)                        # (8, d_sae)
    F = F.numpy()
    base_logits = evaluate(model, texts)

    print()
    print("=== entity feature values at the country token (both attributes) ===")
    for c, f in ENTITY_FEATURE.items():
        vals = {f"{a}_{cc}": round(float(F[index[(a, cc)], f]), 2)
                for a in ANSWERS for cc in COUNTRIES}
        print(f"  f{f:>5d} ({c:6s}): {vals}")

    # ---- build the family of 24 interchanges (4 features x 3 dst x 2 attrs) ----
    # RAVEL reading used here: the *entity* (country) is the intervened
    # attribute, the *context* (capital vs language) is the other attribute.
    #   Cause   -> the source country's answer logit rises for the SAME context
    #              (target LD = logit(answer[attr][X]) - logit(answer[attr][d])).
    #   Isolate -> the entity moves without dragging the OTHER context with it:
    #              the correct-context answer rises more than the wrong-context
    #              answer of the same source country
    #              (iso = dlogit(answer[attr][X]) - dlogit(answer[other][X])).
    # This is the context-preservation half; it is not trivially true, because a
    # non-isolated (polysemantic) feature drags both contexts up equally.
    family = []
    for X in COUNTRIES:
        f = ENTITY_FEATURE[X]
        for attr in ANSWERS:
            other = "language" if attr == "capital" else "capital"
            for d in COUNTRIES:
                if d == X:
                    continue
                bi, si = index[(attr, d)], index[(attr, X)]
                delta = (torch.tensor(F[si, f] - F[bi, f]) * Wdec[f]).numpy()
                family.append({
                    "feature": f, "src": X, "dst": d, "attr": attr,
                    "base_i": bi, "src_i": si, "delta": delta,
                    "t_pos": answer_id[ANSWERS[attr][X]],
                    "t_neg": answer_id[ANSWERS[attr][d]],
                    "w_id": answer_id[ANSWERS[other][X]],
                })
    print(f"\nfamily size: {len(family)} interchanges "
          f"({len(COUNTRIES)} features x 3 dst x 2 attrs)")

    base_idx = [e["base_i"] for e in family]
    real_delta = torch.tensor(np.stack([e["delta"] for e in family]))
    tip = [e["t_pos"] for e in family]
    tin = [e["t_neg"] for e in family]
    wid = [e["w_id"] for e in family]
    rng = np.random.default_rng(SEED)
    B = len(family)
    norms = np.linalg.norm(real_delta.numpy(), axis=1, keepdims=True)
    base_p = {k: float(torch.softmax(base_logits[base_idx[k]], -1)[tip[k]])
              for k in range(B)}

    site_results = {}
    for site_name, site_pos in SITES.items():
        patched = evaluate(model, [texts[i] for i in base_idx],
                           deltas=real_delta, site=site_pos)
        d_target = np.array([logitdiff(patched[k], tip[k], tin[k])
                             - logitdiff(base_logits[base_idx[k]], tip[k], tin[k])
                             for k in range(B)])
        p_patch = np.array([float(torch.softmax(patched[k], -1)[tip[k]])
                            for k in range(B)])
        cause_prob = p_patch - np.array([base_p[k] for k in range(B)])
        d_wrong = np.array([float(patched[k][wid[k]])
                            - float(base_logits[base_idx[k]][wid[k]])
                            for k in range(B)])
        iso = d_target - d_wrong

        null_t = np.empty((N_NULL, B))
        null_iso = np.empty((N_NULL, B))
        for r in range(N_NULL):
            dirs = rng.standard_normal((B, Wdec.shape[1]))
            dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
            lg = evaluate(model, [texts[i] for i in base_idx],
                          deltas=torch.tensor(dirs * norms), site=site_pos)
            for k in range(B):
                dt = logitdiff(lg[k], tip[k], tin[k]) - logitdiff(base_logits[base_idx[k]], tip[k], tin[k])
                dw = float(lg[k][wid[k]]) - float(base_logits[base_idx[k]][wid[k]])
                null_t[r, k] = dt
                null_iso[r, k] = dt - dw
        cut_c = float(np.percentile(null_t.max(axis=1), 95))
        cut_i = float(np.percentile(null_iso.max(axis=1), 95))
        site_results[site_name] = {
            "site_pos": site_pos if site_pos >= 0 else "final",
            "cutoff_cause": cut_c, "cutoff_isolate": cut_i,
            "d_target": d_target, "cause_prob": cause_prob, "iso": iso,
            "cause_pass": d_target > cut_c, "isolate_pass": iso > cut_i,
        }

    print()
    print("=== intervention SITE comparison (a sibling #7 contribution found the")
    print("    single-feature effect below the noise floor at the final token) ===")
    print(f"{'site':14s} {'mean dLD':>9s} {'mean dProb':>10s} {'cause pass':>11s} "
          f"{'cutoff':>7s} {'mean iso':>9s} {'iso pass':>9s}")
    for s, sr in site_results.items():
        print(f"{s:14s} {sr['d_target'].mean():>9.3f} {sr['cause_prob'].mean():>10.4f} "
              f"{sr['cause_pass'].mean():>11.3f} {sr['cutoff_cause']:>7.3f} "
              f"{sr['iso'].mean():>9.3f} {sr['isolate_pass'].mean():>9.3f}")

    # Primary site is the country token; the final-token site is the sibling's
    # configuration and is reported for reconciliation.
    prim = site_results["country_token"]
    for k, e in enumerate(family):
        e["d_target"] = float(prim["d_target"][k])
        e["iso"] = float(prim["iso"][k])
        e["cause_pass"] = bool(prim["cause_pass"][k])
        e["isolate_pass"] = bool(prim["isolate_pass"][k])
    cutoff_cause = prim["cutoff_cause"]
    cutoff_iso = prim["cutoff_isolate"]
    print(f"\nprimary site = country_token; cutoffs: cause {cutoff_cause:.4f}, "
          f"isolate {cutoff_iso:.4f}")

    print()
    print("=== Cause / Isolate per feature (fraction of its 6 interchanges) ===")
    per_feature = {}
    print(f"{'country':8s} {'feat':>6s} {'Cause':>7s} {'Isolate':>8s} "
          f"{'mean dtarget':>13s} {'mean iso':>10s}")
    for c in COUNTRIES:
        es = [e for e in family if e["src"] == c]
        cause = np.mean([e["cause_pass"] for e in es])
        iso = np.mean([e["isolate_pass"] for e in es])
        mdt = np.mean([e["d_target"] for e in es])
        miso = np.mean([e["iso"] for e in es])
        per_feature[c] = {"feature": ENTITY_FEATURE[c], "cause": float(cause),
                          "isolate": float(iso), "mean_dtarget": float(mdt),
                          "mean_iso": float(miso)}
        print(f"{c:8s} {ENTITY_FEATURE[c]:>6d} {cause:>7.3f} {iso:>8.3f} "
              f"{mdt:>13.3f} {miso:>10.3f}")

    # ---- interference control: random unrelated SAE features ----
    print()
    print(f"=== interference control: {N_INTERFERENCE} random unrelated SAE features ===")
    active = np.where((F > 0).any(axis=0))[0]
    pool = [int(g) for g in active if g not in ENTITY_FEATURE.values()]
    inter_rows = []
    chosen = rng.choice(len(pool), size=N_INTERFERENCE, replace=False)
    for g_pos in chosen:
        g = pool[g_pos]
        for e in family:
            delta = (torch.tensor(F[e["src_i"], g] - F[e["base_i"], g]) * Wdec[g]).numpy()
            inter_rows.append((g, e, delta))
    inter_delta = torch.tensor(np.stack([r[2] for r in inter_rows]))
    inter_lg = evaluate(model, [texts[r[1]["base_i"]] for r in inter_rows],
                        deltas=inter_delta)
    inter_dt, inter_iso = [], []
    for k, (g, e, _) in enumerate(inter_rows):
        b = base_logits[e["base_i"]]
        dt = logitdiff(inter_lg[k], e["t_pos"], e["t_neg"]) - logitdiff(b, e["t_pos"], e["t_neg"])
        dw = float(inter_lg[k][e["w_id"]]) - float(b[e["w_id"]])
        inter_dt.append(dt)
        inter_iso.append(dt - dw)
    inter_dt = np.array(inter_dt)
    inter_iso = np.array(inter_iso)
    n_cause = int((inter_dt > cutoff_cause).sum())
    n_iso = int((inter_iso > cutoff_iso).sum())
    print(f"  rows: {len(inter_rows)}  mean|dtarget|={np.abs(inter_dt).mean():.3f}  "
          f"max|dtarget|={np.abs(inter_dt).max():.3f}")
    print(f"  exceeding the cause cutoff: {n_cause}/{len(inter_rows)} "
          f"(expected ~0: unrelated features should not move the target)")
    print(f"  above the isolate cutoff: {n_iso}/{len(inter_rows)} "
          f"(interference control - polysemantic transfer would show here)")

    # ---- ablation arm (DEC-008 preference) ----
    print()
    print("=== ablation arm: remove each entity feature on its own prompt ===")
    abl = []
    for c in COUNTRIES:
        f = ENTITY_FEATURE[c]
        for attr in ANSWERS:
            i = index[(attr, c)]
            delta = (-float(F[i, f]) * Wdec[f]).numpy()
            abl.append({"feature": f, "country": c, "attr": attr, "i": i, "delta": delta})
    # measure own-answer logit change vs mean of the other three countries
    abl_delta = torch.tensor(np.stack([a["delta"] for a in abl]))
    abl_lg = evaluate(model, [texts[a["i"]] for a in abl], deltas=abl_delta)
    for k, a in enumerate(abl):
        b = base_logits[a["i"]]
        own0 = float(b[answer_id[ANSWERS[a["attr"]][a["country"]]]])
        own1 = float(abl_lg[k][answer_id[ANSWERS[a["attr"]][a["country"]]]])
        others = [cc for cc in COUNTRIES if cc != a["country"]]
        m0 = np.mean([float(b[answer_id[ANSWERS[a["attr"]][cc]]]) for cc in others])
        m1 = np.mean([float(abl_lg[k][answer_id[ANSWERS[a["attr"]][cc]]]) for cc in others])
        a["own_delta"] = own1 - own0
        a["other_delta"] = m1 - m0
        print(f"  ablate f{a['feature']:<5d} on {a['attr']:8s} {a['country']:6s}: "
              f"own {own0:6.2f}->{own1:6.2f} (d={own1-own0:+6.2f})  "
              f"mean_other {m0:6.2f}->{m1:6.2f} (d={m1-m0:+6.2f})")
    abl_own = np.array([a["own_delta"] for a in abl])
    abl_oth = np.array([a["other_delta"] for a in abl])
    print(f"  ablation mean own-answer drop: {abl_own.mean():+.3f} "
          f"({int((abl_own < 0).sum())}/{len(abl)} negative)")
    print(f"  ablation mean other-answer change: {abl_oth.mean():+.3f}")

    # ---- full-residual interchange: in-model upper bound ----
    print()
    print("=== full-residual interchange (all 512 dims) at country token: upper bound ===")
    upper = []
    for e in [x for x in family
              if x["attr"] == "capital" and x["src"] in ("Japan", "Egypt")]:
        delta = (R[e["src_i"]] - R[e["base_i"]]).numpy()
        lg = evaluate(model, [texts[e["base_i"]]], deltas=torch.tensor(delta[None, :]))
        b = base_logits[e["base_i"]]
        dt = logitdiff(lg[0], e["t_pos"], e["t_neg"]) - logitdiff(b, e["t_pos"], e["t_neg"])
        upper.append({"src": e["src"], "dst": e["dst"], "d_target": dt})
        print(f"  full {e['src']:6s}->{e['dst']:6s}: dtarget={dt:+.3f} "
              f"(SAE feature f{e['feature']} gave {e['d_target']:+.3f})")

    # ---- RAVEL ceiling + verdict ----
    print()
    print("=== calibration (RAVEL, ACL 2024, arXiv:2402.17700) ===")
    print(f"  ceiling to read these against: SAE {RAVEL_CEILING['sae_entity']}/"
          f"{RAVEL_CEILING['sae_context']} vs supervised MDAS "
          f"{RAVEL_CEILING['mdas_entity']}/{RAVEL_CEILING['mdas_context']} disentanglement.")
    print("  Our Cause/Isolate are fractions of interchanges passing a family-wise")
    print("  direction-null cutoff, not RAVEL's disentanglement score; no direct")
    print("  numeric comparison is claimed.")

    mean_cause = float(np.mean([p["cause"] for p in per_feature.values()]))
    mean_iso = float(np.mean([p["isolate"] for p in per_feature.values()]))
    print()
    print("=== summary ===")
    print(f"  mean Cause across 4 entity features:   {mean_cause:.3f}")
    print(f"  mean Isolate across 4 entity features: {mean_iso:.3f}")
    print(f"  unrelated-feature interference: {n_cause}/{len(inter_rows)} spurious cause passes")
    verdict = ("harness validated"
               if mean_cause >= 0.5 and n_cause <= 0.05 * len(inter_rows)
               else "inconclusive - see numbers")
    print(f"  verdict: {verdict} (no arbitrary bar is placed on Isolate; "
          f"the SAE isolation weakness is a reported result, not a pass/fail gate)")

    out = {
        "run_id": "20260919-0229-to3m", "issue": 7, "model": MODEL,
        "sae": SAE_RELEASE, "hook": HOOK, "layer": LAYER, "country_pos": COUNTRY_POS,
        "entity_features": ENTITY_FEATURE,
        "entity_feature_values": {c: {f"{a}_{cc}": float(F[index[(a, cc)], f])
                                      for a in ANSWERS for cc in COUNTRIES}
                                  for c, f in ENTITY_FEATURE.items()},
        "answer_base_logits": {a: {c: round(float(base_logits[index[(a, c)]]
                                                  [answer_id[ANSWERS[a][c]]]), 4)
                                   for c in COUNTRIES} for a in ANSWERS},
        "cutoff_cause": cutoff_cause, "cutoff_isolate": cutoff_iso,
        "n_null": N_NULL, "n_interchanges": len(family),
        "site_results": {s: {"site_pos": sr["site_pos"],
                             "cutoff_cause": sr["cutoff_cause"],
                             "cutoff_isolate": sr["cutoff_isolate"],
                             "mean_dtarget": float(sr["d_target"].mean()),
                             "mean_cause_prob": float(sr["cause_prob"].mean()),
                             "cause_pass_fraction": float(sr["cause_pass"].mean()),
                             "mean_iso": float(sr["iso"].mean()),
                             "isolate_pass_fraction": float(sr["isolate_pass"].mean())}
                         for s, sr in site_results.items()},
        "family": [{k: (v.tolist() if isinstance(v, np.ndarray) else v)
                    for k, v in e.items() if k not in ("delta", "base_i", "src_i")}
                   for e in family],
        "per_feature": per_feature,
        "interference_control": {"n_features": len(chosen), "features": [int(g) for g in chosen],
                                 "n_rows": len(inter_rows),
                                 "spurious_cause_passes": n_cause,
                                 "above_isolate_cutoff": n_iso,
                                 "mean_abs_dtarget": float(np.abs(inter_dt).mean()),
                                 "max_abs_dtarget": float(np.abs(inter_dt).max())},
        "ablation": {"n": len(abl), "mean_own_delta": float(abl_own.mean()),
                     "n_negative": int((abl_own < 0).sum()),
                     "mean_other_delta": float(abl_oth.mean()),
                     "rows": [{k: (float(v) if isinstance(v, (np.floating,)) else v)
                               for k, v in a.items() if k != "delta"} for a in abl]},
        "full_residual_upper": upper,
        "ravel_ceiling": RAVEL_CEILING,
        "mean_cause": mean_cause, "mean_isolate": mean_iso,
        "verdict": verdict,
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "2026-09-19-interchange-intervention-results.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
