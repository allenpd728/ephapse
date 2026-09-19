# Ephapse — Agent Handoff

## What this project is

Ephapse probes open-weight model internals (activations, sparse-autoencoder
features, circuits) to find cross-domain co-activation — cases where
unrelated inputs trigger the same internal structure — as a candidate
generator for mathematical hypotheses. It is a sibling project to Maith,
not a merged one. See "Relationship to Maith" below before doing anything
that blurs that line.

Named for the neuroscience term for unintended signal crossover between
adjacent neurons (as opposed to a synapse, the intended connection) —
that crossover is the literal phenomenon being searched for, just in a
network's activation space instead of a brain.

## What this project is not (read this before opening any issue)

- Not a fork or extension of Maith. Different substrate (model weights and
  activations, not Lean terms), different toolchain (Python/PyTorch, not
  Lean/lake), different validation story (statistical/exploratory, not
  kernel-checked).
- Not a training project. No model gets trained or fine-tuned here. Every
  model used is pretrained and open-weight, used read-only for probing.
- Not a P vs NP project, not a circuit-complexity project specifically.
  Domain-general cross-domain search, same reasoning as Maith's own
  non-goals section: aiming narrowly at a famous target produces worse
  scoping than aiming at a falsifiable, general method.
- Not authorized to claim a discovery is "novel" or "valid" on the
  strength of anything computed inside this repo. See "What counts as a
  result" below.

## Relationship to Maith

One-way handoff, at exactly one interface point:

1. Ephapse flags a cross-domain co-activation event (two unrelated inputs
   triggering the same internal feature/circuit).
2. A human (not an agent) reviews the flagged pair and, if it seems worth
   pursuing, articulates it as a plain-language mathematical claim.
3. That claim is handed to Maith as an ordinary candidate proposal,
   entering Maith's existing gate 1 (homomorphism obligation) exactly like
   any other candidate. Maith's pipeline does not change to accommodate
   this source, and Ephapse does not implement its own gates 2-5.

Do not build a Lean-side validation layer inside this repo. If a candidate
needs Lean checking, it goes to Maith.

## What counts as a result here (the actual validation story)

There is no kernel-equivalent oracle for this repo — that is the central,
structural difference from Maith, and it means the discipline has to come
from process, not from an automatic checker:

- A flagged co-activation event is a **statistical observation**, not a
  finding. Log the models, prompts/inputs, layer, feature ID, and
  activation values. Nothing more is claimed at this stage.
- Statistical significance (co-activation stronger than baseline/noise) is
  the bar for "worth a human looking at it," not "worth calling a
  discovery." Every writeup at this stage should read like a lab notebook
  entry, not an announcement.
- A candidate only becomes a claim once it survives Maith's gates. Nothing
  produced in this repo is ever described as "a new mathematical result"
  in this repo's own docs or issues — that language belongs to Maith's
  gate-3-survivor artifacts only, once earned there.
- Unusual activation is not evidence of correctness. State this
  explicitly in any writeup: hallucination-like generation and genuine
  insight can look identical from inside activation statistics alone.

## Two separate model roles — do not conflate these

This has caused confusion once already; state it plainly so it doesn't
happen inside an agent's plan too.

- **The agent-driving LLM.** This model writes code, manages issues, and
  drives the OpenHands agent loop. It is accessed only over an API.
  **It cannot be probed** — no activation access, no weight access, text
  in and text out only. It has no role in Ephapse's actual research
  subject. (Do not hardcode a model name here: the platform-wide default
  has changed repeatedly — GLM → Kimi K3 → DeepSeek V4 Flash in the
  release notes — and account-level config can differ from the default.
  Check the account's Settings if it matters.)
- **The probed model** (a small open-weight model) — downloaded separately via
  HuggingFace and loaded locally, in-process, inside the sandbox. This is the
  only kind of model TransformerLens/SAELens can actually instrument. It has
  nothing to do with which LLM is powering the agent.

  **The model choice is constrained by SAE availability, not by size.**
  Measured (issue #2): SAELens has **7 Pythia SAE releases, all for
  `pythia-70m-deduped`** — there is no Pythia-160M release and no
  non-deduped Pythia-70M release. So the target is **`pythia-70m-deduped`**
  (`d_model=512`, `n_layers=6`), not the "Pythia-70M to ~410M" the earlier
  guidance implied. A 160M target would require training an SAE first.
  Full table in `SANDBOX_BASELINE.md` §Model and SAE availability.

- **The remote probing API** (Neuronpedia, and nnsight/NDIF for larger
  models) is a **third path, not a smaller local one.** It runs the model
  and SAE on someone else's GPU and returns only a summary: dashboards,
  top-k activations, `maxActApprox`, autointerp labels. You get no arbitrary
  activation matrix, so you cannot compute a full PMI/FDR sweep through it.
  Its binding constraint is **rate limit**, not sandbox RAM. Use it for
  targeted inspection of a feature that already looks interesting; use the
  local path for exploration.

  **Correction (issue #2):** this section previously said the API returns
  "a feature's decoder vector." It does not — `hasVector` is `False` and
  `vector` is an empty list even with `?includeVector=true`, verified on both
  a Pythia and a GPT-2 SAE. The decoder direction comes from **local**
  `sae.W_dec`, which is strictly better (no rate limit, no network, no
  hosted copy to trust). See `SANDBOX_BASELINE.md` §Neuronpedia API.

`get_llm()` / `get_secrets()` are methods on `OpenHandsCloudWorkspace` in
the OpenHands SDK (see the SDK example
`02_remote_agent_server/10_cloud_workspace_share_credentials.py`). They
let an SDK client create a Cloud conversation that inherits the account's
LLM config and secrets. That is an **agent-driving-LLM tool, not a probing
tool**: correct use here is automating the plain-language articulation step
at the Maith handoff interface (turning a flagged co-activation into a
candidate math claim), nothing closer to the research itself.

## Compute and infrastructure constraints

**These are measured, not estimated.** See `docs/reference/SANDBOX_BASELINE.md`
for the raw evidence. Re-verify before sizing an experiment, since sandbox
provisioning can change.

- **RAM**: measured **15 GiB total** (~13 GiB available), CPU only, no GPU,
  shared across OS, Python environment, and the probed model simultaneously.
  **No cgroup cap is enforced** (`memory.max` = `max`), so this is host RAM —
  budget **~10 GB per run**, not 13. Pythia-160M in fp32 peaks at **2.68 GB
  RSS**; Pythia-70M at **1.52 GB**. Cached activations are negligible
  (0.11 MB/prompt for 3 layers) as long as you aggregate rather than
  accumulate them. The doc's older "24GB" figure was wrong — do not size
  against it.
- **CPU**: 4 cores. Latency depends entirely on batching, and the earlier
  guidance here was off by ~10x for sweeps: Pythia-160M is **207 ms** for a
  single prompt (per-call overhead) but **21 ms/prompt** at batch 64. Size
  *sweeps* on the batched figure (2,000 prompts ≈ 40 s); size *interactive
  single-prompt iteration* on the 207 ms figure. Full table in
  `docs/reference/SANDBOX_BASELINE.md`.
- **Disk**: 58 GB free on `/` (overlay). Pythia-160M ≈ 1.1 GB cached; egress
  runs at ~25 MB/s, so a 1 GB checkpoint is under a minute. Not a binding
  constraint.
- **Network egress**: not allowlist-restricted. huggingface.co, the full LFS
  download path, neuronpedia.org, pypi.org, and api.github.com all work.
  Confirm per session rather than assuming, but do not plan around a
  restriction that is not currently present.
- **Environment is not persistent across sessions** — torch and the
  interpretability libraries had to be reinstalled at the start of the issue-1
  run. Assume a cold environment or install from `requirements.txt` first
  thing.
- **Credentials are re-provisioned per session too.** The clone URL embeds a
  token that can expire mid-session, after which `git push` blocks on a
  password prompt (it does not fail). `$GITHUB_TOKEN` was also observed to
  expire mid-session this session, so have the fallback ready. Re-run the
  setup in `MULTI_AGENT_WORKFLOW.md` §Credentials at session start — it states
  which token does what and the one-command fallback — rather than
  re-deriving it.
- **Model size ceiling**: the doc's "70M–1B" is directionally right but the
  mechanism matters. TransformerLens loads **fp32 by default** (hence
  160M → 2.68 GB). With dtype control (fp16) and no autograd, ~1–2B
  params is feasible. Note that batched evaluation is far cheaper than
  interactive use, so "larger models are impractical" applies to iteration,
  not to a fixed eval sweep. Don't declare something "blocked" purely on
  parameter count — state the dtype, the batch size, and whether hooks cache
  activations.
- State the exact model size used in every experiment writeup. Don't
  imply a finding generalizes to a different model size without
  re-running — this matters more here than usual, since the whole method
  is unproven at any size yet.
- If a task needs more than the sandbox provides, flag it as
  `status:blocked-needs-input` rather than silently substituting a
  smaller model or skipping a step — a quiet substitution invalidates the
  experiment design without anyone noticing.

## Tooling (free, no local GPU required)

- **Neuronpedia** — hosted browser for pretrained SAE features on GPT-2,
  Pythia, some Llama/Gemma models. Start here for exploration before
  writing any code.
- **TransformerLens** — standard open-source interpretability library,
  runs on CPU for small models.
- **SAELens** — loads pretrained sparse autoencoders, pairs with
  TransformerLens.
- **Pythia suite (EleutherAI)** — 70M-12B models built for
  interpretability research with full training-data provenance; use the
  70M-410M range for CPU-feasible iterative work.
- **nnsight** — remote-GPU probing via a hosted service, for when CPU is
  genuinely insufficient and local GPU isn't available.

**Which models actually have SAE coverage** matters more than parameter
count when picking a target, and this is a hard constraint, not a preference.
Measured (issue #2): SAELens has 7 Pythia releases and **all are
`pythia-70m-deduped`** — no 160M, no non-deduped 70M. Use
`sae_lens.loading.pretrained_saes_directory.get_pretrained_saes_directory()`
to check before choosing any target, and use the release's `neuronpedia_id`
field to match a local SAE to its hosted copy rather than guessing names.

## Method notes (read before designing issue 3)

**See `docs/reference/PRIOR_ART.md` first — it changes this section's
premises.** The headline: feature universality is established (arXiv:2410.06981)
and SAE features are already known to co-occur more than chance (Clarke,
PIBBSS). So "two unrelated inputs share a feature" is close to the *expected*
result, not a signal. What matters is what survives a filter built to kill
the boring cases.

Cross-domain co-activation fires a lot, for reasons that are not
interesting. The filter has to be specified before the run, or
`findings.jsonl` fills with noise that looks like signal.

- **Specify the null model first.** Normalized PMI between binary feature
  activations, or a co-activation z-score against a permuted-input
  baseline. The choice must be recorded in the finding.
- **Use a positive control, not just a null.** Inject a known
  cross-domain correlation into a background corpus and confirm the
  detector recovers it, reporting recovery rate vs. injection rate. A null
  baseline tells you your detector isn't too permissive; it cannot tell you
  the detector works. The reference method does this and compares against
  an LLM-judge baseline that recovers injected correlations only
  unreliably. This is the most transferable result in the prior-art review.
- **Filter on NPMI *and* semantic distance.** The reference method selects
  candidate pairs at `NPMI > 0.8` and `semantic similarity < 0.2`. The
  second clause is what excludes pairs whose features are similar to each
  other — the naive confound.
- **Use per-feature thresholds, and give prompts enough context.** Two bugs
  found by measurement (DEC-023), both of which silently disabled the
  detector:
  1. **Never threshold on a pooled percentile.** A pooled 99th percentile was
     dominated by a few extreme features and left **32,764 of 32,768 features
     firing on zero prompts**. Threshold each feature on its *own* positive
     activations, then restrict to a selectivity band (e.g. 0.05–0.60) so
     features that fire on everything (which saturate any bridge statistic)
     are excluded.
  2. **Prompts need context.** A 5-token prompt starves the residual stream.
     Usable features by input format: bare 541, sentence 909, **passage 1,188**
     (firing on >=20% of prompts). Wrap prompts in a shared carrier passage so
     only the varied part differs.
- **Use the bridge statistic, not max-NPMI over all pairs.** Measured
  (DEC-023): `max NPMI` over 7.5M pairs failed to separate an *injected*
  signal from noise — `best` was identical (0.6322) with and without
  injection, and the negative control produced false positives. The
  per-feature bridge rate (`P(f fires in both renderings)`) over a restricted
  selectivity band did discriminate. Prefer the restricted statistic.
- **Positive controls must pass a constructibility check and use a bounded
  pair set.** Two requirements, both learned from instrument failures
  (DEC-019, DEC-024):
  1. **Constructibility.** Before the control is run, demonstrate that the
     planted signal actually *moves* the selected features — check that the
     injected rows raise the group marginals. A control whose groups cannot
     fire is not a control, and four consecutive runs failed this way before
     it was checked. (Sibling session's DEC-019; reached independently.)
  2. **Bounded, pre-specified pairs.** Test a pre-specified set (e.g. 20 x 20
     = 400 cross-group pairs), **not** all pairs among active features. An
     unbounded max-statistic over 7.5M pairs is governed by the noisiest pair
     in the family and will not separate an injected signal from noise — and
     it can produce false positives under the null. Measured: the bounded
     version recovers 0.87 at rate 0.20 with 0 false positives; the unbounded
     version returned an identical maximum with and without injection.
- **Two valid nulls, with different failure modes.** A **permutation** null
  has a resolution floor (p >= 1/N_PERM) and cannot resolve a family of
  millions at q=0.1 with N_PERM=100. An **analytic** per-pair null (e.g.
  Poisson independence) has no floor and is the right choice for large
  families. Choose per family size, and state which is in use.
- **A permutation null is only a null if the transform is label-invariant.**
  This applies to a **domain-label** permutation (relabeling items as A vs B),
  not to a pairing permutation. If the design relabels items, then binarization
  and feature selection must not depend on the label assignment: thresholding
  per-domain, or choosing the feature set from the *observed* per-domain rates,
  silently invalidates the null — the selected features sit at the band under
  the real labels while their permuted rates scatter, lifting the observed
  statistic above its own null so the run *looks* like a positive. Threshold on
  the pooled corpus and select on a pooled (label-blind) criterion. Measured
  once: selecting on observed labels gave `T=0.0504` against a null mean of
  `0.0470` with `p=0.0` — an artifact of the selection, not evidence (DEC-028).
  The landed #3 probe permutes **pairing**, which preserves each side's
  marginals, so its selection rule is unaffected; this is a trap for a future
  label-permutation design, not a defect in #3.
- **Constructibility requires a signal-*specific* feature.** Select the feature
  the planted signal moves *relative to baseline* (`with marker` minus `without
  marker`, embedded in neutral text), not the feature with the largest raw
  activation on marker text — a broadly-firing feature wins the latter and its
  rate then varies for reasons unrelated to the injection. Then assert the rate
  rises monotonically with the injection rate. The landed #3 positive control
  already does this (`top_feature_activation_elevation`); recorded here so the
  reasoning is not lost (DEC-028).
- **Correct for multiplicity — with the max-statistic permutation cutoff.**
  With 10^5 features and many prompt pairs, per-pair significance is
  meaningless. **Use the 95th percentile of the per-permutation maximum**
  (family-wise control). **Do not use BH-FDR with a permutation null unless
  `N_PERM >= 1e4`**: with N_PERM=100 over m=6.3e4 pairs the smallest
  achievable p is 0.01 while BH needs 1.6e-6, so *nothing can pass and the
  zero is an artifact* (DEC-016). With an analytic null, BH is fine (DEC-018).
  A 100-permutation 95th percentile is also a noisy null estimate over
  millions of pairs and can yield false positives under the null — check the
  negative control every time.
  Anchor for scale: one study finds only ~25% of highly active features in
  a layer encode genuine task-relevant information (arXiv:2511.11711).
- **Cluster before counting.** Feature splitting means one coherent
  structure can appear as several partially-overlapping features. Cluster
  co-activating features before treating them as independent hits.
- **Rank by surprise, not magnitude.** The field's convention for
  cross-domain candidate ranking is `structural similarity x semantic
  distance`, which prefers candidates that are structurally alike but
  semantically far apart (see PRIOR_ART §8). Raw co-activation magnitude
  prefers frequent, uninteresting features.
- **Record the known confounds.** Same literal token in both prompt sets;
  same sequence position; high-frequency catch-all features (check the
  activation histogram — broad and weak is a red flag); syntactic or
  discourse-marker features. At 160M these may account for essentially all
  cross-domain overlap.
- **Require paraphrase invariance — a co-activation claim is a vocabulary
  claim until proven otherwise.** This is the strongest objection to the
  project's premise and it is detector-side, not a small-model artifact
  (`PRIOR_ART.md` §6). Two controls, both cheap:
  1. **Lexical-shuffle control** — flag a feature only if it survives
     paraphrases with the domain-identifying tokens removed or swapped. A
     feature that fires only on the original wording is a token feature.
  2. **Zero shared tokens** — the two prompt sets should share no lexical
     items at all, and the co-activation must survive that. This is a much
     stricter gate than "unrelated topics" and is what makes a flagged pair
     non-trivial.

  Note this is a *different* filter from the NPMI + semantic-distance screen
  above: that one kills pairs whose **features** are similar, this one kills
  pairs whose **inputs** share surface form. Both are needed.

  Because this gates the interpretation of everything else, the paraphrase-
  invariance probe should be the *first* experiment run, not a later
  validation step.
- **Correlation triages; intervention evidences — with caveats.** The
  intervention literature is weaker than it looks (PRIOR_ART §5). Prefer
  **ablation** over additive steering; require **in-distribution**
  contexts; include an **interference control** (intervening on one SAE
  feature is known to transfer to semantically unrelated features on
  Pythia-70M and GPT-2-small specifically); and treat a *failed*
  intervention as inconclusive rather than as evidence against the feature.
  **Use RAVEL's two-part decomposition** (`PRIOR_ART.md` §11, Q1): a good
  feature both **Causes** the target attribute to change and **Isolates** the
  change (leaves other attributes intact). Carry RAVEL's ceiling as context —
  SAEs scored 48.6/46.8 against 60.1/65.6 for supervised methods, so SAE
  features are measurably worse at isolation than supervised featurizers.
- **The claim a finding actually supports is causal, not mathematical.**
  State it as: feature F is causally load-bearing in both domains A and B, and
  the overlap survives surface-form controls (`PRIOR_ART.md` §11). That claim
  needs no mathematical oracle and is falsifiable. Do not phrase findings as
  though "statistical significance" answers a question about mathematical
  truth — it doesn't, and the question it invites has no answer here.
- **A null result is a result — but check absorption first.** A null may
  mean no cross-domain structure, *or* it may mean the SAE cannot represent
  it. Feature absorption produces false negatives, occurs in every model
  tested, and may be structural to the sparsity objective (arXiv:2409.14507).
  Any null writeup must state this caveat.
- **For numerical or arithmetic inputs, rule out the bag-of-heuristics
  explanation.** Models solve arithmetic with memorized heuristics, not
  algorithms (arXiv:2410.21272), so a math-adjacent co-activation may be
  two heuristics sharing a trigger pattern rather than a shared
  mathematical concept. This is the most likely way for the project to
  produce a plausible artifact.

## Validation layer (adopted 2026-09-19, DEC-021)

**Read [`docs/reference/TEST_VALIDATION_SPEC.md`](reference/TEST_VALIDATION_SPEC.md)
before claiming any result.** It is the adopted authority for Ephapse's
automated validation layer, replacing prose-only discipline. This section is a
pointer, not a substitute.

**The two-tier split, binding, never merged.**

- **Tier 0** — no model load, no torch. Schema, text, and cross-reference
  checks over artifacts (`findings.jsonl`, experiment headers, requirements,
  docs coherence), **plus the `G-C` experiment-code gates**. Runs in CI. 29 of
  the 37 gates.
- **Tier 1** — requires loading the probed model. The detector-validity gates
  (positive control, control-can-fail, null calibration, constructibility,
  frozen parameters, recovered-pair identity, instrument supersession,
  paraphrase survival, causal load-bearing, interference control, site and
  scale). 8 gates.

> **Count history.** DEC-021 recorded "20 of 24" from the spec as committed at
> `26840ed`. DEC-022 added the `G-C` series and raised it to 34. DEC-025 to 36,
> DEC-026 to 37. The largest number is current.

**A tier-0 pass is not "gate passed."** Maith's formulation is exact and
binding here: *"Treating a grep pass as a gate pass is itself an integrity
hole."* A green CI run means the artifacts are internally consistent and their
evidence is present. It does **not** mean a detector measures what it claims —
that is tier 1, and beyond tier 1 it is the human's.

**The fixture rule, non-negotiable.** Every gate ships a fixture that makes it
fail, and the test suite asserts both directions (fires on its violation,
silent on the clean case). A gate that cannot fail is removed, not kept.

**Why this exists, in one line:** four failures in one day — DEC-016 to
DEC-020 — all had the shape *a plausible-looking artifact from a process whose
correctness was never checked*. The permutation null that could never fire; the
positive control that activated neither group; the isolate score that was
trivially 1.0 because nothing had moved.

**The status ladder binds.** A record in `findings.jsonl` is rung 0
(Observed). Rung 1 is tier-0-clean. Rung 2 needs paraphrase survival. **Rung 3
is causal at *per-feature* granularity and is not currently reachable** —
DEC-020 measured 0/50 features above the cause threshold at pythia-70m. Rung 4
is causal at *aggregate* granularity (the cumulative dose-response ladder,
DEC-020) and is the strongest currently attainable causal rung. **The word
"finding" is reserved for rung 3 and above**; rungs 0–2 are observations. Rung
5 (handoff) is not reachable by an agent.

**Declined, so it is not re-proposed:** PleaNP's probe-checklist layer. It
works there because expected answers are machine-derivable from Lean text;
Ephapse has no formal text, so deriving them would insert an unverifiable LLM
step between reviewer and artifact (DEC-021).

## Program management (adopted 2026-09-19, DEC-030)

**Read [`docs/reference/PROGRAM_MANAGEMENT_SPEC.md`](reference/PROGRAM_MANAGEMENT_SPEC.md)
before filing or closing work.** The validation layer above asks *"is this
artifact valid?"* This one asks *"where is the program, and what does it need
next?"* They fail separately, so they are adopted separately.

**Three classification axes, each independent.** A piece of work carries one
value from each.

| Axis | Values | Where it lives |
|---|---|---|
| **Issue kind** | `experiment`, `gate`, `repair`, `defect`, `gap`, `decision`, `protocol` | a `kind:` label, orthogonal to `status:` |
| **Outcome class** | `instrument-validated`, `instrument-failed`, `phenomenon-null`, `phenomenon-present`, `defect-found`, `requirement-emerged` | the program ledger |
| **Rung** | 0–5 (reused verbatim from the validation spec §5) | the program ledger |

**The axis that matters most is the second, and specifically this split:**
`instrument-failed` and `phenomenon-null` both read "no significant result" and
mean opposite things — *the apparatus is broken* versus *the world is empty
here*. DEC-023→025 is the record of this project rediscovering that distinction
three times. If you record a null, say which one it is.

**`kind:decision` is not `status:blocked-needs-input`.** The status says "this is
stopped"; the kind says "this is a judgment, and stopping is correct." A
`kind:decision` issue should not be picked up by an agent however available it
looks.

**The ledger.** `program/ledger.jsonl` (task D, #31) is append-only and holds
**only what GitHub cannot express** — the outcome class, the rung, and the
traversal links between results, findings, and decisions. It does not copy issue
titles, statuses, or priority. GitHub remains the system of record for tasks; a
stored copy drifts, a derived view cannot. Every view in spec §5 is computed.

**Emergent requirements.** Discovering something outside your claimed task is
the normal case. File it, label it, record it under `emergent` in your ledger
entry, and **do not fix it inside the claimed task** — that makes the done
comment unverifiable. An agent filing an emergent issue does not have to solve
it; the discovery is the deliverable. The worked example is #24: it does not
block #11 (closed, and its work corrected) but it does block #15.

**`G-M1`** (task C, #30) enforces one `status:` and one `kind:` per open issue.
It exists because nine violations appeared within a day of the rule being
written down — including one produced by the session that proposed the gate.

## Issue-based task management

Ported from Maith's `docs/MULTI_AGENT_WORKFLOW.md` (itself ported from
PleaNP), which battle-tested it. See `docs/MULTI_AGENT_WORKFLOW.md` in
this repo for the full protocol. Summary:

- Status labels: `status:available` / `status:claimed` / `status:done` /
  `status:blocked-needs-input`.
- **Run-ids**: every agent session generates
  `<YYYYMMDD-HHMM>-<4 random alphanumerics>` at session start and includes
  it in every claim/done/blocker comment. All agents share one GitHub
  identity, so labels and assignees cannot distinguish claims — the
  run-id is what makes the re-fetch ownership check work.
- Atomic claiming: swap the label and self-assign in one edit, then
  **re-fetch and read the latest claim comment**; if the run-id isn't
  yours, a sibling won and you back off.
- One claim per agent at a time.
- Stale-claim sweep: a claim older than 1 hour with no activity reverts to
  `status:available`. **Ephapse-specific caveat:** NDIF queue waits and
  cold model downloads can legitimately exceed this. If you're blocked on
  a remote queue, post a heartbeat comment rather than losing the claim.
- Single active branch: **`dev`**. State it in the README on day one —
  Maith's DEC-036 adopted this after parallel branches sprawled.
- Every experiment (not just every code change) gets an issue and a
  logged result, positive or negative — mirrors Maith's ledger discipline
  of recording failures as informative, not just successes.
- Dependencies use GitHub "blocked by" relationships. A task becomes
  available only when every blocker is `status:done`.

## Where the method stands — read `docs/ROADMAP.md` first

If you are picking this repo up and wondering what to work on, read
[`docs/ROADMAP.md`](ROADMAP.md) before the issue queue. It is the **verdict-
revision rung ladder** (adopted DEC-033) and it states, for each rung, what the
project is testing, what it costs, and what would falsify it.

Summary as of 2026-09-19: rungs 0–2 are **done** (detector validated;
surface-controlled signal weakly positive; general cross-domain probe a clean
null, DEC-027). **Rung 3 — sensitivity at scale — is the single live rung**, and
it is *feasible, not blocked*: `gemma-2-2b` has 316 SAEs in the Gemma Scope
residual release, ~28× the current parameter count. Rung 4 (causal reachability)
depends on rung 3. Rung 5 (interestingness) is explicitly a human step with **no
falsifier** — a rung without one is appropriate only when it is a human judgment.
Rung 6 is the Maith handoff and is not this repo's to reach.

**Foreclosed at every rung, so it does not need re-arguing.** This project does
not certify novelty and does not produce commercial assets. An external spec
proposing a B2B "Innovation Asset Inventory" was reviewed and rejected on this
repo's stated position (DEC-033,
[`EPHAPSE_SPECIFICATION_ASSESSMENT.md`](reference/EPHAPSE_SPECIFICATION_ASSESSMENT.md)).
Two ideas from it were rolled in (the "frictions obliterated" framing, PRIOR_ART
§11) and three postponed with stated conditions (the vault, hotspot search,
feasibility grading) — do not re-propose the rejected parts as new.

## Repo scaffolding (minimal — this is proof-of-concept stage)

```
README.md             — scope, non-goals, compute constraints, link to this doc
requirements.txt      — transformer_lens, sae-lens, torch (CPU build)
experiments/          — one file or notebook per experiment, dated, with a
                        short header stating model, inputs, and what's being
                        tested
findings.jsonl        — append-only log: one record per co-activation event
                        flagged, with model/layer/feature/inputs/activation
                        values. No conclusions field — observations only.
docs/
  AGENT_HANDOFF.md    — this document
  MULTI_AGENT_WORKFLOW.md — full claiming/run-id/dependency protocol
  decisions/LOG.md    — decision log (DEC-0xx)
  reference/SANDBOX_BASELINE.md — measured sandbox numbers + evidence
```

Do not build a full pipeline (proposal generator, automated gate-checker,
promoted-findings database) before a single co-activation event has been
found and reviewed by a human. This repeats a mistake already made once in
Maith's own history (infrastructure built ahead of any result to justify
it) — don't repeat it here at a smaller scale.

## Immediate first issues

1. **Verify sandbox infrastructure and record the numbers.** Disk quota and
   free space, network egress to huggingface.co, RAM headroom after loading
   a small model plus TransformerLens overhead (not just parameter count).
   Log the actual numbers, not just pass/fail — later issues need them to
   size experiments. A partial baseline already exists in
   `docs/reference/SANDBOX_BASELINE.md`; this issue confirms it and fills
   the gaps (e.g. actual quota vs. observed free space).
2. **Set up TransformerLens + SAELens against Neuronpedia's hosted
   features.** **Done 2026-09-18** (run `20260918-1720-altu`, commit pending
   at time of writing; see the issue). Outcome: the toolchain works end to
   end at `pythia-70m-deduped` / `blocks.3.hook_resid_post`, and the target
   model was corrected — there is **no Pythia-160M SAE release**, so 160M is
   not usable (DEC-014). Blocked on issue 1 (closed).
3. **Validate the detector with an injected positive control.** Inject a
   known cross-domain co-activation into a background corpus and measure
   the recovery rate as a function of injection rate, per
   `docs/reference/PRIOR_ART.md` §2. This must run *before* the real probe,
   because the probe's interpretation depends on the detector's measured
   sensitivity — a null from an unvalidated detector is uninterpretable.
   Blocked on issue 2.
   **DONE 2026-09-18 — the pass stands, on one instrument; a second
   instrument was tried and is retired.** Adjudicated in DEC-024 from the
   committed result files, after two concurrent sessions reached opposite
   verdicts.

   - **The analytic-null control stands** (run `20260918-2332-e7c4`,
     DEC-018/019). It recovered the injected correlation at 0.868 (rate 0.20)
     and 0.895 (rate 0.40), with a naive raw-co-occurrence baseline recovering
     **zero** at every rate, and no false positives on the negative control.
   - **The max-NPMI + permutation-null variant is retired** (DEC-023). Re-run
     under per-feature thresholds it did not replicate: `best` was identical
     (0.6322) with and without injection at every rate, so the top-ranked pair
     was never the injected pair, and the negative control produced false
     positives. It is **not** a failed model result — it is an instrument that
     cannot resolve the family it was pointed at. Root cause (DEC-024): a
     max-statistic over an unbounded ~7.5M-pair search is governed by the
     noisiest pair, and a permutation null at N_PERM=100 cannot resolve that
     family. Use a **pre-specified, bounded** pair set.

   **Consequence for #3 and #6, and the reason this is recorded as a design
   constraint rather than a caveat:** a positive control must (a) demonstrate
   the planted signal actually moves the selected features — constructibility,
   DEC-019 — and (b) use a pre-specified bounded pair set rather than an
   unbounded search, DEC-024. A recovery curve alone does not distinguish a
   working detector from one tracking an unrelated high-frequency pair, which
   is exactly what the retired variant did.

   Four earlier runs returned zero for reasons unrelated to detector
   sensitivity — catch-all feature groups, an inverted p-value that could never
   reject, and a control that activated neither group. All four are recorded in
   DEC-019 because each produced a plausible-looking negative.
4. **Establish paraphrase invariance.** Zero shared lexical items between the
   two prompt sets, plus a lexical-shuffle control, per
   `docs/reference/PRIOR_ART.md` §6 and DEC-011. Promote this *ahead of* the
   general cross-domain probe: a flagged co-activation is a vocabulary claim
   until surface form is ruled out, so running the general probe first would
   produce results whose interpretation depends on an untested assumption.
   A negative result here is informative and likely — it would mean the
   detector is reading tokens, not relations, and it should be recorded with
   the same care as a positive one. Blocked on issue 3.
   **DONE 2026-09-19 (issue #6, run `20260919-0213-tsm5`, DEC-023).** Weak
   but real bridging on verbal-vs-symbolic renderings of the same relation:
   **6 matched survivors vs 0 under permutation**. The paraphrase arm
   survives at 17. Two detector bugs were found and fixed in the process
   (a pooled threshold that disabled the detector; prompts too short at 5
   tokens — usable features rise 541 -> 1188 from bare prompts to passages).
   Both bugs produced plausible-looking negatives before they were caught.
5. **Design one small, well-defined cross-domain probe** — two sets of
   prompts from genuinely unrelated topics, scored for co-activation above
   baseline, with the paraphrase controls from issue 4 in place. The null
   model, positive control, multiplicity correction, NPMI + semantic-distance
   filter, and confound checklist from "Method notes" must be fixed *before*
   the run. This is a methodology proof-of-concept, not a math-discovery
   attempt. Blocked on issue 4.
   **DONE 2026-09-19 — NEGATIVE** (run `20260919-0229-to3m`, DEC-027). 120
   cooking and 120 astronomy passages with a **mechanically verified zero
   token-id intersection**. Positive control recovers (planted token, best
   z **11.30** vs cutoff **4.47**); real run **0 survivors** (|family| 793,
   best z **3.10** vs cutoff **4.41**). A clean, interpretable null — the
   legitimate done state the issue named. A **raw co-activation-rate
   family-max cutoff is retired**: it could not be cleared by a 10% injected
   signal (0.3417 vs 0.3750) because high-firing features co-fire at ~0.37 by
   chance (DEC-016's structural failure in a new place); standardizing per
   feature fixed it. Whether the null is SAE representational limits or
   genuine absence is not resolved (feature-absorption caveat, PRIOR_ART §4).
6. **Add a causal positive control using interchange intervention.** Patching
   is cheap here (~217 ms per forward pass, so hundreds of interventions are
   minutes of compute) and needs no mathematical ground truth. Score candidate
   features on RAVEL's two properties — **Cause** (intervention changes the
   target attribute) and **Isolate** (it leaves other attributes intact) — per
   `PRIOR_ART.md` §11 Q1. This converts "F is active in both domains" into
   "F is causally load-bearing in both domains," which is the strongest claim
   this repo can support on its own.
   **DONE 2026-09-19, two independent runs** (DEC-020 and DEC-025). The two
   disagree and both are right — the result is **site- and scale-dependent**.
   At the **final token** on a **probability** scale, 0/50 features clear a 0.01
   threshold (DEC-020: use the cumulative ladder for aggregate questions). At
   the **country token** on a **logit-difference** scale, mean **Cause 0.75**
   for 4 attribute-selective features, interference control **0/240**. Mean
   Δ probability is 8e-4 at either site, so the effect is real on the logit
   scale and invisible on the probability scale. **Isolate is the negative
   that survives: mean 0.208, 3 of 4 features fail context isolation**,
   reproducing RAVEL's ceiling (SAE 48.6/46.8 vs 60.1/65.6). Reporting rule
   from DEC-025: every intervention result states its site and scale. An entity
   feature can be causally load-bearing *without* keeping the domains apart, so
   #3 must report the causal and semantic results together.
7. **Log the result in `findings.jsonl` regardless of outcome** — a null
   result (no meaningful co-activation found) is informative about whether
   this method works at all at this model scale, and should be recorded
   with the same care as a positive one — with the feature-absorption
   caveat stated (`PRIOR_ART.md` §4). Records should carry the **causal**
   claim, not a mathematical one (`PRIOR_ART.md` §11).
   **DONE 2026-09-19.** Records now exist for #5 (positive control and its
   non-replicating rerun), #6 (weak bridging), #7 (causal positive control),
   and #3 (the clean null). Each carries its null model, correction, family
   size, confound checklist, and the feature-absorption caveat where a null
   is involved.

**Optional, if the detector needs a ground-truth panel:** train and evaluate
against SynthSAEBench-16k (`PRIOR_ART.md` §11 Q2), which supplies 16,384
ground-truth feature directions with hierarchy, correlation, and superposition,
and extends the SAELens this repo already uses. Two conditions: confirm CPU
feasibility first (the paper assumes a single GPU), and carry the ceiling — the
best SAE tested reaches probing F1 0.88 vs 0.974 for a logistic-regression
probe, so no SAE recovers ground truth cleanly.

**The first "search for novel math" experiment is now unblocked in principle
but not advised.** Issue 5's signal-to-noise has been assessed: at
`pythia-70m-deduped`, with a validated detector and token-disjoint domains, the
cross-domain probe returns a null (DEC-027), bridging is weak (DEC-023), and
single-feature causal isolation mostly fails (DEC-020/DEC-025). A search for
novel math on top of this signal-to-noise would be reading noise. The ladder
from DEC-020 is the aggregate instrument that performed; a larger model with a
narrower intervention (DEC-020's stated conditions) is the prerequisite.
