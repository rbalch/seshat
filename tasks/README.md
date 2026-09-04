# Tasks

One directory per plan, one file per task. The `planner` skill writes them; the
`orchestrate` skill consumes them. A task file is a self-contained brief: an agent given
only that file, `AGENTS.md`, and `governance/views/RULES.md` has everything it needs.

```
tasks/
└── <plan-slug>/
    ├── T-01-<slug>.md
    ├── T-02-<slug>.md
    └── ...
```

## File format

```markdown
---
id: T-02
plan: <plan-slug>                  # tasks/<plan-slug>/, matches docs/specs/<plan-slug>.md
title: Add the repository layer for orders
status: todo                       # todo | in_progress | in_review | done | blocked
depends_on: [T-01]                 # ids that must be merged first; [] if none
files:                             # what this task expects to create or edit
  - src/seshat/orders/repository.py
  - tests/orders/test_repository.py
rules: [DEC-0]                     # DEC ids from RULES.md that plausibly apply; [] if none
---

## Goal

One paragraph. What exists when this task is done that does not exist now, and why the
plan needs it.

## Scope

1. Numbered, concrete, checkable items.
2. Each one is something a reviewer can confirm is present or absent.

## Non-scope

- What a builder will be tempted to do and must not. Later tasks, adjacent refactors,
  "while I'm here" cleanups.

## Acceptance

Runnable checks, each with the command and the expected result. These are the contract
the builder writes tests against **before** implementing. If an acceptance criterion
cannot be expressed as a test, say so and name what a human checks instead.

- `uv run pytest tests/orders/test_repository.py -q` → exit 0, covers: create, get by id,
  get missing raises `OrderNotFound`
- `make check` → exit 0

## Context

Facts a fresh agent cannot derive from the tree: prior decisions from the spec, the
shape of neighbouring code it should match, external constraints, what was tried and
rejected. Link the spec section rather than restating it at length.

## Manual QA

What the human looks at after merge, if anything, and what "correct" looks like.
`None.` is a valid answer.
```

## Rules

- **`depends_on` is a merge dependency**, not a "nice to have first". A task lists a
  dependency only when it cannot be built or tested without that task's code present.
  Dependent tasks wait; they never build speculatively on an unmerged branch.
- **`files` is the parallelism signal.** Two tasks with no dependency and disjoint
  `files` can run in separate sessions at the same time. Overlapping `files` means run
  them in order, even with no logical dependency. The list is an expectation, not a
  fence; a builder that needs to touch something else reports it.
- **Acceptance criteria are the test contract.** The builder turns them into tests
  first and watches them fail. If a criterion turns out to encode a wrong assumption,
  that is a planning error to report, not a test to quietly rewrite.
- **`status` is maintained by the orchestrator**, updated on develop when a task's PR is
  opened (`in_review`) and merged (`done`). Builders never edit task files.
- **Small enough for one review loop.** If a task needs more than roughly one day of
  human-equivalent work, or touches more than one architectural layer, the planner splits
  it.
