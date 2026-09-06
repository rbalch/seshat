# NVIDIA NOOA — Object-Oriented Agents (research notes)

Working notes for a sandbox project exploring NVIDIA's **NOOA** (NeMo Labs
Object-Oriented Agents) framework and the ideas in its launch post. Ryan is
noodling on what to actually build; this file preserves the shared understanding
so a fresh agent doesn't start cold.

## Primary sources
- Blog: https://developer.nvidia.com/blog/six-agent-harness-capabilities-for-higher-model-performance/
- Repo: https://github.com/NVIDIA-NeMo/labs-OO-Agents
- Quickstart ladder (01→15, standalone runnable feature demos):
  https://github.com/NVIDIA-NeMo/labs-OO-Agents/tree/main/examples/quickstart
- CyberGym example (real, compact, good reference):
  https://github.com/NVIDIA-NeMo/labs-OO-Agents/tree/main/examples/cybergym/nooa_cybergym
- ARC-AGI-3 example (large research codebase, 50KB+ solver — mine the skill, skip the plumbing):
  https://github.com/NVIDIA-NeMo/labs-OO-Agents/tree/main/examples/arc_agi_3
- The world-model skill (the transferable gold — full text embedded below):
  examples/arc_agi_3/skills/interactive-game-solver/SKILL.md

## The thesis
Harness design alone can cause double-digit benchmark swings. NOOA collapses
prompt templates + tool schemas + callbacks + workflow graphs into **one Python
class**: methods are capabilities. "An agent is a single Python class."

## The six capabilities
1. **Typed I/O** — validated args/returns, not free-form text.
2. **Pass by reference** — model holds live Python objects + bounded previews,
   not serialized dumps. Data stays a variable; only the *question asked of it*
   enters context.
3. **Code as action** — model writes Python in a Jupyter-style REPL (control flow
   + N calls per turn), not N tool round-trips.
4. **Programmable loop** — orchestration is plain, human/model-writable Python.
5. **Explicit object state** — durable typed state on the agent object, not smeared
   through the transcript (survives summarization/compaction).
6. **Model-callable harness APIs** — model can inspect/manage its own context blocks
   and event history.

## Benchmark claims (frontier models; vendor paper — treat with healthy skepticism)
| Domain | Benchmark | Score | Model | Note |
|---|---|---|---|---|
| SWE | SWE-bench Verified | 82.2% | GPT-5.5 | ~1.1M tok/task vs 2.2M for 78.2% baseline |
| Cyber | CyberGym L1 | 86.8% | GPT-5.5 | no network; top open-source agent |
| Reasoning | ARC-AGI-3 | 50.2% mean RHAE | GPT-5.5 | $17.85/game; 85.1% w/ GPT-5.6-sol @ $13.3 |

Ablations (the numbers worth trusting because they isolate the harness):
- World-modeling skill: **+8.5** over a prose/hypothesis-driven baseline.
- Memory subsystem: **+11.8** over file-based notes.
- Combined ~20.3 points ride on two prompts + a SQLite store — i.e. how much is
  "framework" vs "two well-chosen prompts + durable memory" is a fair open question.

Efficiency story: no compaction needed → append-only transcript → prefix cache keeps
hitting. Median sessions peak 22–72k against 200–400k windows. ~half the token cost.

## The mental model (settled through reading the source)
- A class docstring → system prompt. A method docstring → the task.
  Type annotations → the I/O contract. `Annotated[str, "..."]` on the **return**
  type tells the model the output shape. **The class IS the prompt.**
- `...` (Ellipsis) body = **generation method**: the model implements it, fresh,
  **on every call**. It is NOT "built up"/accumulated over time.
- Normal method with a real body = **deterministic tool**: runs as written AND is
  automatically exposed to the model as a callable tool (no schema, no decorator,
  no registration).
- Leading-underscore / `Annotated[..., hidden]` fields stay OUT of the model-visible
  state block. Model gets a bounded capability (e.g. `get_stock()`) or a bounded
  `__str__` render instead of the raw dict. Pass-by-reference as access control.

### Where "learning" actually comes from — IMPORTANT
There is **no ML learning**. No weights move, nothing is trained. Three things share
the word:
1. Weight learning — not happening.
2. In-context learning — lives in transcript, dies with the window.
3. **Artifact learning** — code/notes/typed state written to files + SQLite + the
   agent object, read back later. **This is NOOA's entire contribution.**

Concretely (CyberGym): the `...` worker method (`find`) does NOT get smarter. A
hand-written accumulator object (`Portfolio`, "the only shared state") hoards verified
crashes; each fresh `find` call sees the current portfolio in its context. Learning =
your accumulator + memory store, NOT anything the framework trains. The method is
hardcoded; only the *content* it discovers is emergent.

## CyberGym shape (good template — ~85% your code, ~15% model)
Roughly 20 concrete methods, exactly 4 generation (`...`) points:
- `Finder.find(...)` — `...` — the worker's job spec.
- `Expander.expand(...)` — `...` — variant-hunting strategy.
- `CyberGymAgent._review(...)` — `...` — reviewer criteria.
- plus return annotations as output contracts.
Everything else (`submit`, `solve`, `_wait`, `pending_crash_clusters`, `apply_review`,
`_make_finder`, …) is hand-written orchestration. `Portfolio` is the durable accumulator.

For a FIRST build: copy the *shape* (one accumulator object, one `...` worker, one
`...` reviewer). Skip the async/concurrency (three agent types, task juggling).

## The world-model / "learning" loop, distilled
When an agent must learn an unknown system, make it write a **predictor** (executable
code), not **notes** — code can't hedge, so contradiction is caught on the next tick —
and store that predictor where the context window can't erode it (workspace files +
SQLite). Both halves required: skill without memory loses 11.8; memory without skill
loses 8.5.

Loop:  predict → act → diff (retrodict) → revise predictor → persist.
Only the *diff* crosses back into context, not the full state.

## Project ideas discussed (testbed needs: hidden-but-learnable rules, fast ticks,
## crisp prediction target, ground truth the agent doesn't hold; build the ablation
## in from day one: {code-predictor vs prose-notes} × {durable memory vs fresh context})
- **A. Sealed simulator** (recommended first build) — small deterministic sim (mutated
  Conway, tiny physics box) exposed ONLY as `step(action)->obs`; source off-limits.
  You know true physics, so "did it recover the rules?" is gradeable. Inject a rule
  change mid-run, watch whether retrodiction notices. Metric = prediction-accuracy
  learning curve, not win/lose.
- **B. Undocumented API/protocol** (Ryan's instinct; most real payoff) — wrap a
  service behind a docstring-stripped client; model builds a generated client library +
  a written list of quirks. Predict status code + response shape. Use a LOCAL fake to
  avoid network noise polluting the signal.
- **C. Custom/mutated roguelike or text adventure** — closest to ARC; risk: known games
  test recall, not science. Custom only.
- **D. Reverse-engineer a black-box function** — sharpest scoring (`mine(x)==theirs(x)`
  over a fuzz corpus); narrower, memory matters less.
- **E. Flaky/legacy codebase** — learn blast radius via edit+test; most useful, slowest
  ticks. Later, not first.
- **F. Two-player hidden opponent policy** — model an adversary; best memory stress test.

Suggested quickstart reading order: 01 → 03 → 08 (context blocks) → 10 (skills) →
12 (memory). That's the spine; 08/10/12 are where the ARC result comes from.

## Caveats to keep honest
- Vendor paper, vendor benchmarks, unnamed baselines, NVIDIA runtime (OpenShell).
- Every headline number is on a frontier model — nothing isolates design-causes-gain
  from strong-model-given-room. Falsifiable test: same harness across a capability
  ladder; if the gap widens on weaker models it's real scaffolding.
- "Code as action" predates this (CodeAct, smolagents); novelty is the typing/OO wrapper.
- ARC's 45-line skill is a bespoke, hand-injected prior for a benchmark where
  world-modeling is known in advance to win.
- "No rule leakage across 13,335+ logs" is an effort metric, not a security property.
- RHAE = per-level action efficiency vs an unseen human baseline, **squared**, weighted
  by level index (see skill below). NOT raw win rate.

---
## REFERENCE: the ARC-AGI-3 world-model skill (Apache-2.0, verbatim)
The single most transferable artifact — a ~45-line prompt that turns a model into an
empirical scientist. This is what a "learning" prompt looks like in the flesh.

```markdown
# Interactive Game Solver

## The game
The game presents a **64×64 grid** of colors (hex `0`–`f`), one state per turn on your
`game_states` queue (each state carries a live status header). Games have multiple
**levels** to clear. Discover the unknown rules by experiment.
Legal actions are those in `available_actions`: `UP`/`DOWN`/`LEFT`/`RIGHT`, `USE` (interact),
`CLICK x y` (column x, row y, 0-indexed), `RESET` (restart level), `UNDO`. Parse with
`self.grid_array(state["grid_rows"])` and compute in numpy; `self.trajectory()` is the full
history and `diff_summary` reports changed cells. Reply with `self.submit_actions([...],
rationale)` — the **sequence** of actions that carries out your current plan.

## Scoring (RHAE)
Score = per-level **action efficiency** relative to an unseen human baseline, **squared**.
Every action spent on a level counts (exploration, failed attempts, RESET, UNDO); an
unsolved level scores 0. Level i of n carries weight i: the environment score is the
weighted mean of the level scores, capped by the weighted share of completed levels.

## World model
Persist a compressed model as helpers (`self.write_helper(name, src)`; reload with
`self.load_helpers()`, call `self.h.<module>.<fn>`):
1. **`encode(grid) -> z`** — the **latent state**: the few fields that drive the game, each
   named in a `Z_SCHEMA` with type + range.
2. **`predict(z, action) -> z'`** — the dynamics.
3. **Retrodict each turn** — compare `predict(z, a)` to the real next state; a mismatch is the
   signal to refine `encode`/`predict` until predictions hold.

## Search & planning
Once `predict` is trustworthy, **plan with it**: search (BFS / greedy / best-first) over
action sequences in latent space for one reaching the goal or a sub-goal, then
`submit_actions` the plan. While `predict` is weak, explore to discover the mechanics.

## Long-Term Memory
Consult your store (`<knowledge_api>`) before deciding; at a new level, recall the relevant
prior knowledge first. Each turn, after seeing results, record **hypotheses** (status +
deciding test), **knowledge** (confirmed dynamics, action semantics, failures),
and **long-term plans** (the sub-goal chain and solve procedure).

Reflect at level boundaries. On completion, summarize what generalizes (mechanic, winning
policy, transferable `encode`/`predict`, ruled-out hypotheses) and carry it forward. Before a
RESET, record what the attempt confirmed, what failed, and the next-attempt plan.

## Turn contract
Every turn ends with one call: `self.submit_actions([...], rationale="predict: ...")` with at
least one action — it submits your move and ends the turn. Do your analysis and any
knowledge/helper writes before it.
```

---
## APPLICATION THREAD: codebase mapping / vectorization (Ryan's dev idea)

Ryan explored applying the NOOA loop to **mapping & vectorizing codebases** (his
`~/code/new-project` governance-harness project is the backdrop — it already has a
codegraph MCP covering many languages, and a decision→control→view ratchet). Two valid
company use cases, pursue both eventually:
- **Search index** — "has anyone sorted a list from third-party API X anywhere in our
  repos?" Intent/behavior search, NOT snippet search.
- **Coding substrate** — an agent that reliably modifies these repos.

### The core reframe
An unfamiliar codebase is a NOOA-style system to "learn the rules of" — BUT with one
decisive disanalogy Ryan caught:
- A game is a **black box**: rules hidden, learned blind over many probe rounds; bounded
  only by a small discrete state/action space.
- Code is a **glass box**: the rule is in the source, readable directly. So the loop is
  ~one round per unit (read → conjecture the contract → ONE boundary poke → persist),
  not many blind rounds. It feels infinite only under the wrong (black-box) framing.

### What we predict (this was the crux confusion — settled)
NOT outputs for infinite inputs, and NOT "ADRs". We conjecture the code's **hidden rules**
and falsify each against an oracle. Two loops:
- **Loop A — behavioral (true prediction):** predict what a function returns → RUN it →
  check. Oracle = execution. You genuinely can't look it up.
- **Loop B — structural (falsification, not forecasting):** conjecture an invariant
  ("API never imports DB") → check against codegraph/corpus → refine. Oracle = the code.

Why predict at all when you can read the source:
1. Catches the misread — the skimmed `except`, the silent mutation, the off-by-one.
   "I read it and I'm sure" is exactly where you're wrong.
2. **Compression is the real reason.** Being forced to predict-and-get-caught is what
   separates understanding from plausible paraphrase (NOOA's `encode->z` / Z_SCHEMA step).
   A summary that survived falsification captured the *contract*; a "summarize each file"
   pass captured *surface*. The first answers intent queries; the second returns confident
   garbage. The prediction loop is a forcing function for trustworthy summaries.

Bounded because: guess the RULE not the outputs (one sentence covers infinite inputs);
source is finite & readable; finite units; conjecture picks the few boundary probes; and
you climb **leaves-up** so confirmed sub-models become facts higher callers reuse
(understanding composes — never re-derive against infinity). "Large" = the cost
conversation (go deep only on repos you live in), never "infinite".

### The falsifier ladder (pick the rung per claim; language matters differently at each)
- **Tier 0 — compiler/types (free, already ran).** Typed targets (Rust/Java/Go) are
  EASIER to map, not harder — signatures are verified truth for free.
- **Tier 1 — structural invariants (cheap, ~language-agnostic).** A Python function over
  AST/codegraph. Ryan's "no API file imports DB" lives here. This IS a new-project fitness
  control pointed at a foreign repo. Use tree-sitter (uniform parser across languages) or
  the resolved codegraph edge — prefer the graph over textual import-grep (re-exports/
  aliases cause false negatives). "import" is Python framing; Rust `use`, Java `import`,
  Go blocks. ~60-70% of search value, uniform across the fleet, cheap.
- **Tier 2 — behavioral characterization (expensive, language-native).** Must run code:
  native test (`cargo test`/JUnit, agent writes target-language) OR drive a boundary from
  Python (subprocess CLI / HTTP / FFI — reaches only what's exposed). Reserve for
  load-bearing logic.
Cost & language-coupling concentrate at the bottom. Search-index question ≈ Tier 0-1
(cheap, broad); coding-substrate question ≈ Tier 2 (expensive, deep, hot repos only).
These two rungs map cleanly onto Ryan's two company questions.

### Map ≠ ADRs (important inversion)
- ADR/decision = **prescriptive**, human intent, "should."
- The map = **descriptive**, discovered, "is."
- Bridge = Ryan's rule-of-three ratchet: an invariant the code *already obeys everywhere*
  is a CANDIDATE decision. Discovery → ratchet → ADR. The map is the INPUT to the
  governance canon, not the canon. (This is the synthesis: NOOA discovery front-end feeds
  the new-project hardening back-end. Risk: a finding-predictor that hallucinates rules
  floods the ledger — apply the same falsifiable "does the middle bin honestly fatten" test.)

### Product shape
Per code unit, persist to SQLite: **what** (verified behavioral contract — for intent
search) + **how/deps** (calls Stripe, mutates cache — the edges for "who else calls API X")
+ confidence + verifying test id. Reflection pass consolidates/dedupes across units.
Vectorize the **verified summaries**, NOT raw code — that's the entire edge over
chunk-and-embed for intent queries (raw embeddings match tokens; idiomatic sorts share
zero tokens across Rust/Java/C#). Tests double as a **staleness detector** a vector index
can't have: code drifts → suite fails → the failure points at the exact rotted DB row.
The test is proof-of-work, not the deliverable; the deliverable is the verified summary+graph.

### Next concrete step (where we left off)
Run the loop live on one gnarly real function from a repo on Ryan's machine: show the
conjecture → the one boundary poke → the two rows that land in SQLite vs. the mush a naive
summary would store.
