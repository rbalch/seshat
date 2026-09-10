---
id: DEC-1
title: exec and eval are confined to src/seshat/verify.py
status: superseded
kind: negative
created: 2026-09-07
superseded_by: DEC-2
controls: []
---

**Superseded by [DEC-2](DEC-2-exec-eval-confined-to-verify.md).** DEC-2 carries the
same prohibition forward and widens its scope to every directory that holds
first-party Python in this repo, `scripts/` included — a gap this decision's own Rule
text left uncovered (see `docs/ledger-findings.md` F-42). DEC-2's Context also corrects
a false claim made below: ruff's `S102` was never active in this repo, so the
"accidental guard" this decision describes never existed. This record is kept as
written, uncorrected, because the ledger is a record, not a constraint — see
`governance/scripts/check_governance.py`'s scoping note that checks apply to live
decisions only.

## Rule
A call to `exec` or `eval` may appear only in `src/seshat/verify.py`. No other file
under `src/`, `controls/`, `governance/`, or `tests/` (excluding `tests/fixtures/`)
may call either.

## Context

**This is a seeded rule, not a discovered one.** DEC-0 is the precedent for saying so
plainly instead of dressing a seed as a discovery: the rule of three was not run here.
It is promoted on sight because T-05 introduces the repo's first `exec` — mandated by
its task file and by `AGENTS.md`, which requires structural verifiers to run a model's
`check(graph)` source in-process; the subprocess alternative is explicitly forbidden by
that task's Non-scope. Ryan approved seeding it explicitly.

Before T-05, `exec`/`eval` were blocked repo-wide, but by accident: ruff's `S102` is
enabled in ruff's default rule set, and this repo's `pyproject.toml` never opted out of
it, so the count of `exec`/`eval` sites sat at zero without anyone deciding it should.
Granting `src/seshat/verify.py` a per-file-ignore for `S102` buys T-05 its one
legitimate call, but it also lifts `S102`'s guard from every other file — the next
`exec` written anywhere else would still be flagged by ruff, and the cheapest fix at
that point would look like appending another line to `per-file-ignores`, one file at a
time, until the ignore list quietly became the actual policy. This decision and its
control exist so the accidental guard is replaced with a deliberate one before that
happens, not after.

Scope note: this control governs **where** dynamic execution may appear, not whether
one particular call is safe. `verify.py`'s own containment for its one call is two
things together: an `ast` walk that rejects any `import` statement outside `json`/`re`
before the source is ever executed, and an explicit allow-list of builtins in the exec
namespace (no `__import__`, `open`, `eval`, `exec`, `compile`, or anything else that
reaches the interpreter or the filesystem directly). Together these close the *direct*
routes — a verifier cannot `import os`, cannot call `__import__('os')`, cannot `open()`
a file, cannot nest another `eval`/`exec`.

**They do not close attribute-traversal escapes, and the gap is arbitrary code
execution, not mere introspection.** A verifier that reaches a live module through
some object's internals without going through any builtin at all —
`().__class__.__bases__[0].__subclasses__()`, or
`json.__loader__.__class__.__init__.__globals__['sys']` — can run any command the
Seshat process itself can run: `os.system`, an arbitrary subprocess, a filesystem
write, a network call. The only thing standing between that and a reported `pass` is
that no verifier has been written to do it. This is accepted for phase 1 solely
because verifier source is model-authored against a trusted code graph, not
attacker-supplied — it is not safe against an adversarial verifier author, and closing
it for real requires process isolation, deferred to phase 1.5's behavioral agent and
its sandbox. This decision exists so an `exec`/`eval` written somewhere else, with no
gate and no allow-list at all, cannot bypass even this partial containment by
appearing outside the one file that has it.

## Consequences

`controls/fitness/exec_confinement.py` walks the `ast` of every `.py` file under `src/`,
`controls/`, `governance/`, and `tests/` (skipping `tests/fixtures/`, which is committed
probe-repo data, never linted or rewritten) looking for an `ast.Call` whose function is
a bare `ast.Name` with `id` in `{'exec', 'eval'}`. It goes **red**, names the offending
file, and exits non-zero if that call appears anywhere but `src/seshat/verify.py`. It
goes **green** on the tree as it stands, including `verify.py`'s own
`compile(tree, '<verifier>', 'exec')` — a string literal, not a call to the `exec`
builtin, so an `ast`-based control does not confuse the two the way a grep would.

`pyproject.toml` carries a per-file-ignore for `S102` scoped to `src/seshat/verify.py`
alone, referencing this decision by ID rather than restating the rule.

## Rejected alternatives

- **A bare per-file-ignore for `S102` on `verify.py`, with no decision or control.**
  Rejected. It solves T-05's immediate lint failure but removes the only thing
  currently stopping a second `exec` from appearing anywhere else in the tree — ruff's
  `S102` was never a chosen policy, so once one file is exempted there is no longer any
  guard on the rest of the repo, deliberate or otherwise.

- **Add `"S"` to `extend-select` and then narrow it back down.** Rejected. `S101`
  (`assert` used) is not enabled by ruff's default set, so turning on all of `S` newly
  flags every `assert` in `tests/test_graph.py` — 44 of them, measured directly — for a
  rule this repo has no interest in enforcing. The blast radius is disproportionate to
  the one behavior actually worth controlling.
