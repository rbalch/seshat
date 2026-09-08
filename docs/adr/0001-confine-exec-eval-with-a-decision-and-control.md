---
adr-id: ADR-0001
status: accepted
date: 2026-09-07
components: [controls/fitness, pyproject.toml, src/seshat/verify.py]
tags: [governance, ruff, exec]
decision-makers: [ryan]
related-adrs: []
supersedes: []
superseded-by: []
---

# ADR-0001: Confine exec/eval with a decision and control, not a bare lint exemption

## Summary (Y-Statement)

In the context of T-05 needing its one legitimate `exec` call past ruff's `S102`,
facing the choice of how to grant that exemption, we decided for a governed decision
plus an executable control and against a bare per-file-ignore or a repo-wide `S`
opt-in, to achieve a deliberate, checkable confinement of dynamic execution, accepting
the cost of authoring and maintaining one more decision and control pair.

## Context and Problem Statement

`src/seshat/verify.py` gained the repo's first `exec` call, and ruff's `S102` — on by
default — started failing the build. The rule this fix needs to satisfy is recorded as
DEC-1; this record is about which of three ways to grant the exemption was chosen, and
why the other two were rejected. See DEC-1 for the rule itself; it is not restated
here.

## Decision Drivers

* `S102` was never a chosen policy — it happened to be on by default, so the fact that
  `exec`/`eval` had zero sites repo-wide was an accident, not a decision anyone made.
* Whatever is chosen has to survive the *next* file that wants an `exec`, not just this
  one.
* The fix must not silently widen unrelated lint coverage as a side effect.

## Considered Options

1. **A bare per-file-ignore for `S102` on `verify.py`, no decision or control.** —
   Smallest possible diff; unblocks T-05 immediately.
2. **A decision (DEC-1) plus an `ast`-based fitness control, with the same
   per-file-ignore.** — Records the rule, and a control keeps enforcing it after the
   ignore is in place.
3. **Add `"S"` to `pyproject.toml`'s `extend-select`, then narrow back down with
   ignores.** — Turns on all of flake8-bandit and walks it back to just `S102`.

## Decision Outcome

Chosen option: **"a decision plus control (2)"**, because it is the only one of the
three where confinement survives the exemption that makes T-05 possible in the first
place — see DEC-1 for the rule and its reasoning.

### Consequences

* Good, because the per-file-ignore stops being the only thing standing between the
  repo and an unbounded `exec`/`eval` count — the control keeps that count at exactly
  one call, in exactly one file, regardless of what ruff configuration looks like
  later.
* Good, because the control is `ast`-based, so it cannot mistake `verify.py`'s own
  `compile(tree, '<verifier>', 'exec')` string argument, or a comment or docstring
  containing the word "exec", for a real call — false positives were the failure mode
  most worth designing against here.
* Bad, because it is one more decision and one more control file to maintain, where
  option 1 would have been a single line.

## Implementation Guidance

* **Affected paths:** `governance/decisions/DEC-1-exec-eval-confined-to-verify.md`,
  `controls/fitness/exec_confinement.py`, `pyproject.toml`
  (`tool.ruff.lint.per-file-ignores`).
* **Pattern:** follow `controls/fitness/view_naming.py` / DEC-0 for shape: parse with
  `ast`, never grep for a name; fail with `FAIL [DEC-N] <file>` plus an actionable
  `-> ...` line; succeed with `ok [DEC-N] ...`; `raise SystemExit(main())`.
* **Anti-pattern:** do not add `"S"` wholesale to `extend-select` — measured directly,
  it turns on `S101` across `tests/test_graph.py` (44 `assert` statements) for a rule
  this repo has no interest in enforcing, which is option 3's rejection reason above.

## More Information

DEC-1 states the enforced rule and is the source of truth for it; this ADR only
records why option 2 was chosen over options 1 and 3.
