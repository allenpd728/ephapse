# Ephapse — Test & Validation Spec

**Status:** **adopted**, 2026-09-19 (DEC-021). Drafted 2026-09-18 (run
`20260918-2347-0201`). This document is now the authority for Ephapse's
automated validation layer; it was adopted by decision-log entry, as it
specified.

> **Definition of Done note (issue #8).** The issue's check has two clauses:
> the spec must be referenced from the decision log and the handoff (it is,
> both), and the status line above must no longer read as a draft (it does not).
> The second clause was originally written as a whole-file grep for a word that
> also appears in two unrelated senses in §3 and §8; those phrasings were changed
> to "candidate generator" / "No gate-checker for candidates" so the whole-file
> grep is unambiguous. Recorded because a DoD check that fires on the wrong
> thing is the same class of defect as a gate without a valid fixture (spec §4).

**Purpose.** Ephapse has no automated validation layer of any kind — no CI, no
test suite, no gate scripts. Its process discipline is written entirely in
prose (`docs/MULTI_AGENT_WORKFLOW.md`, `docs/AGENT_HANDOFF.md`) and enforced by
agent discipline alone. This document specifies the automated validation layer
that should exist, and how it should be built without repeating the mistake
both sibling projects made.

**Read first.** `docs/MULTI_AGENT_WORKFLOW.md` § Gates (done-evidence) defines
what a human should already require. This spec turns as much of that as is
mechanically checkable into code.

---

## 1. Why this exists now — four failures in one day

The scaffolding itself is deliberately minimal, per README's "What not to build
yet". That stance is about *research* infrastructure — a candidate generator, a
gate-checker, a promoted-findings database. A validation layer over artifacts
that already exist is a different thing, and the case for it is not
speculative: the repo's own first two sessions produced four defects that a
mechanical check would have caught, each recorded against the process rather
than against the person who made it.

| # | Defect | Evidence in-repo | Class |
|---|---|---|---|
| 1 | Three experiment files disagree with pinned deps on the model | `2026-09-18-latency-vs-batch.py` and `-sandbox-baseline-hooked.py` both load `pythia-160m`; `experiments/README.md` and DEC-014 settle `pythia-70m-deduped` | stale artifact |
| 2 | `experiments/README.md` mandates six header fields; none of the three shipped files has them | `experiments/README.md` § Header vs. the three files' docstrings | unenforced rule |
| 3 | The model choice was made from a plausible range, not a catalogue query, and was wrong | DEC-014; handoff § "Which models actually have SAE coverage" | unverified premise |
| 4 | A prior-art claim was written from field *names*, not a response, and was wrong | DEC-015 (`hasVector` false, `vector` empty); DEC-003 superseded | unverified premise |

Defects 1–3 are mechanical and checkable in seconds. Defect 4 is the one that
generalizes: an API contract was assumed from its shape. A validation layer
cannot prove a claim is true, but it can refuse to accept a claim whose
supporting artifact was never produced.

**What is *not* the motivation.** This is not a step toward the "automated
gate-checker" README warns against. That warning is about deciding whether a
*candidate is mathematically interesting* — a judgment no checker can make. No
task in this spec claims that. Every gate here checks that evidence was
produced, recorded, and internally consistent. The human gate stays exactly
where it is.

### The fifth defect class, and it is the one that matters

This spec was drafted before issues #5 and #7 ran. Its first version gated only
**artifacts** — findings records, experiment headers, docs. Those runs then
demonstrated that the dominant failure mode is one step earlier, in the
experiment **code**, and none of the original gates would have caught it.

Four consecutive #5 designs produced plausible-looking negative results for
reasons that had nothing to do with the phenomenon (DEC-019). Each was found
by running, not by review:

1. Catch-all feature groups — a marginal already at 1.0 cannot rise, so the
   statistic is structurally bounded below threshold.
2. A band ceiling that still left the statistic bounded.
3. Groups that never fire on the planted text — the control was never shown to
   be **constructible**.
4. An inverted survival function (`gammaincc` where `poisson.sf` was needed),
   returning 1.0 for every pair. Detection that "fired" was the mask alone.

Every one of these is a **vacuity** defect — a reading that cannot come out
low, or a test that cannot fire — and every one is mechanically detectable.
The same class recurred in #7: the isolate score read `0.996` across all 50
features, computed entirely from cases where nothing had happened (DEC-020).
DEC-019's own formulation is the general rule: *a check that cannot fail is not
a check*, applied to the control and the code, not just the metric.

So a gate inventory over artifacts alone is insufficient. §3's code-gate series
(`G-C`) is the response, and it is the highest-value part of this layer —
higher than CI wiring, higher than the findings schema, because it is the only
part that catches the failure mode this repo has actually hit five times.

**The defensible claim in hindsight.** The original version of this spec said,
in §4: *a gate without a failing fixture is assumed broken*. That principle, if
applied to the experiment code rather than to the gate scripts, would have
caught failures 1–4 at design time. The gates were pointed one level too high.
That is the correction this revision makes.

---

## 2. What is borrowed, what is new, what is rejected

The obvious move is to port Maith's gate pattern — it is ported from PleaNP and
battle-tested across two repos. The problem is that Maith's gates are all
statement-level (Lean hygiene, vacuity, binder lethality). Ephapse's validation
object is a *measurement process*, so the gate inventory cannot port. Three
adjacent reference docs can, and one should be explicitly declined.

| Reference | Borrow | Why |
|---|---|---|
| Maith `EXPERIMENT_MEASUREMENT.md` § "Measurement Validity via Prior-Art Alignment" | **The central test idea** | Maith's answer to "is the apparatus working?" is: *does every result land where prior art predicts for these conditions?* Noise would indicate breakage; convergence at predicted coordinates is the evidence. Ephapse has the equivalent — its own prior art predicts a **null**, an **absorption-limited** null, and **token-shaped** detector output. If a run returns a strong positive, that is the surprising event and should be treated as suspect, not celebrated. |
| Maith `PIPELINE_QUALITY_GATES.md` (production-line metaphor) | **Structure** | Stations with a gate between each, so a defect is caught at the station that produced it. Ephapse's failure #1 was exactly a downstream artifact built from an upstream value that was never checked. |
| Maith `tooling/gates/README.md` + `tests/case*.lean` | **The fixture rule** | Every scanner ships fixtures proving it detects what it claims. Maith's own note: *"a check that cannot fail is not a check"*, with the admission that their first exit-code verification **was vacuous** (`str.replace` silently no-oped on a missed anchor) — so the probes now assert their mutation applied. |
| PleaNP `VALIDATION_SUITE.md` § three requirements | **The three-category shape** | Must-prove (known truths the system must reproduce), must-refute (the absurdity it must exclude), smoke tests (concrete executables with decided outcomes). |
| PleaNP `STATEMENTS/HUMAN_REVIEW_LAYERS.md` § the irreducibility argument | **The human layer's scope** | The argument that one human step is irreducible, and every other layer must absorb ambiguity so the human is never the tiebreaker. |
| Maith `docs/reference/EXPERIMENT_MEASUREMENT.md` § "Automated Prevention" | **Map each gate to a documented concern** | Every gate traces to a specific validity gap, stated in advance. |
| Maith `TOOLCHAIN_AND_CI.md` | **Pins, two tiers, single dev branch** | Already partly present (`requirements.txt` is pinned); the two-tier split maps cleanly onto "no model load" vs "model load". |
| Maith `EXPERIMENT_MEASUREMENT.md` § "Measurement Validity via Prior-Art Alignment" | **The prediction-before-run discipline** | Maith's guard against post-hoc rationalization is that predictions were recorded *before* the experiments. DEC-018 applies the same move to the control's parameters. |

### Rejected: PleaNP's probe checklist

PleaNP's Layer 3 turns a claim into 3–5 single-choice probes for a
non-Lean-writing reviewer. It is a genuinely good design *for formal
statements*: lean enough that one wrong answer decides it, and the reviewer
never adjudicates prose.

It should **not** be ported here, and the reason is worth recording so it is
not re-proposed. Probe checklists work because the expected answers are
**machine-derivable from the formal text** — `statement_lint.py` computes
quantifier order, direction, and bound from the Lean syntax. Ephapse has no
formal text. It has activation statistics and a prose claim. Deriving "expected"
answers would mean asking an LLM what the claim means, which places an
unverifiable step between the reviewer and the artifact — the exact
Pattern-A failure (`PleaNP/FAILURE_AUDIT.md`) where the check confirms the
author's recollection rather than the artifact's content.

Where the human-review reasoning *does* transfer is its **shape**: prefer one
crisp check on a rendered artifact over asking a human to weigh subtle prose.
Ephapse's rendering of that is a done-comment block that mechanically
corresponds to `findings.jsonl` fields, so the human diff is a diff, not a
reading comprehension task (§7).

---

## 3. The production line

Ephapse's stations, with the artifact each produces and the gate that
validates it before anything downstream consumes it.

```
Stage 0        Stage 1          Stage 2        Stage 3         Stage 4
Prompt sets → Detector      →  Findings    →  Evidence     →  Repo
+ corpus      measurement      claims         record           integrity

             G-D1..G-D4       G-F1..G-F4     G-E1..G-E8      G-R1..G-R5
```

Stage 4 is deliberately last and deliberately cheap: it is where failures #1
and #2 above live, and both are pure-data checks that need no model.

### Gate inventory

Every row maps to a documented concern. `tier` is 0 (no model load, no torch —
runs in CI) or 1 (requires loading the probed model).

| Gate | Checks | Traces to | Tier |
|---|---|---|---|
| **G-P1** | Prompt set integrity — both sets listed in full, count `N` recorded, provenance stated | issue #3 DoD 1 | 0 |
| **G-P2** | Zero-shared-token verified **mechanically** — token-ID set intersection on the target tokenizer, not string matching; intersection size recorded | DEC-011; issue #6 DoD 1 | 0/1 |
| **G-P3** | Domain unrelatedness asserted in writing *before* the run, timestamped | issue #3 DoD 1 | 0 |
| **G-P4** | Split disjointness — no prompt appears in both sets | Maith G3-1 analogue | 0 |
| **G-D1** | Null model fixed and recorded **before** the run; header mtime precedes result mtime | DEC-005; workflow § Gates | 0 |
| **G-D2** | Multiplicity correction named **and arithmetically capable of firing** at this N and m — the DEC-016 check | DEC-005, **DEC-016**; workflow § Gates | 0 |
| **G-D3** | Positive control present: recovery-vs-injection curve at ≥3 rates, including a near-zero rate | DEC-007; PRIOR_ART §2 | 1 |
| **G-D4** | Control can fail — recovery at the near-zero injection rate is *not* 1.0 | fixture rule; **DEC-019** | 1 |
| **G-D5** | Null calibration — on un-injected background, flagged count falls inside the band the correction predicts | PRIOR_ART §3 | 1 |
| **G-D6** | Sensitivity floor stated numerically; every downstream null cites it | DEC-007 (interpretability) | 0 |
| **G-D7** | **Constructibility** — the planted signal is shown present in both groups by construction, before recovery is interpreted | **DEC-019** | 1 |
| **G-D8** | Injection/threshold/rate-grid parameters committed **before** the run; result artifact is not a reshaping | **DEC-018** | 0 |
| **G-D9** | **The recovered pair is the injected pair** — not merely a pair above cutoff. A statistic whose top-ranked pair is identical with and without injection has not detected anything | **DEC-023, DEC-024, DEC-026** | 1 |
| **G-D10** | Supersession — a retired or superseded instrument is cited as such wherever its results were reported | **DEC-024, DEC-026** | 1 |
| **G-F1** | Paraphrase survival — lexical-shuffle and/or zero-shared-token control ran, result recorded as a bool | DEC-011; issue #6 | 1 |
| **G-F2** | Causal load-bearing — intervention at a named hook/layer, with `cause` **and** `isolate` both present, **and `isolate` reported only where `cause` cleared the threshold** | DEC-013; **DEC-020**; PRIOR_ART §11 Q1 | 1 |
| **G-F3** | Interference control run and reported | DEC-008 | 1 |
| **G-F4** | Verdict rule enforced: `flagged` **iff** `paraphrase_survived` and `causal_claim` | `findings.jsonl` header | 0 |
| **G-F5** | Aggregate-vs-per-feature attribution — a causal claim names the level it holds at (feature vs cumulative ladder) and carries the reconstruction error | **DEC-020** | 0 |
| **G-F6** | Intervention results state **site and scale** — a cause score is uninterpretable without them, since the same threshold means different things on a probability vs a logit difference, and the final token dilutes while raising the null bar | **DEC-025** | 0 |

**Code gates (`G-C`) — over `experiments/*.py`.** These are the gates for the
fifth defect class (§1). They inspect experiment *code*, not its output, and
they are the cheapest place to catch a vacuous measurement — at design time
rather than after a plausible-looking null.

| Gate | Checks | Traces to | Tier |
|---|---|---|---|
| **G-C1** | Declared statistic is not structurally bounded below its own threshold — computing the bound from the declared marginals, N, and threshold | DEC-019 failures 1–2 | 0 |
| **G-C2** | Declared control is constructible — the code computes and records the planted signal's presence in both groups before recovery is read | DEC-019 failure 3 | 0 |
| **G-C3** | Statistical-test direction is asserted — every survival/CDF call is bound to a known-answer case in the fixture | DEC-019 failure 4 | 0 |
| **G-C4** | Every reported reading can come out low — no metric computed solely from cases where the effect was absent | DEC-020 isolate vacuity | 0 |
| **G-C5** | Cross-run comparability of experiment parameters (the Maith G5-4 analogue: what must match for two numbers to be compared) | Maith `PIPELINE_QUALITY_GATES` G5-4 | 0 |
| **G-E1** | Schema validity — record parses, all required keys present, no unknown keys | `findings.jsonl` header | 0 |
| **G-E2** | Required values non-empty — `null_model`, `correction`, `n` | issue #4 DoD; header | 0 |
| **G-E3** | Causal consistency — `causal_claim: true` requires an `intervention` object with both properties and a control result | DEC-013 | 0 |
| **G-E4** | Paraphrase consistency — `paraphrase_survived: true` requires ≥1 control listed | DEC-011 | 0 |
| **G-E5** | No conclusions — no mathematical-claim language anywhere in the record | README § "What counts as a result"; workflow § Gates | 0 |
| **G-E6** | Append-only — line count non-decreasing across commits; existing lines never modified | `findings.jsonl` header | 0 |
| **G-E7** | Cross-reference — `issue` names a real issue closed as done; `run_id` matches the documented format | workflow § Run-ids | 0 |
| **G-E8** | Absorbtion caveat on nulls — a `null` verdict citing a detector limit rather than an absence | PRIOR_ART §4; issue #4 | 0 |
| **G-R1** | Header completeness — six mandatory fields for experiment files; three for infrastructure files (the documented exemption) | `experiments/README.md` | 0 |
| **G-R2** | No model substitution — the model id in an experiment matches the DEC-014 target unless a DEC authorizes otherwise | **defect #1**; DEC-014 | 0 |
| **G-R3** | Dependency pinning — every requirement carries a version specifier | `requirements.txt` header | 0 |
| **G-R4** | Docs coherence — README / handoff / DEC log / experiments README agree on target model and settled facts | workflow § Step 1b | 0 |
| **G-R5** | Run-log currency — every `experiments/*.py` has a row in the experiments README run log | **defect #2** | 0 |

**Tier 0 is the first deliverable.** It is 29 of the 38 gates, needs no model,
no torch, and no GPU, and it covers defects #1 and #2 outright, the whole
evidence-integrity surface, and — most importantly — the entire `G-C` code-gate
series for the fifth defect class. Tier 1 gates are the detector-validity ones,
and they can wait for the runs that produce their inputs.

**A sixth defect class: the statistic does not track the signal (DEC-023,
adjudicated in DEC-024).** Re-running #5's positive control under per-feature
thresholds found the top-ranked pair *identical with and without injection*
(0.6322 at every rate), so the max-NPMI instrument was never selecting the
injected pair — it was selecting a high-frequency structural co-occurrence, and
the negative control produced false positives.

This is distinct from the fifth class. There, the code could not fire at all.
Here it fired, passed its cutoff, and was **tracking something other than the
planted signal** — a failure a constructibility check alone does not catch,
because the signal *was* constructible. DEC-024 located the cause: a
max-statistic over an **unbounded** ~7.5M-pair search is governed by its
noisiest pair, so an unrelated high-frequency co-occurrence always wins. G-D9 is
the gate for it — the recovered pair must be the injected pair, not merely above
cutoff — and DEC-024 adds the design constraint that the pair set be
pre-specified and bounded.

**What the adjudication settled, and why G-D10 exists.** #5's pass **stands** on
the analytic-null control; the max-NPMI + permutation-null *instrument* is
retired. Getting there took three entries — pass (DEC-017), non-replication
(DEC-023), adjudication (DEC-024) — during which the handoff held two
contradictory states. G-D10 makes the propagation of a retirement mechanical
rather than dependent on a later session noticing.

---

## 4. What makes a check a check

Carried from `Maith/tooling/gates/README.md`, and non-negotiable:

1. **Every gate ships a fixture that makes it fail.** A gate without a
   failing fixture is assumed broken until proven otherwise. This is not
   ceremony — Maith's first exit-code verification was vacuous because a
   string anchor silently missed, and the fix was to assert the mutation
   applied.
2. **A gate that cannot fail is removed, not kept.** If no plausible input
   makes it fire, it is not a check.
3. **Exit codes are the contract.** Non-zero on findings; the message names
   the gate id and the offending artifact.
4. **Gates are partial by construction, and say so.** These are text and
   schema checks over artifacts. They cannot tell whether a detector is
   measuring what it claims. That is `G-D3`–`G-D5`'s job, and beyond those,
   it is the human's.
5. **Two tiers, never merged.** A tier-0 pass is not "gate passed". Maith's
   formulation is exact: *"Treating a grep pass as a gate pass is itself an
   integrity hole."*

### The prior-art alignment test (the one gate that is not mechanical)

Not every validation question has a checker. Ephapse's central one does not:

> Is the apparatus producing results at the coordinates prior art predicts?

Ephapse's own prior art makes specific predictions for its conditions —
Pythia-70M, SAE features, cross-domain corpora:

- Raw cross-domain co-activation should be **close to the expected result**,
  not rare (DEC-006; universality is established).
- A `null` is the **expected** outcome of the first probe (DEC-005, DEC-007).
- Detector output should skew **token-shaped** at this scale (DEC-011).
- Any SAE result inherits the **absorption** and **isolation** ceilings
  (PRIOR_ART §4, §11).

So the apparatus check inverts the usual direction: a *strong positive* on the
first probe is the surprising event, and the burden of proof runs against it.
This cannot be automated — it is a written comparison, done by a human, of
observed coordinates against predicted ones. It is specified here so it is not
skipped, and it belongs in the methodology writeup, not in a gate script.

---

## 5. The status ladder

Adapted from PleaNP `VALIDATION_SUITE.md`. Applied to **claims** rather than
definitions, since that is Ephapse's unit.

| Rung | Name | Requires |
|---|---|---|
| 0 | **Observed** | A record exists in `findings.jsonl` with `verdict: null` or `flagged`. Nothing is claimed. |
| 1 | **Recorded** | Passes all tier-0 gates (G-C1–G-C5, G-E1–G-E8, G-R1–G-R5). The record is internally consistent and its evidence is present. |
| 2 | **Surface-controlled** | G-F1 passed. The overlap survived paraphrase / zero-shared-token. |
| 3 | **Causal, per-feature** | G-F2, G-F3, and G-F5 passed, with the claim at feature granularity. **Not currently reachable at pythia-70m** — DEC-020 measured 0/50 features above the cause threshold. |
| 4 | **Causal, aggregate** | The cumulative dose-response ladder (DEC-020) moves the target monotonically, with reconstruction error recorded. This is the strongest *currently attainable* causal rung at this scale. |
| 5 | **Handed off** | A **human** articulates the candidate as a plain-language mathematical claim and passes it to Maith's gate 1. |

**Rung 5 is not reachable by an agent, and rungs 3–4 are not a discovery.** The
word "finding" is reserved for rung 3 and above; rungs 0–2 are observations.
Nothing below rung 5 is described as a mathematical result — that language
belongs to Maith's gate-3 survivors (README; workflow § Gates).

**Why rungs 3 and 4 split.** DEC-020 measured single-feature intervention at
pythia-70m as below the noise floor (0/50 features above threshold; mean
relative SAE reconstruction error 0.362). Per DEC-008 a null there is
*inconclusive, not negative* — it does not count against any feature. So the
per-feature claim `PRIOR_ART.md` §11 originally described is not testable at
this scale, and the aggregate ladder is what the apparatus can actually
support. Recording that as two rungs rather than one avoids the failure mode
where an unattainable rung 3 makes the whole ladder look blocked when a
weaker but honest rung 4 is available.

---

## 6. Artifact layout

Mirrors the sibling repos' `tooling/gates/` convention so an agent that has
worked in Maith or PleaNP can navigate this without re-learning.

```
.github/workflows/ci.yml        — tier-0 gates on push to dev
tooling/gates/
  README.md                     — the reference: gates, severities, usage
  validate_findings.py          — G-E1..G-E8   (findings.jsonl records)
  validate_experiments.py       — G-R1, G-R2, G-R5 (experiment files, targets, run log)
  validate_deps.py              — G-R3        (requirements pinning)
  check_docs_coherence.py       — G-R4        (cross-doc settled facts)
  check_prompt_disjointness.py  — G-P2, G-P4  (tokenizer-level; needs tokenizer, not model)
  check_experiment_code.py      — G-C1..G-C5  (experiment code; the DEC-019/020 gates)
  tests/
    conftest.py
    fixture_findings/           — one minimal JSONL per G-E gate, each violating exactly one
    fixture_experiments/        — one .py per G-R1/G-R2/R5 violation
    fixture_requirements/       — unpinned / pinned pairs
    fixture_code/               — one .py per G-C violation, drawn from the real DEC-019/020 failures
    test_gates.py               — asserts each gate fires on its fixture and passes on clean
```

**Fixture rule in practice:** `test_gates.py` asserts, for each gate, both
directions — fires on its fixture, silent on the clean fixture. A gate with
only the positive direction is incomplete.

**The `fixture_code/` set is not synthetic.** The four DEC-019 failures and the
DEC-020 isolate-vacuity bug are known, reproducible shapes, so the G-C fixtures
are drawn from them directly: a catch-all group whose marginal is 1.0, a
bounded statistic, a control that never fires, an inverted survival function,
and a metric computed only over no-effect cases. A G-C gate that cannot fire on
the bug that motivated it is not a gate — and these fixtures are the only way
to demonstrate that, because the original code is already fixed.

---

## 7. Human review, adapted

The PleaNP three-layer table transfers in shape, with Layer 3 replaced (§2).

| Layer | Verifies | Who | Effort |
|---|---|---|---|
| 1. Mechanical | schema, required values, verdict rule, header completeness, pins, doc coherence | CI (tier 0) | none |
| 2. Detector | recovery curve exists and can fail; null calibration | tier-1 gates, run by an agent | none |
| 3. Read-back | the `findings.jsonl` record says what the writeup says | agent produces both; **human confirms one correspondence** | one comparison |
| 4. Prior-art alignment | results land at predicted coordinates; a positive is treated as suspect | **human** | one written paragraph |

The irreducible human step is Layer 4, plus the existing handoff judgment
(README § "Relationship to Maith"). It is **not** reducible, for the same
structural reason PleaNP gives: satisfaction is not internal to the system.
A perfectly consistent `findings.jsonl` with all gates green can still be a
faithful record of a detector reading tokens. Only the prior-art comparison and
the human's "is this interesting?" answer address that, and both are outside
what any checker can reach.

**The human is never the tiebreaker.** If the record and the writeup disagree,
that is a defect for the agent to fix, not a judgment call.

---

## 8. Explicitly not in scope

- **No candidate-quality gate.** Nothing here judges whether a co-activation is
  mathematically interesting or correct. That is the human gate and Maith's
  gates 1–5.
- **No gate-checker for candidates.** This layer validates artifacts that
  already exist. It does not generate, rank, or triage candidates.
- **No Lean-side validation.** Unchanged from the handoff: if a candidate
  needs Lean checking it goes to Maith.
- **No promoted-findings database.** Rung 5 artifacts live in Maith.
- **No LLM in CI.** Every tier-0 gate is deterministic file inspection. PleaNP
  left the LLM-in-CI question open; Ephapse should not open it — a
  non-deterministic gate is not a gate.

---

## 9. Task map

Decomposed into 14 issues (#8–#21), sized to one agent run each, with native
GitHub blocked-by relationships forming the lineage. Only #8 is unblocked.

Each task's Definition of Done names **one observable check** — per the
protocol's "one task = one signal", which the first draft of this decomposition
violated by listing four to eight items per issue. For gate tasks the single
signal is a command over that gate's fixtures, plus the requirement that
removing a fixture turns it red. That mutation half is not decoration: Maith
recorded that its own first exit-code verification *was* vacuous because a
string anchor silently missed.

| Issue | Task | Gate(s) | Blocked by |
|---|---|---|---|
| #8 | Adopt this spec (decision-log entry + handoff pointer) | — | — |
| #9 | Tier-0 gate scaffolding: `run_all.py`, fixture tree, gate reference | all | #8 |
| #10 | `validate_findings.py` — schema and evidence | G-E1, E2, E6, E7 | #9 |
| #11 | `validate_experiments.py` — headers, target model, run log | G-R1, R2, R5 | #9 |
| #12 | `validate_deps.py` — dependency pinning | G-R3 | #9 |
| #13 | CI wiring for the tier-0 set | all tier 0 | #10, #11, #12 |
| #14 | `check_prompt_disjointness.py` | G-P2, P4 | #8, #9 |
| #15 | Repair the experiment artifacts so the gates pass | defects #1–#2 | #10, #11, #12 |
| #16 | Make the header rule checkable and single-sourced | G-R1 | #11 |
| #17 | Tier-1 detector-validation harness contract (scoping only) | G-D3, D4 | #8 |
| #18 | Prior-art alignment record (template + first use) | §4 | #8 |
| #19 | `validate_findings.py` — claim-consistency rules | G-E3, E4, E5, E8 | #10 |
| #20 | `check_docs_coherence.py` | G-R4 | #9 |
| #21 | Reconcile `requirements.txt` with the pinning gate | G-R3 | #12 |
| **#22** | **`check_experiment_code.py` — the `G-C` code gates** | **G-C1–C5** | #9 |

**Revision 2026-09-19 (run `20260918-2347-0201`).** This spec's first version
gated artifacts only, and was filed as #8–#21 before issues #5 and #7 ran. Those
runs (DEC-016–DEC-023) established two further defect classes one level lower
than artifacts — in experiment *code* and in the *statistic's ability to track
its target* — that no gate in the original inventory would have caught. Four
consecutive #5 designs and one #7 metric produced plausible-looking results that
were artifacts of vacuous measurement (fifth class); then #5's own pass failed
to replicate, with the top-ranked pair identical with and without injection
(sixth class).

The revision adds the `G-C` series (§3), the constructibility, frozen-parameter,
tracking and replication gates (G-D7–G-D10), the arithmetic-capability
requirement on multiplicity correction (G-D2, corrected by DEC-016), the
isolate-vacuity rule (G-F2), the aggregate-attribution gate (G-F5), and the
split causal rung (§5). Inventory: 24 → 38 gates. #22 is the new
highest-value task; #23 logs the related registry gap.

*Count history:* DEC-021 recorded 24 gates, DEC-022 raised it to 34, DEC-025 to
36, DEC-026 to 37 (G-D9/G-D10 from DEC-023/024; G-F6 from DEC-025). DEC-039
added no gate: it recounted this section's § 3 inventory mechanically and found
**38** ids (29 tier-0 capable, 9 tier-1), so DEC-026's 37 was a hand-count that
missed one row. 38 is canonical. `tooling/gates/gate_inventory.py` derives the
count from this table — quote its output rather than a typed number.

**Three splits, each because the bundled task had more than one signal.**
This is the substantive change from the first filing, and it is worth recording
because the same instinct will recur:

- **#10 / #19** — schema validity ("is this well-formed") and claim consistency
  ("does the claim match the evidence") are different kinds of check. The
  second carries the false-positive risk: G-E5 must reject a mathematical
  claim while passing a record that correctly *disclaims* one.
- **#12 / #20** — dependency pinning is a one-file check; docs coherence has to
  distinguish a wrong current value from a decision-log entry that correctly
  records a superseded one. Shipping the second behind the first would have
  hidden its difficulty.
- **#15 / #21** — repairing experiment files and settling the `numpy` pin
  exception are different artifacts and different decisions.

**Relationship to the existing methodology lineage (#3–#7).** These tasks do
not block the experiments and the experiments do not block them, with two
touchpoints: #14 automates the control #6 requires, and #17 specifies the
artifact #5 must produce. Neither is a hard block, because #5 and #6 can
proceed with the control run manually — the gates make it recorded and
repeatable, not possible.

---

## 10. Open questions

1. **How much of tier 1 belongs here at all?** The detector-validity gates
   (G-D3–G-D5) are the ones that matter most and are the hardest to express as
   pass/fail. It may be that G-D3's only real content is "the artifact exists
   and reports a curve", with the judgment staying human. Worth deciding before
   building it.
2. **Tokenizer-level disjointness means a download.** G-P2 needs the target
   tokenizer, which means network access in CI. Acceptable, or should the
   token-ID sets be committed as evidence and only re-verified when they change?
3. **Where does `findings.jsonl` migration live?** G-E1's schema is the file
   header's prose. If the header and the gate diverge, which is authoritative?
   The gate should probably be, with the header generated from it.
4. **Does the append-only check (G-E6) need history?** If the clone is shallow
   (it is), G-E6 cannot see prior commits. Either require a full clone in CI or
   check only that the current line count is ≥ a recorded high-water mark.
