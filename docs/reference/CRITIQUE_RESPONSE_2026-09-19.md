# Evaluation of the external critique (2026-09-19)

**Status:** reference. Input to DEC-034. The two adopted items are actioned by
issues #37 and #38; everything else is recorded as not-adopted with reasons.

**Source.** An externally-authored, AI-generated audio critique of this
project's narrative write-up, supplied as a transcript (`.srt`). Round-trip
material — it critiques a *narrative* document, not the repo, and it has not
read the decision log.

**Method.** Every claim was checked against the repo before disposition.
That checking is the point of this document: two of the critique's load-bearing
claims did not survive contact with the tree.

---

## 1. What the critique got right

**1.1 The scale constraint is real.** Surface-level artifacts dominate at 70M and
limit legible semantic overlap. This is the repo's own conclusion
(`PRIOR_ART.md` §6), not a new one; the critique is agreeing and pressing on what
to do about it.

**1.2 The cohort of pivot targets is the repo's own.** Task-trained/grokking
models (`PRIOR_ART.md` §7) and synthetic ground-truth models (§11 Q2) are both
already recorded. The critique recommends moving them from "later" to "now" —
a **priority argument, not a discovery**, which is why it is dispositioned as a
priority question rather than adopted as a finding.

**1.3 The comparator-baseline gap is genuine — and the one real contribution.**
See §3.

**1.4 The pristine-data over-optimization risk is correctly raised and correctly
answered** by the critique itself: an instrument that cannot see a planted
pristine signal has untrustworthy readings on messy data regardless. Sound, and
consistent with DEC-019's constructibility precondition.

---

## 2. What did not survive checking

**2.1 "Biological hypothesis" is a misframing, and it is load-bearing.** The
critique calls the target a "biological hypothesis" throughout. The repo's
subject is **mathematical** structure (`README.md`); the neuroscience reference
is the project's *name*. The closing phrase — "even if the primary biological
hypothesis remains null" — silently changes what a null means. A null here is a
claim about whether a *method* can surface candidate mathematical structure from
activations.

**2.2 "Hard compute wall" names the wrong constraint.** The binding constraint is
SAE **availability** plus iteration latency, not raw compute (`DEC-014`;
`AGENT_HANDOFF.md`: no Pythia-160M SAE release exists, and the handoff explicitly
warns against declaring something blocked on parameter count alone). DEC-033
*measured* the correction by querying the registry: `gemma-2-2b` has 316 SAEs.
Adopting the critique's diagnosis would point the fix in the wrong direction.

**2.3 The AxBench numbers are not in the repo.** The critique states that "the
material openly admits" SAEs underperformed simple probes at 0.695 vs 0.940
AUROC. Verified: no `AxBench`, `0.695`, or `0.940` anywhere in `docs/` or
`README.md`. Those figures came from a **narrative companion document**, which
the critique mistook for the repo's own prior-art review.

This is a real sourcing error with a real consequence, and it is the same class
as DEC-015 (an API contract assumed from its shape): **a premise can enter a
project because it looks reviewed when it is not.** The fix is not to reject the
argument — the numbers are accurate to the literature — but to *review and cite
them properly first*. That was done as part of DEC-034, and they now live in
`PRIOR_ART.md` §3a.

**2.4 "38-gate specifications" is wrong, and the discrepancy is a repo defect.**
The repo says **37** in four places and **38** in a fifth
(`PROGRAM_MANAGEMENT_SPEC.md:16`); 9 are wired. Three circulating figures is
exactly the drift **G-R4** (issue #20) exists to catch — and #20 is unwired, so
nothing detects it. Folded into #38.

**2.5 Transcription artifacts.** The transcript renders the project as "AFAPS" /
"EppsApps", the model as "PTS 70MD-DUTE", grokking as "rocking", constructibility
as "constrictibility", sparsity as "sparse city", and Hendrycks as "Hendrix".
Not carried into repo text.

---

## 3. The one substantive contribution: comparator baselines

**The gap.** `PRIOR_ART.md` §4 carries the absorption caveat: a null may mean "the
SAE cannot represent the structure" rather than "the structure is absent." As
written that caveat is a **disclaimer** — every null writeup must state it, and
nothing measures it. The repo nowhere proposes running a simple supervised
baseline alongside the SAE, so the pipeline cannot answer *"would a cheaper,
non-sparse method have found this overlap the SAE missed?"*

**Why the repo missed it.** §5 and §11 Q1 carry RAVEL's ceiling
(SAE 48.6/46.8 vs supervised 60.1/65.6), which looks like the same result. It is
not: RAVEL measures **isolation**, not **detection**. A project tracking only
RAVEL would have no reason to add a detection comparator.

**The grounding, now recorded.** AxBench (arXiv:2501.17148, ICML 2025):
difference-in-means 0.942, linear probe 0.940 mean AUROC, vanilla SAE **0.695**.
Partial rebuttal carried (arXiv:2605.31183): SAEs reach parity *with a supervised
feature-selection pipeline* — i.e. when machinery is added around them. Fair
statement: **vanilla SAEs lose to trivial baselines at detection**; not "SAEs are
useless."

**The experiment this enables.** The gating test is paraphrase invariance (#6,
DEC-011). Running the same inputs through both substrates gives a two-sided
result:

- probe detects a bridge the SAE misses → **the instrument, not the scale, is the
  bottleneck** — actionable at this budget;
- both miss it → the surface-form explanation gains independent support from a
  non-sparse method, strengthening the rung-2 null against the objection that it
  is an SAE artifact.

**The limit, stated so it cannot be over-read.** A probe yields a *direction*, not
an enumerable interpretable feature with a decoder vector. The SAE's purpose is
the feature list. A comparator is a **sensitivity check on the detector**, not a
substitute substrate.

**Adopted:** DEC-034 item 1, issue #37.

---

## 4. The repositioning: validation layer as first-class output

**The argument.** The critique holds that the validation framework — stated as a
~40-gate, fixture-gated, two-tier method with an `instrument-*` / `phenomenon-*`
vocabulary — is "arguably the project's most significant, ready-to-ship
contribution," and that the current narrative treats it as secondary support for
the co-activation hypothesis. That is a fair reading of the repo's own framing.

**Why it is defensible on the repo's evidence.** `PROGRAM_MANAGEMENT_SPEC.md` §3.2
already names separating `instrument-failed` from `phenomenon-null` as "the
load-bearing decision." DEC-023 → DEC-024 → a third entry exist because that
distinction had to be adjudicated once, at cost. Five measurements produced
plausible-looking results that were artifacts of vacuous code (DEC-019, DEC-020).
The layer is expensive, rare, and transferable to anyone probing small models.

**Adopted:** DEC-034 item 2, issue #38.

**The boundary, which is binding and is what makes this adoptable.** Repositioning
an existing asset is **not** building infrastructure. The decision asserts what
the work *is*; it authorizes no new machinery. `README.md`'s "What not to build
yet" is unchanged, and DEC-012's and DEC-033's rejections stand.

---

## 5. Declined, with reasons inherited rather than re-argued

| Critique item | Disposition | Reason |
|---|---|---|
| Pivot to grokking models as the immediate target | **Priority question, not adopted** | Already recorded as a future direction (`PRIOR_ART.md` §7). Unstated cost: the target has **no pretrained SAE**, so one must be trained. |
| Synthetic ground-truth panel (SynthSAEBench) | **Already on the optional track** | `PRIOR_ART.md` §11 Q2. Carries its own ceiling (best SAE F1 0.88 vs 0.974 probe), so it cannot validate an SAE pipeline outright. |
| **Extract the ~37 gates into a standalone library** | **Declined** | The concrete gates check repo-local conventions — `findings.jsonl` schema (`G-E*`), experiment headers (`G-R1`), `requirements.txt` pinning (`G-R3`), *this* tokenizer's disjointness (`G-P2`). They do not generalize. Only the *pattern* does — a separate, smaller question, not authorized by DEC-034. |
| Run paraphrase test through both substrates | **Adopted** | Follows from the comparator decision; it is the concrete experiment. |
| Hendrycks-style scepticism motivates substrate-swapping | **Adopted as motivation, with care** | Valid, but "we can swap substrates" is a robustness claim, not evidence the current substrate is sound. Must not be phrased as a rebuttal to Hendrycks. |
| Pristine-data over-optimization risk | **Noted; resolved by the critique itself** | No action. |

### Why "extract the library" does not transfer cleanly

This is the critique's most appealing practical suggestion and it is the one that
most directly collides with the repo's own record. `README.md`:

> No proposal generator, no automated gate-checker, no promoted-findings
> database — not before a single co-activation event has been found and reviewed
> by a human. Maith built infrastructure ahead of any result once already and had
> to justify it afterward.

And DEC-012 declined a whole sibling project on the same reasoning. "Extract and
generalize the library" reads as *build more validation infrastructure before any
result exists* — the named failure mode. The distinction that saves the
repositioning (item 2) is that it is a **statement about existing assets**,
whereas extraction is **new construction**. The critique does not engage with
this, and a reader could reasonably take its recommendation either way.

If the pattern is ever written up, it should be scoped as *principles plus one
worked example*, with generalization explicitly refused as deliberate discipline —
not as a framework.

---

## 6. Verdict

The critique is **well-aimed on one point and derivative on most others**.

- Its genuine contributions are the comparator-baseline proposal (§3) and the
  repositioning of the validation layer (§4). Both are adopted.
- The rest is already-recorded material, a priority argument that belongs in
  `docs/ROADMAP.md`'s rung ordering, or the infrastructure-ahead-of-results move
  the repo has twice rejected.
- Two load-bearing claims did not survive checking: the "38-gate" figure (a repo
  inconsistency, now folded into #38) and the AxBench numbers (absent from the
  repo; introduced by a narrative document and mistaken for the repo's own
  review — now properly cited in `PRIOR_ART.md` §3a).

The most useful thing about it is that it arrived independently at the repo's own
central unresolved question: **is the bottleneck the instrument or the model
scale?** The comparator baselines of #37 are the cheapest experiment that could
answer it.