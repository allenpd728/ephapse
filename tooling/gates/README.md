# Tier-0 integrity gates

Ports the fixture-gate pattern from Maith's `tooling/gates/` (itself ported from
PleaNP). The authority is
[`docs/reference/TEST_VALIDATION_SPEC.md`](../../docs/reference/TEST_VALIDATION_SPEC.md)
§3–§4; this file is the operator's reference.

> **Revision note (DEC-026).** The failures that motivated this harness shared
> one shape: *a plausible-looking artifact produced by a process whose
> correctness was never checked*. The last was different in kind — the max-NPMI
> instrument **fired, passed its cutoff, and tracked the wrong pair**, with its
> top-ranked pair identical with and without injection (DEC-023, adjudicated in
> DEC-024). That is not a gate that cannot fire; it is a statistic answering a
> different question, and it needs G-D9. The spec's §3 gained G-D9/G-D10 for it.

## Why this exists

Four failures in one session shared one shape: **a plausible-looking artifact
produced by a process whose correctness was never checked.**

- a multiplicative-correction layer that could not fire, reported as "no
  significant pairs"
- a positive control that activated neither of its intended feature groups
- an isolate score of 0.996 computed entirely from cases where nothing moved
- a per-feature causal claim at 36% SAE reconstruction error

Each read as a result. None was. Ephapse's discipline had been prose in
`MULTI_AGENT_WORKFLOW.md` and `AGENT_HANDOFF.md`, enforced by agent diligence —
which is exactly the enforcement that failed four times. These gates turn as
much of that prose as is mechanically checkable into code.

## The two tiers, never merged

- **Tier 0** — no model load, no torch, no network. Schema, text, and
  cross-reference checks over artifacts. Runs in CI. 29 of the 37 gates (see
  the count history in `docs/AGENT_HANDOFF.md` § Validation layer — this number
  has moved twice since the harness landed).
- **Tier 1** — requires loading the probed model. The detector-validity gates.

**A tier-0 pass is not "gate passed."** Maith's formulation, adopted verbatim:

> Treating a grep pass as a gate pass is itself an integrity hole.

A green tier-0 run means the artifacts are internally consistent and their
evidence is present. It does **not** mean a detector measures what it claims —
that is tier 1, and beyond tier 1 it is the human's.

## The one rule that makes the rest work

**Every gate ships a fixture that makes it fail, and the runner proves it does.**

`run_all.py` asserts, per gate:

1. it is **silent on the clean fixture**, and
2. it **fires on its failing fixture**.

If (2) cannot be demonstrated — no failing fixture registered, fixture missing,
or the gate stays silent on it — the gate is reported **`BROKEN`** and the run
fails. A gate that cannot fail is not a check.

This is not ceremony. Maith's first exit-code verification was itself vacuous: a
string anchor silently missed and the "test" passed against a broken scanner.
The same thing happened while building this harness: G-R1's infrastructure
regex matched the phrase *"does NOT declare itself an infrastructure file"* in
its own failing fixture, silently exempting it from the full header. The runner
reported `BROKEN`, which is exactly the signal that rule exists to produce.

## Usage

```bash
python3 tooling/gates/run_all.py              # all gates, human report
python3 tooling/gates/run_all.py --json       # machine-readable
python3 tooling/gates/run_all.py --gate G-R1  # one gate
python3 tooling/gates/tests/test_gates.py     # the harness's own tests
```

Exit codes: `0` when every gate is `PASS`; `1` when any gate is `FAIL` or
`BROKEN`. That is the contract CI consumes.

## Statuses

| Status | Meaning |
|---|---|
| `PASS` | Silent on its clean fixture **and** fires on its failing fixture. |
| `FAIL` | Fired on the clean fixture — the gate is wrong or the fixture is dirty. |
| `BROKEN` | Its ability to fail could not be demonstrated: no failing fixture registered, fixture missing, the gate stayed silent on it, or it **raised**. **Not a pass.** |
| `SKIP` | Fires on its failing fixture (so it *is* a check), but part of its input was unavailable on the clean side. Reported with the reason. **Never a pass** — the exit code stays non-zero unless `--allow-skip` is given. |

Two rules that follow from the incident history:

- **A gate that raises is `BROKEN`, not a crash.** An exception means the gate
  cannot be shown to work, which is what `BROKEN` says. The runner catches it and
  carries the exception text into the report. (Learned building G-E7, whose
  `.relative_to(REPO)` raised on a relocated path and took the suite down.)
- **`SKIP` must not mask a reportable violation.** G-E7 checks `run_id` format
  (offline, always reportable) and issue state (needs a cache). A malformed
  `run_id` returns `FAIL` even when the cache is missing; only the *unavailable*
  half produces `SKIP`.

## Layout

```
tooling/gates/
  README.md              — this file
  run_all.py             — the runner: discovery, both-directions contract, exit code
  validate_*.py          — gate modules; each self-registers via register()
  tests/
    conftest.py          — puts tooling/gates/ on sys.path
    test_gates.py        — per-gate both-directions + harness-behaviour tests
    fixtures/
      <gate>/{clean,failing}_*.py
```

## Adding a gate

1. Write `validate_<area>.py` beside `run_all.py`.
2. Implement `check(path) -> list[str]` (empty list = pass; deterministic; no
   network, no model, no LLM).
3. Call `register(Gate(id=..., name=..., tier=0, check=..., clean_fixture=...,
   failing_fixture=..., traces_to=...))`. **Both fixtures are mandatory.**
4. Make the failing fixture a **near miss**, not an obviously-broken file. A
   gate that only fires on an empty file satisfies the letter of the fixture
   rule and none of its purpose.
5. `python3 tooling/gates/run_all.py --gate <ID>` must report `PASS`, and
   deleting the failing fixture must report `BROKEN`.

## Gate inventory

Five gates are wired so far (G-R1, G-E1, G-E2, G-E6, G-E7). Issues #11–#14, #16, #19, #20, and #22 add
the rest; each names its gate ids in its Definition of Done.

| Gate | Checks | Traces to | Status |
|---|---|---|---|
| **G-R1** | Experiment header completeness — six fields, or three for a file declaring itself an infrastructure file | `experiments/README.md`; spec §3 | **wired** |
| **G-E1** | Findings schema — parses, required keys present, no undeclared keys | `findings.jsonl` header | **wired** |
| **G-E2** | `null_model`, `correction`, `n` non-empty — the evidence bar | issue #4 DoD | **wired** |
| **G-E6** | Append-only — record count >= committed high-water mark | `findings.jsonl` header; spec §10 Q4 | **wired** |
| **G-E7** | `issue` cites a closed-done issue; `run_id` matches format | workflow § Run-ids | **wired** (SKIPs without the issue cache) |

Spec §3 lists the remaining 19; issues #11–#14, #16, #19, #20, #22 add them.
Each must trace to a documented concern — the suite asserts `traces_to` is
non-empty for every registered gate.

### Two spec §10 questions resolved while building G-E1/E6

**Q3 — is the gate or the header prose authoritative for the schema?** The gate,
but with one deliberate deviation recorded here: **G-E1 does not reject unknown
keys outright.** The three committed records carry `kind`, `injection`, `result`,
and `note`, which the header prose never listed. Rejecting them would
retroactively invalidate the project's only recorded evidence. Instead a fixed
`REQUIRED` set must be present *and* every extra key must appear in
`KNOWN_EXTENSIONS`, so an addition is explicit but real records survive. The
required-key list is identical to the header's, so there is no divergence to
reconcile; the extensions list is the single place the gate is more permissive
than the prose.

**Q4 — does G-E6 need git history?** No. The clone is shallow, so the gate reads
a committed integer, `findings.highwater`, and requires the current record count
to be `>=` it. Raising the mark is a separate reviewable commit. Its limitation
is stated in the gate: deleting a line fires, but *editing* a line in place does
not — count-based checking cannot see that without history.

## What these gates cannot do

They are **partial by construction, and say so.** They are text, schema, and
cross-reference checks over artifacts. They cannot tell whether a detector is
measuring what it claims — that is tier 1's job (G-D3–G-D5), and beyond tier 1
it is the human's. A tier-0 suite that passes is evidence that the *paperwork is
consistent*, nothing more.
