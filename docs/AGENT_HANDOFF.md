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
- **The probed model** (a small open-weight model such as Pythia-70M to
  ~410M) — downloaded separately via HuggingFace and loaded locally,
  in-process, inside the sandbox. This is the only kind of model
  TransformerLens/SAELens can actually instrument. It has nothing to do
  with which LLM is powering the agent.

- **The remote probing API** (Neuronpedia, and nnsight/NDIF for larger
  models) is a **third path, not a smaller local one.** It runs the model
  and SAE on someone else's GPU and returns only a result: top-k
  activations, or a feature's decoder vector. You get no arbitrary
  activation matrix, so you cannot compute a full PMI/FDR sweep through
  it. Its binding constraint is **rate limit**, not sandbox RAM. Use it
  for targeted validation of a feature that already looks interesting;
  use the local path for exploration.

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
  Pythia-160M in fp32 peaks at **2.65 GB RSS**; Pythia-70M at **1.52 GB**.
  The doc's older "24GB" figure was wrong — do not size against it.
- **CPU**: 4 cores. Pythia-160M forward pass ≈ **217 ms/call** (one core);
  Pythia-70M ≈ **121 ms/call**. This is the real ceiling on experiment
  size: a 2,000-prompt sweep at 160M is ~7 minutes of pure forward-pass
  time before any SAE overhead.
- **Disk**: 55 GB free on `/`. Pythia-160M checkpoint ≈ 1.1 GB in the HF
  cache. Separate budget from RAM, but not currently tight.
- **Network egress**: huggingface.co, neuronpedia.org, and pypi.org were all
  reachable (HTTP 200) from the sandbox. Egress is not currently
  allowlist-restricted, but confirm before designing an experiment around
  a new host rather than discovering this mid-task.
- **Model size ceiling**: the doc's "70M–1B" is directionally right but the
  mechanism matters. TransformerLens loads **fp32 by default** (hence
  160M → 2.65 GB). With dtype control (fp16) and no autograd, ~1–2B
  params is feasible in 13 GiB. So: don't declare something "blocked"
  purely on parameter count — state the dtype and whether hooks cache
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
count when picking a target. GPT-2-small and the Pythia suite have the
deepest pretrained-SAE coverage on Neuronpedia; pick from those rather
than choosing a size and hoping an SAE exists.

## Method notes (read before designing issue 3)

Cross-domain co-activation is expected to fire *a lot*, for reasons that
are not interesting. The filter has to be specified before the run, or
`findings.jsonl` fills with noise that looks like signal.

- **Specify the null model first.** Pointwise mutual information between
  binary feature activations, or a co-activation z-score against a
  permuted-input baseline. The choice must be recorded in the finding.
- **Correct for multiplicity.** With 10^5 features and many prompt pairs,
  per-pair significance is meaningless. Use BH-FDR or a permutation null
  over the whole feature × pair matrix, and record N and the correction.
- **Record the known confounds.** Same literal token in both prompt sets;
  same sequence position; high-frequency catch-all features (check the
  activation histogram — broad and weak is a red flag); syntactic or
  discourse-marker features. These are the dominant false-positive
  sources at small model scale, and at 160M they may account for
  essentially all cross-domain overlap.
- **Correlation triages; intervention evidences.** A feature that fires on
  both domains *and* whose ablation/steering changes behavior on both is
  the signal worth handing to a human. Co-activation alone is not.
- **A null result is a result.** At this scale, "the interesting-looking
  overlaps were surface artifacts" is a likely and fully legitimate
  outcome, and it should be recorded with the same care as a positive one.

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
   features for a Pythia-70M or -160M model.** Confirm the toolchain works
   end to end in the sandbox, and confirm the Neuronpedia API shape
   (`/api/search-all` payload is currently unconfirmed — the feature
   endpoint `/api/feature/{model}/{sae}/{index}` is confirmed working).
   Blocked on issue 1.
3. **Design one small, well-defined cross-domain probe** — two sets of
   prompts from genuinely unrelated topics, checking whether any SAE
   feature co-activates across both sets more than a random baseline.
   The null model, multiplicity correction, and confound checklist from
   "Method notes" must be fixed *before* the run. This is a methodology
   proof-of-concept, not a math-discovery attempt. Blocked on issue 2.
4. **Log the result in `findings.jsonl` regardless of outcome** — a null
   result (no meaningful co-activation found) is informative about whether
   this method works at all at this model scale, and should be recorded
   with the same care as a positive one.

Do not attempt a "search for novel math" experiment until issue 3 has run
at least once and the method's basic signal-to-noise has been assessed.
