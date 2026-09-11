# seshat — agent contract

Seshat surveys a codebase it did not write and stores what it learns as a **ledger of
verified claims**: one falsifiable sentence per row, each paired with executable Python
that re-checks it against the code graph. It is built this way because a prose summary
of code cannot be falsified and cannot rot loudly — a claim with a verifier does both,
so the same rows that answer "what does this do" also detect drift on the next run
without a full rescan.

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
   └─▶ docs/specs/<slug>.md, tasks/<slug>/<PREFIX>-NN-*.md, docs/adr/ (only if alternatives were rejected)

/orchestrate tasks/<slug>      ORCHESTRATOR (you, on develop, never in a worktree)
  │   ┌───────────────────────────── one task ─────────────────────────────┐
  ├──▶│ task-critic (root)   task file vs the tree → CLEAN, or the human    │
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
| `task-critic` (agent) | Reads a task file against the tree before any builder. Symbols exist, acceptance matches scope, criteria are testable. |
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
- **Reviewers start in the root checkout, not in a task's tree.** Every reviewer brief
  opens with that reviewer's own absolute path. A gate run in the wrong tree reviews the
  wrong code. The two reviewers get *different* trees — the boundary reviewer a detached
  checkout of its own, the code reviewer the builder's — because both verify by planting
  and reverting deliberate defects, and in one shared tree each sees the other's.
- **Blocked by a rule is a valid, wanted outcome.** Say so and stop. Do not raise a
  threshold, delete a pragma, or reach for `# noqa`. Reporting it is the most useful
  thing you can do; working around it quietly corrupts the experiment and nobody finds
  out for weeks.

## Architectural shape

```
                      target repo
                 .codegraph/  .seshat/ledger.db
                          ▲          ▲
        codegraph MCP ────┘          │ typed tool methods only
        (worker reads)               │
                                     │
  orchestrator ──▶ worker ──▶ verifier author ──▶ reflection ──▶ answer
  plain Python     CodeAct     Predict            Predict        CodeAct
   no model        model       model              model          model
        │                          │                   │            │
        └────────── graph helper API (the one way to read the graph) ┘
```

Two rules of shape carry the design. **Everything above the helper API talks to the code
graph through it, never through codegraph's own tables** — node ids there hash line
numbers and churn on any edit, so identity is `(file_path, qualified_name)` and the
backend stays swappable. **Only a passing verifier promotes anything into the ledger**;
conjectures, doc seeds and dead ends live in NOOA working memory, which decays, and the
ledger, which never does, holds nothing that has not been checked.

The model is used at exactly four generation points — worker, verifier author,
reflection, answer. Orchestration, the queue, the budget and every write to SQLite are
deterministic Python. That split is the experiment, not an implementation detail: if a
model creeps into the orchestration, the run stops being measurable.

## Always

- Read the target's code graph through the graph helper API (`plan.md` §6). Verifiers
  import nothing else.
- Store a claim as one falsifiable sentence with a verifier and a status. A summary is
  the rendered set of confirmed claims, never a stored paragraph.
- Ask for a verifier that checks from a *different* angle than the claim was derived
  from — callers rather than the body. A check that re-queries its own source proves
  nothing.
- Keep every row stamped with `repo_id` and the `run_id` that wrote it, so a future
  fleet store is a union of per-repo files.
- Cite claim id, qualified name, file path, line span, `verified_sha`, the claim's
  own status, and the verifier's last status. A stale citation says so inline.
- Keep the ledger inside the target repo at `.seshat/ledger.db`, gitignored, beside
  `.codegraph/`.

## Never

- Never hand-edit a generated file (`governance/views/**`, `governance/registry.json`).
- Never edit a control to make a failing change pass.
- Never write a claim into the ledger before its verifier passes. A refuted claim is
  recorded as refuted and kept; it is evidence about where the model misreads code.
- Never run the target's own code. Phase one is structural verifiers only; the
  `behavioral` kind is reserved for a later agent with a sandbox and a timeout.
- Never let the answer agent cite working memory, or write a sentence with no citation.
  Nothing found means say so.
- Never emit a governance rule. Seshat sets `candidate_rule` and counts sightings; a
  human and the rule-of-three decide what becomes a decision.
- Never store prose where a claim belongs, and never let a README statement into the
  ledger unverified — it is a hypothesis with `source='readme'` until a verifier passes.

## Working context (keep this current)

**Why it exists.** Two questions at work: a search index that answers "has anyone sorted
a list from third-party API X anywhere in our repos" by intent rather than tokens, and a
substrate an agent can rely on when modifying an unfamiliar repo. Both need a
description of a codebase that can be trusted and can announce when it rots. Chunk-and-
embed gives neither.

**The reframe that shaped everything.** A game is a black box learned by blind probing;
code is a glass box — the rule is in the source. So the loop is roughly one round per
unit: read → conjecture → one check → persist. The prediction step earns its keep as a
forcing function, not as forecasting: a summary that survived falsification captured the
contract, a summarize-each-file pass captured surface.

**Prior art.** NVIDIA NOOA (agent = one Python class, `...` body = generation point,
methods with bodies are tools for free). CyberGym is the template shape: one durable
accumulator, a few generation points, ~85% hand-written orchestration. `nooa-research.md`
has the reading order and the honest caveats about the vendor benchmarks.

**Stack.** Python 3.13, `uv`, `nooa[cli,viewer]`, SQLite. Codegraph MCP is
`@colbymchenry/codegraph`; set `CODEGRAPH_TELEMETRY=0`. Model is
`hosted_vllm/qwen3.8-27b` on a DGX Spark via vLLM at `LLM_HOST`, thinking on by default,
model string per role in config so any one role can move to a frontier model.

**Rejected.** NOOA memory as the ledger — its decay is recency × recall count, so a true
claim nobody asks about starts fading, which is exactly the row a drift scan needs a year
later. A reviewer agent — the verifier is the reviewer, one retry then refuted. Emitting
ADRs — the map is descriptive, decisions are prescriptive.

**Known risks.** A 27B model writing bad verifiers (the refuted rows measure this). A
verifier that restates its own claim and proves nothing. Hallucinated candidate rules
flooding the ledger. Codegraph gaps — Python decorators came back empty, external calls
sit in `unresolved_refs`, so decorator claims need an `ast` fallback before they can be
verified. If workers flail at CodeAct on a 27B model that is a finding about the
capability ladder, not a bug; `PurePythonStrategy` is the fallback.

**Out of scope for phase one.** Vectors, fleet-wide merge, languages other than Python,
running target code, the prose-notes ablation arm (rows carry a `mode` tag for it).

**Audience.** Ryan, dogfooding. First target is `~/code/labs-OO-Agents`; the phase-one
bar is the five acceptance questions in `plan.md` §9, answered with citations, then an
edit and a rescan where `seshat drift` names exactly the rotted rows.

**Current work (2026-09-04).** Plan and decision log written to `docs/specs/docs/`;
nothing implemented yet — `src/seshat/` is an empty package. Build order: ledger schema →
graph helper API → one worker turn on one unit → queue and budget → reflection → CLI →
`ask`. A two-tool CodeAct smoke test against the Spark comes before any of it.

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
