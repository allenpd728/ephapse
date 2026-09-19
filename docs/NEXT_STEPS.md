# Next Steps — Ephapse handoff for orchestration

**Written:** 2026-09-19, at commit `7727d98` on `dev`.
**Audience:** a high-level orchestrator dispatching agent sessions.
**Purpose:** what the project is, where it stands, what to work on next, and what
not to do.

Every number here was measured at the commit above. Counts drift (two issues were
filed during a previous analysis), so re-measure before acting on a count.

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

## 3. The next action, and it is one action

**Rung 3: re-run the rung-2 probe at larger scale.**

This is the only live rung and it is the highest-value work in the repo. It
converts "we could not see it at 70M" into "we could not see it at scale *X*",
which is either a materially stronger negative or the discovery the project
exists to find.

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

**Two prerequisites, each a measurement rather than a build** (do these as one
scoped task before the full probe):

1. **CPU feasibility at 2B** — load it, measure RSS and per-prompt latency at
   batch, per `SANDBOX_BASELINE.md`'s discipline. Do not assume; the sandbox has
   no cgroup cap and ~10 GB is a budget, not a guarantee.
2. **Re-derive the statistic for the new SAE** — the hook changes
   (`layer_N/width_16k/...` for Gemma Scope residual, vs `blocks.3.hook_resid_post`
   now), the family is larger, and the multiplicity parameters from DEC-016/018 do
   **not** transfer silently. Re-pre-register them and keep the positive control
   mandatory (DEC-019).

**The rule that has cost this project the most, and must be honored on rung 3:**
run the positive control *first*. Four statistics in four issues looked plausible
and could not fire — a model target, a multiplicity correction, a threshold, and a
rate cutoff. Only the control caught each. The working rule is stated in DEC-027:
**a family-wise cutoff over an unstandardized statistic is the recurring bug.**

## 4. The work queue

### Claimable now (8 issues)

| # | Kind | What |
|---|---|---|
| **#31** | protocol | Build the program ledger (`program/ledger.jsonl`) — **keystone; #32/#33 are blocked on it** |
| #29 | repair | Backfill `kind:`/`status:` labels on open issues |
| #34 | protocol | Adopt the emergent-requirement protocol into the workflow doc |
| #22 | gate | Experiment-code gates G-C1..G-C5 |
| #19 | gate | Findings claim-consistency rules G-E3/E4/E5/E8 |
| #20 | gate | Docs-coherence gate G-R4 |
| #21 | decision | Reconcile `requirements.txt` with the pinning gate (numpy exception) |
| #16 | documentation | Make the experiment-header rule checkable and single-sourced |

**Sequencing note:** #31 first among these — it unblocks #32 and #33.

### Blocked

| # | Blocked by | Note |
|---|---|---|
| #32, #33 | #31 | Program views and ledger backfill |
| #23 | #22 | Detector contract registry |
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
| `kind:` coverage | Present on newer issues (#29–#36); older ones need #29 |

**Two tooling facts a session needs:**

- `python3 tooling/program/issue_state.py refresh && ... audit` — the cheap path
  for label/dependency hygiene. `refresh` reads labels *and* `blocked_by` via
  GraphQL (`gh issue list` cannot read dependencies).
- `python3 tooling/gates/run_all.py` — the authoritative gate run. A gate with no
  failing fixture reports `BROKEN` and fails, by design.

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

**Rung 3's prerequisites** (§3): measure CPU feasibility at `gemma-2-2b`, and
re-derive the detection statistic for its SAE hook. Both are bounded, both are
measurements rather than builds, and together they unblock the only live rung in
the project.

If a second: **#24**, because it is an open defect in shipped validation work and
it currently blocks #15.

---

## Appendix — where the authoritative documents live

| Question | Document |
|---|---|
| Where does the method stand, and what would revise it? | `docs/ROADMAP.md` |
| What are the rules for claims and gates? | `docs/reference/TEST_VALIDATION_SPEC.md` |
| How is work tracked? | `docs/reference/PROGRAM_MANAGEMENT_SPEC.md` |
| How do agents claim and finish work? | `docs/MULTI_AGENT_WORKFLOW.md` |
| What is the literature position? | `docs/reference/PRIOR_ART.md` |
| What was decided, and why? | `docs/decisions/LOG.md` (DEC-001 … DEC-033) |
| What has been measured? | `experiments/README.md`, `findings.jsonl` |
| Why was the external spec rejected? | `docs/reference/EPHAPSE_SPECIFICATION_ASSESSMENT.md` |
