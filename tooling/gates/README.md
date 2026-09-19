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
| `BROKEN` | Its ability to fail could not be demonstrated. **Not a pass.** |

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

Only the worked example is wired so far. Issues #10–#14, #16, #19, and #20 add
the rest; each names its gate ids in its Definition of Done.

| Gate | Checks | Traces to | Status |
|---|---|---|---|
| **G-R1** | Experiment header completeness — six fields, or three for a file declaring itself an infrastructure file | `experiments/README.md`; spec §3 | **wired** |

Spec §3 lists the remaining 23. Each must trace to a documented concern — the
suite asserts `traces_to` is non-empty for every registered gate.

## What these gates cannot do

They are **partial by construction, and say so.** They are text, schema, and
cross-reference checks over artifacts. They cannot tell whether a detector is
measuring what it claims — that is tier 1's job (G-D3–G-D5), and beyond tier 1
it is the human's. A tier-0 suite that passes is evidence that the *paperwork is
consistent*, nothing more.
