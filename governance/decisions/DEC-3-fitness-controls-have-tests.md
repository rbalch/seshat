---
id: DEC-3
title: Every fitness control has its own test module
status: accepted
kind: preserved
created: 2026-09-10
superseded_by: null
controls:
  - path: controls/fitness/control_test_coverage.py
    type: fitness_fn
    enforcement: block
    pragma: supported
---

## Rule
Every `.py` module directly under `controls/fitness/` (other than `__init__.py`)
has a corresponding `tests/controls/test_<stem>.py` module, and that module
defines at least one `test_*` function. A control with a missing or empty test
module fails the build.

## Context

This is the narrow, checkable end of a broader pattern this project's ledger has
now recorded four times: a branch whose deletion or inversion no test notices.
`F-26` (T-08) — an optional parameter's "does nothing when omitted" contract
survived 49 tests when mutated. `F-38` (CT-01) — a tool's central membership
guard could be deleted outright with all twelve of its acceptance tests still
green. `F-45` (DEC-2) — `controls/fitness/exec_confinement.py` itself had gated
every build for days with no test of its own, and hid two live false negatives
until a reviewer deleted its exclusions by hand and watched nothing happen. Most
recently, T-14 (PR #16) found the same shape a fourth time in
`Graph.decorators`' `ast`-fallback branch in `src/seshat/graph.py`: mutating
`if raw is None: return []` to `return None` left the whole suite green.

The general claim — "no branch in this repo can be silently deleted or inverted
without a test noticing" — is not something a static control can check. It is
mutation testing, and `F-38`'s own notes already rejected running that in CI as
disproportionate: slow, noisy, and exactly the kind of blanket mechanism this
project's `finding-triage` skill exists to head off. Attempting it as a fitness
control would fire on plenty of correct code that simply has not been mutated
and checked, which is the one failure mode this harness treats as worse than
missing a rule entirely.

What is checkable is narrower, and `F-45`'s own notes named it directly: **a
fitness control is code that decides whether every other build passes, so it
needs tests at least as much as the code it judges** — arguably more, since a
broken control fails silently rather than loudly. Verified directly against the
tree before this decision was written: `controls/fitness/exec_confinement.py`
had gained 26 tests in `tests/controls/test_exec_confinement.py` after `F-45`,
but its sibling, `controls/fitness/view_naming.py`, still had none — the DEC-0
control had gated every build since this project's first commit with nothing
pinning either of its two branches (the forbidden-name check and the
required-file check). `tests/controls/test_view_naming.py` was written
alongside this decision to close that gap before the new control could go
green.

This decision governs only `controls/fitness/`, deliberately. It does not
address `F-26`, `F-38`, or T-14 directly — those live in ordinary source and
application code, and no version of "this branch is covered" that avoids
mutation testing is available for arbitrary code. What earns a control here is
narrower than the family and does not pretend otherwise: controls are the one
class of code in this repo where an untested branch can invalidate every rule
this harness enforces at once, which is a materially different blast radius
than an untested branch anywhere else.

## Consequences

`controls/fitness/control_test_coverage.py` goes **red** if any module under
`controls/fitness/` lacks a `tests/controls/test_<stem>.py` module, or if that
module exists but contains zero functions named `test_*` at any nesting depth
(including inside a class, and including `async def`). It goes **green** when
every control module has a non-empty test module.

The check is presence-and-non-triviality, not coverage. It cannot tell whether
the tests that exist actually exercise a control's guard clauses — that
question is answered by the reviewer discipline both `F-38` and `F-45` already
describe informally (delete a guard, rerun the suite, confirm red), which
remains a review practice rather than a control because nothing about "did a
human or agent do this during review" leaves anything in the repo tree for a
script to inspect.

Any future control under `controls/fitness/` ships with its test module in the
same change, or this control fails immediately — there is no grace period.

## Rejected alternatives

- **Run mutation testing in CI against every control (or every module).**
  Rejected. `F-38` already named the cost — slow and noisy — and a mutation
  suite that flags correct-but-unmutated code as a build failure is precisely
  the "fires on correct code" failure this harness treats as worse than no
  control. *Positive recast:* require the cheap proxy (a non-empty test module
  exists) as a floor, and leave mutation-style verification to the reviewer
  discipline `F-38` and `F-45` both already describe.

- **Encode "every guard clause a change introduces gets deleted once and the
  suite re-run" as the control**, per `F-38`'s own proposed remedy. Rejected as
  a control, not as a practice: it is a runtime instruction for a human or
  reviewing agent during a review round, and it leaves nothing in the repo a
  script can check after the fact — there is no artifact distinguishing "a
  guard was deleted and the suite went red" from "nobody tried." *Positive
  recast:* keep it as the standing reviewer-brief instruction it already
  informally is; `AGENTS.md` and the `orchestrate` skill are the right home for
  it, not `controls/fitness/`.

- **Require every branch in a control to be independently exercised (branch
  coverage threshold).** Rejected as unenforceable without a coverage tool
  wired into the gate, which is closer to the mutation-testing proposal than to
  this decision's narrower claim, and which would need per-control tuning to
  avoid penalizing defensive code that is intentionally hard to hit (e.g. an
  `OSError` guard around a read that never fails on a clean checkout).
  *Positive recast:* the presence-of-tests floor in this decision, plus the
  reviewer discipline for anything sharper.

- **Extend this rule to every Python module in the repo, not just
  `controls/fitness/`.** Rejected. That is the general false-success family
  (`F-4`, `F-10`, `F-13`, and by extension `F-26`/`F-38`/T-14), already
  evaluated and refused twice in this log for lacking a mechanically checkable,
  non-brittle form. Controls are singled out because their blast radius is
  categorically larger: a silently broken fitness control disables enforcement
  of a rule for everyone, every commit, until someone notices by hand.
