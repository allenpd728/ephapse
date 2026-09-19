# Next Steps — Ephapse handoff for orchestration

**Written:** 2026-09-19, at commit `7727d98` on `dev`; **updated** at `f0581ec`
plus the rung-3 filings (#39, #40).
**Audience:** a high-level orchestrator dispatching agent sessions.
**Purpose:** what the project is, where it stands, what to work on next, and what
not to do.

Every number here was measured, not inferred. Counts drift — issues were filed
during earlier analyses, and a sibling session landed DEC-034 and #37/#38 while
this document was being revised — so re-measure before acting on a count.
`gh issue list --repo allenpd728/ephapse --state open --json number,labels` is
the cheap check; `python3 tooling/program/issue_state.py audit` covers labels and
dependencies.

---

## 1. One-paragraph orientation

Ephapse probes open-weight model internals (SAE features, activations) looking for
**cross-domain co-activation** — unrelated inputs driving the same internal
structure — as a *candidate generator* for mathematical hypotheses. It is a
sibling of Maith, not an extension: different substrate, no kernel oracle, so its
discipline comes from a two-tier automated validation layer plus process. The
product is a **candidate**, never a result; results belong to Maith's gates.

## 2. Where the method actually stands

Read [`docs/ROADMAP.md`](../ROADMAP.md) before anything else. It is the
**verdict-revision rung ladder** (adopted DEC-033), deliberately *not* PleaNP's
construction ladder, because this method has already returned a verdict.

| Rung | Question | Status |
|---|---|---|
| 0 | Can the detector detect? | **Done** — yes, with a recovering positive control |
| 1 | Is the signal more than surface form? | **Done** — weakly positive (6 survivors vs 0 on a *constructed* pair) |
| 2 | Does it fire across unrelated domains? | **Done — clean null** (DEC-027) |
| 3 | Is the null a scale artifact? | **Live.** Feasible, not blocked |
| 4 | Is a per-feature causal claim reachable? | Depends on 3 |
| 5 | Would a candidate be *interesting*? | Human step, **no falsifier** |
| 6 | Handoff to Maith | Not reached — no candidate exists |

**The single sentence that matters:** the detector works, the inputs were verified
disjoint, and the cross-domain probe found nothing at 70M. The honest reading is
*poor signal-to-noise at this scale*, not *absence of structure* — feature
absorption is the primary alternative explanation.

## 3. The next action, and it is filed

**Rung 3: re-run the rung-2 probe at larger scale.**

This is the only live rung and it is the highest-value work in the repo. It
converts "we could not see it at 70M" into "we could not see it at scale *X*",
which is either a materially stronger negative or the discovery the project
exists to find.

**It is filed as two prerequisite issues plus the probe:**

| Issue | What | Status |
|---|---|---|
| **#39** | Measure CPU feasibility for `gemma-2-2b` (load, RSS, latency, SAE load, reconstruction error) | **claimable now** |
| **#40** | Re-derive the detector statistic and pre-register it for the new SAE | blocked by #39 |
| — | The rung-3 probe itself | **not yet filed** — it should be filed once #40 lands and its parameters are known |

That sequencing is deliberate. The probe cannot be specified before its statistic
is pre-registered, and the statistic cannot be chosen before the SAE and its hook
are known. Filing the probe now would produce an issue whose Definition of Done
could not be written.

**The correction that makes this actionable.** An earlier draft called rung 3
"blocked on SAE availability." **That was wrong** — queried 2026-09-19:

| Model | SAEs available |
|---|---|
| `pythia-70m-deduped` (current) | 7 |
| **`gemma-2-2b`** | **316** (`gemma-scope-2b-pt-res`); 25 in a Matryoshka residual release |
| `gpt2-small` | 12 per release, 18 releases |
| `qwen3-4b`, `gemma-3-4b-pt`, `mistral-7b`, `qwen3-8b`, `Llama-3.1-8B` | 1–9 each |

**Target: `gemma-2-2b`** — ~28× the current parameter count, ~8 GB fp32 against a
~10 GB per-run budget.

**The rule that has cost this project the most, and must be honored on rung 3:**
run the positive control *first*. Four statistics in four issues looked plausible
and could not fire — a model target, a multiplicity correction, a threshold, and a
rate cutoff. Only the control caught each. The working rule is stated in DEC-027:
**a family-wise cutoff over an unstandardized statistic is the recurring bug.**
Issue #40 exists to re-derive the statistic rather than copy it, precisely because
of this.

## 4. The work queue

### Claimable now (11 issues)

| # | Kind | What |
|---|---|---|
| **#39** | experiment | **Rung 3 prerequisite A** — CPU feasibility for `gemma-2-2b` (the top action, §3) |
| **#31** | protocol | Build the program ledger (`program/ledger.jsonl`) — **keystone; #32/#33 are blocked on it** |
| **#37** | gate | Supervised comparator baselines (difference-in-means, linear probe) alongside the SAE — DEC-034 |
| **#38** | repair | Reconcile the gate-count figures (37 vs 38 vs 11 wired) and single-source them |
| #29 | repair | Backfill `kind:`/`status:` labels on open issues |
| #34 | protocol | Adopt the emergent-requirement protocol into the workflow doc |
| #22 | gate | Experiment-code gates G-C1..G-C5 |
| #19 | gate | Findings claim-consistency rules G-E3/E4/E5/E8 |
| #20 | gate | Docs-coherence gate G-R4 |
| #21 | decision | Reconcile `requirements.txt` with the pinning gate (numpy exception) |
| #16 | documentation | Make the experiment-header rule checkable and single-sourced |

**Sequencing note:** #39 first — it is the top action and it unblocks #40. #31
second among the rest — it unblocks #32 and #33.

### Blocked

| # | Blocked by | Note |
|---|---|---|
| **#40** | #39 | Rung 3 prerequisite B (statistic re-derivation) |
| #32, #33 | #31 | Program views and ledger backfill |
| #23 | #22 | Detector contract registry — **overlaps #40; coordinate rather than duplicate** |
| #15 | **#24**, #10, #11, #12 | Repair the four artifacts — **cannot proceed honestly until #24 fixes the gates it repairs against** |
| #13 | #10, #11, #12 | Wire tier-0 gates into CI |

### Needs a human decision (no agent should pick these up)

| # | Why |
|---|---|
| **#18** | Prior-art alignment record — spec §7 Layer 4, the irreducible human step |
| #17 | Tier-1 harness contract — scoping question |

### Open defects worth prioritizing

- **#24** — two false-negative holes in the G-R1/G-R2 gates: the infrastructure
  exemption is granted by prose (any file can excuse itself), and there is no
  attribution escape, which **blocks #15 from repairing the tree honestly**.
- **#25** — `findings.jsonl` carries an undeclared key; the real log fails G-E1.
  **This is the one currently failing test** (§5).
- **#36** — the claim lock only covers sessions that use it.

## 5. Known breakage and hygiene debt

**Measured, not inferred:**

| Item | State |
|---|---|
| Tier-0 gates | **11 wired, 11 passing** |
| Gate ids specified in the validation spec | 38 |
| Test suite | **67 passed, 1 failed** |
| The failure | `test_real_findings_file_passes_the_registered_findings_gates` → **#25** (pre-existing, owned by that issue) |
| **CI** | **Not wired.** No `.github/workflows/`. Gates run only when a session invokes them manually → **#13** |
| Label hygiene | **8 open issues carry no `status:` label** (#13, #15, #17, #18, #23, #24, #25, #36) |
| `kind:` coverage | Present on #29–#40; the eight above still need it → #29 |
| Open issues | **22**, of which **11 are claimable** |

**The gate-count discrepancy is real and has its own issue (#38).** Four documents
say 37, `PROGRAM_MANAGEMENT_SPEC.md` says 38, and the registry says 11 wired. The
spec contains 38 distinct gate ids; "37" is stale in the README, the handoff, and
the validation spec itself. This is exactly the docs-coherence drift **G-R4**
exists to catch, occurring in the window before G-R4 is wired (#20). It is cited
here rather than fixed, because #38 owns it.

**Two tooling facts a session needs:**

- `python3 tooling/program/issue_state.py refresh && ... audit` — the cheap path
  for label/dependency hygiene. `refresh` reads labels *and* `blocked_by` via
  GraphQL (`gh issue list` cannot read dependencies).
- `python3 tooling/gates/run_all.py` — the authoritative gate run. A gate with no
  failing fixture reports `BROKEN` and fails, by design.
- **The `kind:` label vocabulary is a closed set** — `experiment`, `gate`,
  `repair`, `defect`, `gap`, `decision`, `protocol`. An out-of-vocabulary kind
  makes `gh issue create` fail. This happened while filing #40 (`kind:methodology`
  was rejected); the fix was `kind:gap`, and the mismatch is noted in that issue
  rather than papered over.

## 6. What NOT to do — foreclosed, do not re-propose

**An external spec proposing a commercial "Innovation Asset Inventory" was
reviewed and rejected** (DEC-033,
[`EPHAPSE_SPECIFICATION_ASSESSMENT.md`](../reference/EPHAPSE_SPECIFICATION_ASSESSMENT.md)).
Do not reopen it, and do not dispatch work on it.

The rejections, so a dispatcher can refuse the shape rather than the exact file:

1. **No commercial framing.** The repo is *"not authorized to claim a discovery
   is novel or valid."* Anything that sells an asset asserts that.
2. **No novelty-certification filter.** The "Zero-Synapse Mandate" filters on
   *commercial precedent*, but this repo's measured problem is the opposite:
   co-activation fires *too much*. Also re-opens DEC-012, already declined.
3. **No pipeline, feasibility matrix, vault, or asset schema.** Infrastructure
   ahead of results, for an empty set. The README forbids it.
4. **No second record schema.** The program ledger (PROGRAM_MANAGEMENT_SPEC §4)
   already covers it.

Two ideas *were* rolled in (the "frictions obliterated" framing, PRIOR_ART §11)
and three postponed **with stated conditions** (vault, hotspot search,
feasibility grading). The postponed ones are conditioned on a **candidate
existing** — there are none.

**Also foreclosed by existing decisions:** no LLM in any gate or view (a
non-deterministic gate is not a gate); no promoted-findings database; no
Lean-side validation layer (that is Maith's).

## 7. How to verify any dispatched work

1. **`python3 tooling/gates/run_all.py`** — must exit 0 with every gate `PASS`.
2. **`python3 -m pytest tooling/gates/tests/ -q`** — 67 pass expected; the #25
   failure is the known exception.
3. **Delete a fixture** — the corresponding gate must report `BROKEN`. This is the
   only way to show a gate actually works; a gate that cannot fail is not a check.
4. **For experiment work:** the positive control must run **before** the result,
   and the header must declare model, inputs, question, null, correction, issue.
5. **Claim protocol:** swap the status label and run-id in one edit, then re-fetch
   to confirm ownership. One claim per agent at a time.

## 8. If only one thing gets dispatched

**#39 — rung 3 prerequisite A** (§3): measure CPU feasibility for `gemma-2-2b`.
It is bounded, it is a measurement rather than a build, and it unblocks #40,
which unblocks the only live rung in the project.

If a second: **#24**, because it is an open defect in shipped validation work and
it currently blocks #15.

If a third, and this one is different in kind: **#37** (supervised comparator
baselines, DEC-034). It is the only newly-adopted apparatus change, it runs at
zero additional compute, and it converts the feature-absorption *disclaimer* into
a *measurement* — the caveat that currently every null writeup must state and
nothing checks.

---

## 9. What changed since the first version of this document

Recorded so a reader can tell what is current rather than assuming the whole
document is one vintage:

| Change | Source |
|---|---|
| Rung 3 prerequisites **filed** as #39 (feasibility) and #40 (statistic), linked `#39 → #40` | this session |
| The rung-3 probe is deliberately **not** filed yet — its DoD cannot be written before #40 pins the statistic | this session |
| **DEC-034** adopted: (1) supervised comparator baselines (#37); (2) the validation layer declared a first-class project output (#38) | sibling session |
| README gained a **"What this project produces"** section | sibling session, `7474329` |
| **#38** filed for the gate-count discrepancy (37 vs 38 vs 11 wired) | sibling session |
| A **critique response** document exists at `docs/reference/CRITIQUE_RESPONSE_2026-09-19.md` | sibling session |
| DEC count is now **34** (was 33) | measured |

**One consequence for the ladder.** DEC-034's comparator baselines are a change to
the *apparatus*, not a rung. They cut across rungs 1–3: a probe that detects a
paraphrase-invariant bridge the SAE misses would move the bottleneck from model
scale to *instrument*, which is a different verdict-revision than rung 3 tests.
The roadmap has not yet been updated to record that cross-cut — worth doing when
#37 lands, and flagged here so it is not lost.

---

## Appendix — where the authoritative documents live

| Question | Document |
|---|---|
| Where does the method stand, and what would revise it? | `docs/ROADMAP.md` |
| What are the rules for claims and gates? | `docs/reference/TEST_VALIDATION_SPEC.md` |
| How is work tracked? | `docs/reference/PROGRAM_MANAGEMENT_SPEC.md` |
| How do agents claim and finish work? | `docs/MULTI_AGENT_WORKFLOW.md` |
| What is the literature position? | `docs/reference/PRIOR_ART.md` |
| What was decided, and why? | `docs/decisions/LOG.md` (DEC-001 … DEC-034) |
| What has been measured? | `experiments/README.md`, `findings.jsonl` |
| Why was the external spec rejected? | `docs/reference/EPHAPSE_SPECIFICATION_ASSESSMENT.md` |
| What was the response to the audio critique? | `docs/reference/CRITIQUE_RESPONSE_2026-09-19.md` (DEC-034) |
