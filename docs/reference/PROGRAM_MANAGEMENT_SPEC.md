# Ephapse — Experiment Program Management Spec

**Status:** **adopted**, 2026-09-19 (DEC-030). Drafted 2026-09-19 (run
`20260918-2332-e7c4`). This document is now the authority for Ephapse's
experiment program management; it was adopted by decision-log entry, as it
specified.
Modelled on `TEST_VALIDATION_SPEC.md`, which it complements.

**Purpose.** `TEST_VALIDATION_SPEC.md` answers *"is this artifact valid?"* — it
gates the evidence. This document answers a different question: *"where is the
program, and what does it need next?"* — it tracks the work.

The two are deliberately separate. A repo can have perfect artifacts and no
idea what it is doing; it can have a clear plan and invalid evidence. Ephapse
currently has the second problem in its primitive form and the first problem
solved: 38 gate ids are specified (7 wired), 26 decisions are logged, and the
issue queue does not reliably say what is open.

**Read first.** `MULTI_AGENT_WORKFLOW.md` (claiming, run-ids, dependencies) and
`TEST_VALIDATION_SPEC.md` (gates, tiers). This spec adds a layer neither covers.

> **Measurements drift, and that is part of the finding.** Every number in §1 was
> taken on `dev` at commit `cc09eb6`. While this analysis was being written, two
> further issues were filed by a parallel session (#26, #27) and one of them
> arrived without a `status:` label. The counts below are therefore already
> stale. A program view that has to be re-measured by hand in order to be
> trusted is §1's point — not a caveat on it.

---

## 1. The gap, stated precisely

Ephapse's process discipline is strong at the **task** level and absent at the
**program** level. The evidence for that claim, measured on the tree as of
`cc09eb6`:

| Symptom | Measurement |
|---|---|
| The queue is not a trustworthy work surface | **8 of 15 open issues carry no `status:` label** (#13, #15, #17, #18, #23, #24, #25, #27; measured before #26 was filed). `MULTI_AGENT_WORKFLOW.md` § Task states says every issue has one. |
| No issue-type axis | `infrastructure`, `methodology`, `documentation` are *domains*, not *kinds*. Nothing distinguishes "build a gate" from "fix a bug in a gate" from "we discovered a hole" from "a human must decide". |
| No structured outcome vocabulary | `findings.jsonl` has `verdict: flagged\|null` and a free-string `kind` (`positive_control`, `paraphrase_robustness`, …). The four recorded outcomes are not classified by *what they mean for the program*. |
| No results registry | **7 result JSONs** sit in `experiments/` with no index, and no traversal from a result to its finding to its DEC. |
| No program view | Reading the state means reading 26 DECs (1,217 lines), 15 issues, and 4 findings. There is no single surface. |
| No unforeseen-requirement protocol | #23, #24, and #25 were each discovered *while doing other work* and filed ad hoc. #24 found two live false-negative holes **in #11's landed, reviewed, gate-passing work**. |
| No results→plan feedback | A null result should change what is attempted next. Nothing routes it. |
| No health metric | Gate count is "38 ids in the spec, 7 wired" — true only because a human counted. Nothing computes it. |

None of these is a correctness bug. All of them are the reason a growing program
becomes unreadable, and they compound: without an issue-type axis, gate #15
(repair artifacts) and #24 (fix the gate's own holes) look like the same sort of
task, when one is mechanical and the other is a defect in shipped work.

---

## 2. What is borrowed, and what is deliberately not built

| Reference | Borrow | Why |
|---|---|---|
| `MULTI_AGENT_WORKFLOW.md` § Task states, Run-ids, Dependencies | **The claim/run-id/dependency machinery, unchanged** | Battle-tested from Maith/PleaNP. This spec adds axes beside it; it does not replace it. |
| `TEST_VALIDATION_SPEC.md` §4 (a check must be able to fail), §6 (artifact layout) | **The gate discipline and the `tooling/gates/` layout** | The program gates follow the same fixture rule and live in the same runner. |
| `findings.jsonl` § coverage-map decision in `axiom-rewrite` (Maith) | **Derive, never duplicate** | The coverage map is derived from the ledger precisely because a stored second copy drifts. Every view here is derived. |
| `TEST_VALIDATION_SPEC.md` §5 (status ladder) | **Rungs as the outcome vocabulary** | The rungs already rank a claim's strength. Reusing them beats inventing a parallel scale. |

**Not built, and why — these are the tempting mistakes.**

- **No second source of truth for task state.** Issue state lives in GitHub.
  The program ledger holds *only* what GitHub cannot express: the outcome
  classification and the traversal links. If a fact is already in the issue
  title, the label set, or `findings.jsonl`, this spec does not copy it.
- **No LLM in any gate or view.** `TEST_VALIDATION_SPEC.md` §8 is binding:
  "a non-deterministic gate is not a gate." Classification is a *human or agent
  judgment recorded as data*, never an inferred label.
- **No promoted-findings database.** Spec §8 already excludes it; rung 5
  artifacts live in Maith.
- **No burndown or velocity metric.** The program is exploratory and the work
  is not uniformly sized. A velocity chart here would measure the estimator,
  not the progress.

---

## 3. The three axes

Three orthogonal classifications. Each is *independent*; a single issue uses one
value from each.

### 3.1 Issue kind — what sort of work is this?

Added as labels. `MULTI_AGENT_WORKFLOW.md` owns the *status* axis
(`available`/`claimed`/`done`/`blocked`); this is the *kind* axis, and they
compose.

| Label | Meaning | Example on the current tree |
|---|---|---|
| `kind:experiment` | Produces a measurement or a result | #3 (cross-domain probe) |
| `kind:gate` | Builds or extends the validation layer | #19 (G-E3/E4/E5/E8) |
| `kind:repair` | Fixes existing artifacts so gates pass — mechanical | #15 (repair the four artifacts) |
| `kind:defect` | A gate or protocol is wrong in shipped work | #24 (two holes in #11's gates) |
| `kind:gap` | A missing capability, design **unsettled** | #23 (detector contract registry) |
| `kind:decision` | Blocked on a human judgment, no agent work available | #18 (prior-art alignment record) |
| `kind:protocol` | Changes how work is done, not what is produced | this spec's adoption |
| `kind:spec` | Produces a specification or contract a later task must satisfy — design **constrained**, must be written down precisely | #40 (pre-register the rung-3 statistic) |
| `kind:hygiene` | Repo hygiene: license, metadata, community files — files that exist for readers, not for the pipeline | #46 (create `main`), #47 (LICENSE) |

**`gap` versus `spec` is the distinction to get right** (DEC-035). A `gap` is work
whose design is unsettled, so the task invites exploration. A `spec` is work whose
design is already constrained by prior decisions and must be instantiated
precisely — it forbids exploration. #23 and #40 are the two types: #23's registry
design is open; #40's parameters are fixed by DEC-016/018/019/027 and only need
writing down. Filing a spec as a gap misroutes it toward design work that has
already been done.

**The machine-readable vocabulary lives in one place** —
`tooling/program/kind_vocabulary.txt` (DEC-035). Both G-M1 and the atomic setter
read it; neither carries its own copy. Adding a value is a vocabulary change and
needs a DEC, which is the precedent DEC-035 set: the rule above governs a *filer*
(file it as a `gap` and say so), while changing the vocabulary is a separate act
because it reclassifies every future task.

**Why `repair` and `defect` are separate.** #15 repairs *files* against *gates
that work*. #24 repairs *gates* that do not. Conflating them hides which side of
the trust boundary is broken — and #24's existence is the proof that the
distinction matters: it found that #11's review, tests, and gate run all passed
while two holes remained.

**Why `decision` is a kind, not a status.** `status:blocked-needs-input` says
*this is stopped*. `kind:decision` says *this is a judgment, and stopping is
correct*. #18 (align results against prior art) is the type specimen: spec §7
makes it the irreducible human step, and it should never be picked up by an
agent regardless of how available it looks.

### 3.2 Outcome class — what did it produce?

For records in `findings.jsonl` and, more broadly, for any completed experiment.
Recorded in the program ledger (§4), not in `findings.jsonl` — that file is
append-only evidence and its schema is gated by G-E1; adding a field there is a
G-E1 change, which is #25's subject.

| Class | Meaning | Current instance |
|---|---|---|
| `instrument-validated` | The apparatus was shown to work, not a claim about the world | #5 (detector recovers injected signal) |
| `instrument-failed` | The apparatus was shown **not** to work; a method problem, not a phenomenon | #5 rerun under per-feature thresholds (DEC-023) |
| `phenomenon-null` | A real measurement of the world that found nothing | #3's probe (weak/no bridging) |
| `phenomenon-present` | A measurement that found something, at its rung | #6 (weak bridging, rung 2) |
| `defect-found` | The work exposed a flaw in prior work | #24 |
| `requirement-emerged` | The work exposed an unanticipated need | #23 (contract registry) |

**The load-bearing distinction is the first two rows against the middle two.**
`instrument-failed` and `phenomenon-null` look identical in a log — both read
"no significant result" — and are opposite in meaning. DEC-023 and DEC-024 are
the record of the project discovering that the same null was one, then the
other, then adjudicating. A vocabulary that cannot tell them apart at a glance
will keep costing that rediscovery.

### 3.3 Rung — how strong is the claim?

Reuses `TEST_VALIDATION_SPEC.md` §5 verbatim. Do not restate the ladder here;
cite it. A record's rung is its highest passed gate set, and the ladder is
already maintained there.

---

## 4. The program ledger

One machine-readable file: `program/ledger.jsonl`. Append-only, one JSON object
per line, like `findings.jsonl` — and for the same reason: a reader must be able
to verify the history from the repo.

**Schema.** Every record carries exactly these keys:

| Key | Type | Meaning |
|---|---|---|
| `id` | string | Sequential `P-001`, `P-002`, … Stable, orderable, unique |
| `ts` | string | UTC ISO8601, when the record was written |
| `issue` | integer | The GitHub issue this records the outcome of |
| `run_id` | string | The agent run that produced it (`<YYYYMMDD-HHMM>-<4 alnum>`) |
| `kind` | string | §3.1 value, without the `kind:` prefix |
| `outcome` | string \| null | §3.2 value; `null` while in flight |
| `rung` | integer \| null | §3.3 value if the outcome is a claim; else `null` |
| `results` | list[string] | Paths to result artifacts this outcome rests on, repo-relative |
| `decisions` | list[string] | `DEC-0NN` ids this outcome produced or rests on |
| `findings` | list[integer] | 1-based line numbers in `findings.jsonl`, if any |
| `blocks` | list[integer] | Issue numbers this outcome unblocks or redirects |
| `emergent` | list[integer] | Issue numbers this work **created** (the §6 path) |
| `note` | string | Short prose. Not a place for conclusions |

**Rules, enforced on append, not merely documented.**

1. **`outcome` requires `results` or `findings`.** An outcome with no artifact
   behind it is an assertion. (Mirrors `findings.jsonl`'s evidence bar.)
2. **`rung` requires `outcome`.** A rung on an in-flight record is a claim about
   nothing.
3. **`emergent` entries must name real issues** that were filed *by* this work.
   A record may not claim a requirement it did not surface.
4. **A `defect-found` outcome must cite the issue it found the defect in**, in
   `note`, so the traversal is closed. #24's record cites #11.

**Where it lives.** `program/ledger.jsonl`, beside `findings.jsonl` rather than
inside it, because `findings.jsonl` is gated evidence and this is program state.
A `program/README.md` explains the file to a newcomer.

**What it deliberately does not contain.** Issue titles, statuses, assignees, or
priority — all already in GitHub. Copying them creates the drift the coverage-map
decision warns against.

---

## 5. Derived views

Every view is **computed**, never stored. One command:

```
python3 program/view.py            # the program at a glance
python3 program/view.py --json     # machine-readable
python3 program/view.py --issue 24 # one issue's full traversal
```

| View | Answers |
|---|---|
| **Program state** | Per issue kind: counts by outcome class, open/closed, and the rung distribution for claims |
| **Traversal** | For one issue: its ledger records, the results they rest on, the findings, the DECs, and the issues it blocked or created |
| **Decision queue** | Every `kind:decision` issue and what it blocks — the human's inbox |
| **Health** | Gates defined vs wired (from `TEST_VALIDATION_SPEC.md` and the registry), findings by rung, and the label-hygiene count from §7 |
| **Open gaps** | Every `kind:gap` and `kind:defect` with its age in days |

**Why derived.** The same reason the coverage map is: a stored view is a second
source of truth that can silently disagree with the first. If a view is wrong,
the fix is to fix the record, not the view.

---

## 6. The unforeseen-requirement protocol

#23, #24, and #25 were all discovered mid-task. All three were filed ad hoc,
with no shared shape, and only #23 was labelled as what it was. This is the
protocol that makes that path first-class, because discovery-during-work is the
normal case in an exploratory program, not an exception.

**When an agent discovers something outside its claimed task's scope:**

1. **Do not fix it in the claimed task.** Scope creep inside a claim is what
   makes a done comment unverifiable. #24 found holes in #11's work *after* #11
   closed; fixing them inside #11 would have made #11's evidence unreviewable.
2. **File it before closing the claimed task**, search-then-file — file, then
   search again for a twin with a lower number and close yours if one exists
   (`MULTI_AGENT_WORKFLOW.md` §2a, unchanged).
3. **Give it a `kind:` label per §3.1.** A hole in shipped work is
   `kind:defect`, not `kind:gate`. A newly-needed capability is `kind:gap`.
4. **Record it in the claimed task's ledger entry** under `emergent`.
5. **State the blocking relationship honestly.** If the discovery blocks the
   claimed task, or another live task, say so and use a native dependency link.
   If it does not, say that too. #24 is the worked example of both halves: it
   does **not** block #11 (which had already closed and whose work it corrects),
   but it **does** block #15, because #15 cannot honestly repair the artifact
   tree while the gate it repairs against has two false-negative holes. A
   discovery's blocking edge is often to a *later* task, not to the one that
   surfaced it — which is precisely why it must be written down.

**The rule that makes this affordable:** an agent filing an emergent issue does
**not** have to solve it. The discovery is the deliverable. A filed-and-labelled
issue with a reproduction is a complete contribution.

---

## 7. Label hygiene, made checkable

The 7-unlabelled-issue measurement in §1 is the first thing this spec should fix
and the last thing it should trust a human to keep fixed.

**A new gate: `G-M1`.** For every open issue, exactly one `status:` label and
exactly one `kind:` label. Fails on zero or on more than one of either.

- **Tier 0.** It reads the committed issue-state cache
  (`tests/fixture_issue_state.json`) extended with labels — no network, per the
  G-E7 precedent. When the cache lacks an issue, `SKIP` with the reason, never
  pass.
- **Fixture rule applies.** `G-M1` ships a failing fixture (an issue with no
  kind) and a clean one, asserted in both directions like every other gate.

**Why a gate and not a convention.** Seven issues drifted within one day of the
label scheme being written down. A convention that is violated seven times on day
one is not a convention; it is a hope. `TEST_VALIDATION_SPEC.md` §4 is explicit
that a rule which cannot be checked is not enforced.

---

## 8. Scaling to results as they land

The remaining question is what happens when results arrive faster than a human
reads them. Three properties keep that manageable, each cheap:

1. **Every outcome is classifiable in one of six classes** (§3.2). A new result
   that fits none is a signal that the vocabulary is wrong — which is itself
   worth a `kind:gap` issue, not a bespoke label.
2. **`instrument-failed` and `defect-found` route to work; `phenomenon-null` and
   `phenomenon-present` route to judgment.** A null does not by itself imply a
   next experiment — it may imply the instrument needs repair (which is exactly
   what DEC-023→025 adjudicated). The ledger makes `blocks` explicit so this
   routing is visible instead of remembered.
3. **The decision queue is finite and visible.** `kind:decision` issues are the
   only ones a human must act on. Everything else can be claimed, closed, or
   left. That keeps the human's cost proportional to the number of *judgments*,
   not the number of tasks.

**The cap, stated plainly.** This system tracks *that* a judgment was made and
*what it rested on*. It cannot make the judgment. `TEST_VALIDATION_SPEC.md` §7's
Layer 4 is irreducible for the same reason PleaNP gives: satisfaction is not
internal to the system. The program ledger makes the queue shorter and the
traversal auditable; it does not shrink the judgment.

---

## 9. Task map

Filed as issues #28–#34, each sized to one agent run, with native `blocked by`
links. Only A (#28) is unblocked at filing.

| Task | Issue | Kind | Depends on |
|---|---|---|---|
| A — Adopt this spec; land the section 3.1 label axes | **#28** | `kind:protocol` | — |
| B — Backfill `kind:`/`status:` on all open issues | **#29** | `kind:repair` | #28 |
| C — Build `G-M1` label-hygiene gate + fixtures | **#30** | `kind:gate` | #28 |
| D — Build `program/ledger.jsonl` + `program/README.md` | **#31** | `kind:protocol` | #28 |
| E — Build `program/view.py`, the five section 5 views + fixture ledger | **#32** | `kind:gate` | #31 |
| F — Backfill ledger records for the completed experiment issues | **#33** | `kind:repair` | #31 |
| G — Adopt the section 6 protocol into `MULTI_AGENT_WORKFLOW.md` | **#34** | `kind:protocol` | #28 |

**Sequencing rationale.** A before everything: the labels and the adoption are
the decision. B and C are independent of each other — C can be built against
fixtures while the real tree is still red, exactly as #11 and #15 did — but a
gate whose first real run must fail is already precedented, so either order
works. D before E and F: no view without a ledger. G is independent of B–F and
can run in parallel with them.

**A note on the filing itself.** The six dependent issues were filed with
`status:blocked-needs-input` and a native `#28 blocks` edge. While doing so, an
intermediate step set *both* `status:available` and `status:blocked-needs-input`
on the same issue — the exact illegal state `MULTI_AGENT_WORKFLOW.md` §1a says
the sweep must repair, produced here by this very change and fixed within the
same session. That is the argument for `G-M1` (#30) arriving from its own filing:
the rule is easy to state and easy to violate by hand.

---

## 10. Open questions

1. **Is `program/` the right home, or should the ledger live beside
   `findings.jsonl` at the root?** Root keeps the two logs adjacent; `program/`
   fences the tooling. Leaning `program/` because `findings.jsonl` is gated
   evidence with a frozen schema and this is neither.
2. **Should `kind:` be a label or a GitHub issue *type*?** GitHub's native
   types are a closed set and cannot be extended, so labels are the only
   general option — but if GitHub ships configurable types, revisit.
3. **How does `outcome` relate to `verdict` in `findings.jsonl`?** They overlap
   on `null`/`flagged` but are not the same axis: a `flagged` verdict can be
   `instrument-validated` (the #5 control) or `phenomenon-present` (a real
   finding). The ledger's `outcome` is the interpretation; `verdict` is the
   label. Worth stating in the ledger README so neither is read as the other.
4. **Does the health view count gates by parsing the spec, or by reading the
   registry?** Parsing prose is brittle — the same objection that gave
   `target_model.txt`. Prefer the registry, and accept that "defined but not
   wired" then cannot be computed. Decide when E is built.

---

## 11. What this spec does not do

- It does not change any gate in `TEST_VALIDATION_SPEC.md`. It adds one (`G-M1`)
  and reuses the rest.
- It does not change `findings.jsonl` or its schema. #25 owns that.
- It does not make any judgment about results. It records that one was made and
  what it rested on.
- It does not introduce a second source of truth for task state. GitHub remains
  the system of record for issues; this ledger holds only the interpretation
  GitHub cannot express.
