---
id: DEC-4
title: Code comments, docstrings, and test section headers never cite review-round or finding numbers
status: accepted
kind: negative
created: 2026-09-23
superseded_by: null
controls:
  - path: controls/fitness/review_round_refs.py
    type: fitness_fn
    enforcement: block
    pragma: supported
---

## Rule

No comment or docstring under `src/` or `tests/` cites review-process history by
round or finding number — "fix round 1", "fix round 2, item 1", "finding 4", in
any letter case. Task ids (`T-15`, `PT-01`) are house style and are never
flagged; they name a task file, which survives a squash. `docs/` is out of
scope: it narrates review history on purpose, as history.

## Context

Every PR in this repo lands on `develop` as one squashed commit
(`AGENTS.md`, "Branches"). A citation to "fix round 2, item 1" or "finding 4"
names a review artifact — a round of a build loop, an item in a reviewer's
findings list — that the squash deletes on merge. The comment survives; the
thing it points at does not. A reader six months later, or a model reading the
file cold, has no way to resolve the reference and no way to tell that it is
unresolvable — it reads exactly as precise as a working citation.

`docs/ledger-findings.md` F-64 recorded this at three sightings, which is this
project's bar for a decision (`docs/ledger-findings.md`, "Rule of three"):
PT-01's builder wrote one, PT-02's builder wrote another after the brief
explicitly said not to, and PT-02's own search then found the pattern already
on `develop`, predating both — seven instances across six test files, from at
least four earlier tasks, because nobody had searched for it. Re-running that
search while authoring this control found four more in `tests/test_task_symbols.py`
("Fix round 1" through "Fix round 4", capitalized, which a case-sensitive grep
had missed) — eleven pre-existing instances in total, all reworded in the same
change that adds this control.

The claim is narrow and machine-checkable on purpose. It does not reach for
"never mention the review process" — a comment explaining *why* a fix exists
("closes a gap a reviewer found") is fine and common in this codebase; only a
citation to a round or finding **number** is flagged, because only the number
is what a squash actually erases. "Finding" and "round" as ordinary English —
"a code review finding", "this run found flaky output" — are untouched: the
pattern requires "finding" immediately followed by a digit, which no
legitimate use in this repo's `src/` or `tests/` currently produces (verified
directly: `git grep -niE 'finding' -- src tests` turns up no false positives
against the pattern once the digit requirement is applied).

## Consequences

`controls/fitness/review_round_refs.py` scans every `.py` file under `src/`
and `tests/`, excluding `tests/fixtures/` (per DEC-2's precedent — committed
probe-repo data) and any hidden or `__pycache__` directory. It reads real
lexical comments via `tokenize` and real docstrings via `ast.get_docstring` on
the module and every class/function/async-function definition — never an
arbitrary string literal, so a test fixture holding source-as-a-string (for
example `tests/test_verify.py`'s sandboxed-code constants) is never mistaken
for this repo's own commentary.

It goes **red**, naming the file and line, when a comment or docstring matches
`fix\s+round` or `finding\s+\d` (case-insensitive), and exits non-zero. It goes
**green** on a tree with no such citation, including one that names a task id
or discusses the review process in prose without a round or finding number.

Proved directly: a scratch file with `# See fix round 2, item 3 for why this
exists.` under `src/` turned the control red, naming the file and line;
removing it turned the control green again.

## Rejected alternatives

- **Flag any comment containing the word "finding" or "round".** Rejected.
  This repo's own `docs/ledger-findings.md` vocabulary — "ledger finding",
  `candidate_rule`, a code-review "finding" as ordinary English — appears
  inside `src/`/`tests/` docstrings and comments already (e.g.
  `src/seshat/units.py`'s "Finding, not a fix:", several regression tests'
  "matching the reviewer's finding"). None of these are a citation to a
  numbered review artifact, and flagging the bare word would fire on all of
  them — a control that fires on correct code, which this harness treats as
  worse than no control. *Positive recast:* require a digit immediately after
  "finding", which is present in every real violation found and absent from
  every legitimate use checked.

- **Match on raw substring search across the whole file, not lexical
  comments/docstrings.** Rejected. `tests/test_verify.py` and similar files
  hold Python source as string literals — test data for the verifier sandbox —
  and some of that data legitimately contains the literal text `def check(`
  and similar. A raw substring scan cannot distinguish this repo's own
  commentary from sandboxed content under test; `tokenize`/`ast` can, for
  free, because a `#` or docstring inside a string literal is never a
  `COMMENT` token or a real docstring node.

- **Scan the whole repo, including `docs/`.** Rejected. `docs/ledger-findings.md`
  is a deliberate history of review rounds and findings, by design
  (`AGENTS.md`'s ledger-ops description) — "fix round" and "finding N" appear
  there dozens of times as the intended subject matter, not as a dangling
  pointer into deleted review state. Scoping to `src/` and `tests/` matches
  exactly the class of file this decision is about: code that ships and is
  read long after the review that produced it is gone.

- **Leave it as a soft/per-brief instruction rather than a control.** Rejected
  at this sighting count. F-64's own note is direct evidence against relying
  on a brief: PT-02's builder repeated the pattern *after* being told not to,
  which is exactly the rule-of-three trigger this ledger exists to act on.
