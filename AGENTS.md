# seshat — agent contract

<!-- TODO: one paragraph. What this project is, and the one sentence that explains
     why it is built the way it is. An agent reading only this file should know what
     it is working on. -->

This repo runs a ledger governance harness: architectural rules live as decisions,
each decision is backed by an executable control, and CI fails on drift. Read
`docs/governance-harness.md` once for why.

## Read this first

**Binding rules live in `governance/views/RULES.md`.** It is generated. Read it before
writing code. Every rule in it is enforced by CI; violating one fails the build.

**Never read `governance/decisions/` for rules.** It retains superseded records on
purpose. A superseded rule in your context steers you toward the exact pattern this
project abandoned. History is for humans; the view is for you.

> The generated view is `RULES.md`, not `AGENTS.md`, so it can never be confused with
> this file. This file is the contract — how to behave. That file is the rules — what
> is true. See DEC-0.

**This file is hand-written, and it never restates an enforced rule.** The narrow hazard
is copying a `DEC-N` rule here, where the copy drifts from its control and quietly
becomes a lie. The `Always` / `Never` lists below are the *shape* of the design, for
orientation. The enforced wording lives in the view, and the view wins on any
disagreement.

## The contract

- **Never edit code to evade a control.** If a rule blocks you and you think it is
  wrong, supersede it: author `DEC-N+1`, set the old decision to `status: superseded`
  with `superseded_by: DEC-N+1`, update the control and its pragma, run `make views`,
  commit it together. A human reviews that diff. Changing a rule is a visible act, never
  a silent code tweak.
- **New rules ship with controls.** A governing rule arrives with an executable control
  and its `governance: enforces DEC-N` pragma in the same change, or is explicitly
  marked `enforcement: warn` with a justification.
- **One behavior, one decision.** State a rule in exactly one decision and reference its
  ID elsewhere. Never restate a rule in two places.
- **Do not author rules speculatively.** When asked to add a rule, apply the triage in
  the `finding-triage` skill first. Most dislikes are already lintable or are pure
  taste; only the articulable, recurring middle earns a control. A refusal to write a
  brittle rule is worth more than coverage.

## How work gets done here

Two skills, in order. **`planner`** turns a conversation into a spec and task files.
**`orchestrate`** turns task files into reviewed, squashed PRs against `develop`, and
feeds every finding into the ledger instead of letting it evaporate.

```
/planner                       you + the planner, until the plan is agreed
   └─▶ docs/specs/<slug>.md, tasks/<slug>/T-NN-*.md, docs/adr/ (only if alternatives were rejected)

/orchestrate tasks/<slug>      ORCHESTRATOR (you, on develop, never in a worktree)
  │   ┌───────────────────────────── one task ─────────────────────────────┐
  ├──▶│ builder (worktree)   codegraph init → acceptance tests RED → GREEN │
  ├──▶│ boundary-reviewer    live rules + this project's architectural seams│
  ├──▶│ reviewer             red-then-green proof, correctness, tests, shape│
  └──◀│ findings → you judge → builder → re-review → APPROVE, score ≥ 4/5  │
      │ squash to one commit → push → PR to develop                        │
      └───────────────────────────────────────────────────────────────────┘
  ▼  ═══ per task, after the PR is open. This is what makes it a ledger repo. ═══
  ├─ triage every finding → Bin 1 (lintable) / Bin 2 (systemic) / Bin 3 (taste)
  ├─ log sightings in docs/ledger-findings.md — orchestrator only
  ├─ a Bin 2 finding on its third sighting → control-author
  └─ next task, if its dependencies have merged; otherwise wait for the human
```

**Tests at the acceptance boundary come first.** The task file's acceptance criteria
become tests, committed alone, watched failing, before any implementation. The reviewer
checks out that commit and confirms the red. Unit tests below the boundary are the
builder's call. A criterion that turns out wrong is a planning finding for the human,
never a test to quietly rewrite.

**Branches.** Work lands on `develop` by PR, one PR per task, one squashed commit per
PR whose body says what changed and why. `develop` to `main` is a human's PR. A task
that depends on an unmerged task waits; nothing builds on an unreviewed branch.

**The triage step is the point, and it is the one people skip.** A loop that fixes
findings and forgets them is exactly the problem the harness exists to solve: the
correction evaporates, the next session repeats it, and you review it again forever.
Skipping triage means running the experiment while discarding the data.

### The pieces

| | What it is for |
|---|---|
| `planner` (skill) | Plan with the human. Writes the spec, the task files, an ADR if earned. |
| `orchestrate` (skill) | Runs task files through build → review → PR → triage. Start here for any task. |
| `builder` (agent) | One task, in a worktree. Acceptance tests first. Never evades a control. |
| `boundary-reviewer` (agent) | Live rules and this project's architectural seams. Reports; never edits. |
| `reviewer` (agent) | Red-then-green proof, correctness, tests, maintainability. Owns `review.md` / `review.json`. |
| `finding-triage` (skill) | Sort one dislike into a bin. Apply the rule of three. |
| `control-author` (agent) | Turn a thrice-sighted Bin 2 finding into a decision plus control. |
| `ledger-ops` (skill) | Harness mechanics: author, supersede, add a control, debug a red gate. |
| `tasks/README.md` | The task file format. |

### When not to use the loop

A one-line fix, a doc edit, or a question. The loop costs several subagent round-trips;
spending them on a typo is theatre. Run `make check` and commit. **But still triage
anything you disliked along the way** — sightings accumulate regardless of how the
change was made.

### Things that will bite you

- **`make check` fails fast.** A red gate reports only the *earliest* failing stage, not
  every failure. Re-run the whole gate after a fix rather than assuming one error was
  the only one.
- **Touched a decision? Run `make views`.** The view and `registry.json` are generated
  from `governance/decisions/`. A stale one fails the *next* task's gate for reasons
  that look unrelated to it.
- **Reviewers start in the root checkout, not the worktree.** Every reviewer brief
  opens with the worktree path. A gate run in the wrong tree reviews the wrong code.
- **Blocked by a rule is a valid, wanted outcome.** Say so and stop. Do not raise a
  threshold, delete a pragma, or reach for `# noqa`. Reporting it is the most useful
  thing you can do; working around it quietly corrupts the experiment and nobody finds
  out for weeks.

## Architectural shape

<!-- TODO: the diagram or the two paragraphs that explain how this system is put
     together, and which seams the controls exist to guard. An agent that does not
     understand the shape will violate it confidently. Replace the example below. -->

```
<layer A>  ──▶  <layer B>  ──▶  <layer C>
```

## Always

<!-- TODO: the shape of the design, for orientation. Never a restatement of a DEC-N
     rule — point at the view instead. Delete these examples. -->

- Keep the dependency direction one way.
- Put secrets behind the named abstraction, never in a repo file, a log line, or a
  response payload.

## Never

<!-- TODO: negative space is first-class. What must this project never do? -->

- Never hand-edit a generated file (`governance/views/**`, `governance/registry.json`).
- Never edit a control to make a failing change pass.

## Working context (keep this current)

<!-- TODO: this is the section that earns this file's existence — the background an
     agent cannot derive from the code. Why this project exists, what was tried and
     rejected, prior art being followed, the stack, known risks, what is out of scope,
     who the audience is, and what is being worked on right now. Convert relative dates
     to absolute. Delete a line the moment it stops being true; a stale working-context
     section is worse than an empty one. -->

**Current work:** <!-- TODO -->

## Commands

```bash
make check       # the single gate: controls → views --check → governance → tests
make views       # regenerate governance/views/RULES.md + registry.json
make governance  # integrity + drift check (the linchpin)
make controls    # every controls/fitness/*.py, plus ruff and ty
make test        # pytest
```

`make check` is the only gate. Run it before you say a change is done.

---

Rules come from `governance/views/RULES.md`. Change a rule by supersession, never by
edit.
