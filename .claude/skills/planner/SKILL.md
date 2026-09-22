---
name: planner
description: Plan a piece of work with the human, then write the spec, the task files, and an ADR if the plan chose between real alternatives. Runs in the main session because planning is a conversation. Use at the start of any feature, milestone, or change larger than a one-line fix — before any code is written.
---

# Planner

You are planning, not building. Nothing under `src/`, `tests/`, `controls/` or
`governance/` changes during this skill. Your output is three kinds of document, and
you write none of them until the human says the plan is agreed.

```
conversation ──▶ agreed plan ──▶ docs/specs/<slug>.md
                                 tasks/<slug>/<PREFIX>-NN-<slug>.md   (one per task)
                                 docs/adr/NNNN-<slug>.md       (only if alternatives were rejected)
```

## 0. Read first

- `AGENTS.md` — the project, its architectural shape, the Always/Never lists, and the
  working context. The plan has to fit the shape; if it cannot, that is the first thing
  to raise.
- `governance/views/RULES.md` — the live rules. A plan that will collide with a `DEC-N`
  is either wrong or a supersession, and the human decides which before any task exists.
  Never read `governance/decisions/` for rules.
- `docs/specs/` and `docs/adr/` — prior plans and decisions. Do not re-decide something
  already decided; cite it.
- `make tasks` — anything not yet `done`. A new plan that overlaps unfinished work needs
  to say so. `tasks/<slug>/` is untracked (only `tasks/README.md` is in git); the files
  live on this machine and the merged PRs hold the shipped briefs.

## 1. The conversation

Work with the human until the plan is agreed. Your job is to make the plan precise
enough to break into tasks, and to surface what they have not said.

- **Ask the questions that change the work.** Scope boundaries, what is explicitly out,
  the acceptance the human will actually check, which existing code this must match,
  what happens on failure. Do not ask what you can read from the tree.
- **Ask what the human wants to inspect.** Every artifact the work produces — a
  database, files on disk, outbound calls, logs, an in-memory model — and how they want
  to look at it. Each one gets a way to look: a CLI command, a `make` target, a script,
  or a Python snippet they can paste into a REPL. These are features, planned as tasks.
- **Ask the demo order.** What does the human want to run first, second, third? That
  order, not the layer order, is the task order.
- **Push back once, with a reason, then defer.** If a choice looks wrong say so plainly
  in a sentence or two. If the human reaffirms, that is the decision.
- **Name the alternatives when there are real ones.** If the plan picks between two or
  more viable approaches, say which, why, and what was given up. That is what becomes
  the ADR.
- **Check the plan against the rules and the shape.** A plan that crosses a seam in
  `AGENTS.md` or a rule in `RULES.md` is raised here, never discovered by a builder.

Stop iterating when the human says the plan is agreed. Do not write files before that.
Do not ask "shall I write it up?" as a substitute for finishing the conversation.

## 2. The spec — `docs/specs/<slug>.md`

The plan in prose, for a human to read and for tasks to link back to. Short. Sections:

- **Goal** — what exists when this is done, one paragraph.
- **Approach** — how, at the level of components and seams. A diagram if the shape is
  non-obvious.
- **Out of scope** — explicit.
- **Decisions** — choices made in the conversation, each in one line, with the ADR id
  if one was written.
- **Tasks** — the ordered list of task ids and titles, with the dependency edges, and
  for each one line: what the human can run or look at once it merges.
- **Open questions** — anything deferred, and who owns it.

## 3. The tasks — `tasks/<slug>/<PREFIX>-NN-<slug>.md`

Follow the format in `tasks/README.md` exactly. First pick the plan's id prefix: `T` if
no other plan exists, otherwise a short uppercase prefix from the slug that no directory
under `tasks/` already uses (`critic-tooling` → `CT`). Every id in the plan carries that
prefix, and the PR titles will too. Per task:

- **Self-contained.** A builder gets the task file, `AGENTS.md` and `RULES.md`, nothing
  else. Anything it needs beyond those is in the task's Context section, or linked to a
  spec section by heading.
- **Acceptance as runnable checks**, each with the command and expected result. These
  become the tests the builder writes first, so they must describe behaviour at the
  boundary of the task, not internals. "Returns the order or raises `OrderNotFound`" is
  acceptance. "Uses a dataclass" is not.
- **`depends_on` only for merge dependencies.** Ask: can this be built and tested with
  the dependency's code absent? If yes, it is not a dependency. Dependent tasks stack:
  they branch off the predecessor's branch, and their PR targets it.
- **`files` honest and complete.** This is the only signal the human has for which
  tasks can run in separate sessions at once.
- **`rules`** — the `DEC-N` ids that plausibly apply, so the builder reads those first.
- **Sized for one review loop.** Split anything a reviewer could not hold in one pass.
  Crossing layers is fine; a slice usually does. Split by feature, not by layer.

Order the ids so a dependency always has a lower number than its dependents.

### Slice for the human, not the layers

Every PR is a chunk the human can check out, run, and poke at. A plan that is twelve
tasks of models, repositories and services before anything runs is the failure this
section exists to prevent: the human merges blind and finds out at task twenty that
none of it does what they meant.

- **T-01 runs.** The first task is a skeleton the human can start: the CLI answers
  `--help`, the server returns 200, `import {package_name}` works and one call does
  something. No features, but proof the thing is alive and how to run it.
- **Each later task adds one thing the human can try.** A new command, a new flag, a new
  function they can call from a REPL, a new table they can query. Cut through layers to
  get there: a thin slice across model, storage and CLI beats a complete storage layer.
- **Make artifacts visible when they appear.** The task that first writes a database,
  a file, or an outbound call also gives the human a way to see it, or the very next
  task does. Nothing the human asked to inspect stays hidden for more than one task.
- **Parallelise across features, not layers.** Once the skeleton merges, independent
  commands or flags are independent tasks with disjoint `files`, each with its own
  Try it. Run them side by side.
- **Plumbing-only tasks are allowed, and flagged.** CI, a pure refactor, a migration
  with nothing new to see. Its Try it says `None — <reason>` and the spec names it as
  plumbing. If more than one task in a row is plumbing, re-cut the plan.
- **Try it is concrete.** Exact commands or a paste-able Python snippet, run from a
  fresh checkout of the branch, and what the human should see: the output shape, the
  rows in the table, the file that appears. "Verify it works" is not a Try it.
- **Try it is a contract, not a note.** The builder runs it red then green, the reviewer
  re-runs it as a required check, the human runs it last. Write steps an agent can run
  without judgement: no GUI clicks, no "looks right". Where a person must look, say what
  to compare against.

After writing the files run `make tasks PLAN=tasks/<slug>`. It validates the frontmatter,
the prefix and the dependency edges, and shows every task `ready` or `blocked`. A
message instead of a listing is a planning error to fix before hand-off.

## 4. The ADR — only when earned

Write one only if the conversation chose between real alternatives that a future reader
would plausibly re-litigate. Use the `creating-adrs` skill and its MADR format, into
`docs/adr/`. A plan that had one obvious approach produces no ADR, and that is the
common case.

An ADR records a design choice. It is **not** a governance decision: it has no control,
it is not enforced, and it never appears in `RULES.md`. If the conversation concluded
that something should be *enforced*, that is a finding for `finding-triage`, subject to
the rule of three like anything else. Do not seed a `DEC-N` from a plan.

## 5. Hand-off

Report the spec path, the task ids with their dependency edges and one line each of
what the human can try after it merges, which tasks can run in parallel with which, and
the ADR path if any. Then the two ways to run it:

```
/orchestrate tasks/<slug>            # every task, in dependency order
/orchestrate tasks/<slug>/T-03-*.md  # one task, in a second session, if it is independent
```

---

Plan in conversation, write on agreement, one runnable slice per task, acceptance at
the boundary, an ADR only when something was actually decided.
