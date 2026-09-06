# Seshat phase one — ledger, scanning loop, CLI

Plan source: `docs/specs/docs/plan.md` (the design) and `docs/specs/docs/decisions.md`
(every settled question, Q1–Q38). This spec does not restate them; it cuts them into
tasks. Section references below (`plan §N`) point at `plan.md`.

## Goal

A `seshat` CLI that indexes a Python repo with codegraph, runs the scanning loop
(plan §5) with a local vLLM model, writes a ledger of verified claims to
`.seshat/ledger.db` inside the target, rolls confirmed claims into concepts, and
answers questions from the ledger with a citation on every sentence. A second run on
an edited repo marks exactly the rotted rows stale and `seshat drift` names them.

## Approach

One Python package, `src/seshat/`. Layers, bottom up:

```
tests/fixtures/target/         hand-written Python repo + committed .codegraph/codegraph.db
src/seshat/config.py           LLM_HOST, model string per role, thinking flag
src/seshat/ledger/             schema + typed store; the only writer of ledger.db
src/seshat/graph.py            Graph helper API over .codegraph/codegraph.db (plan §6)
src/seshat/verify.py           run one verifier's source against Graph; tautology gate
src/seshat/units.py            enumerate units, ast_hash, changed/vanished/stale diff
src/seshat/agents/             verifier_author, worker, reflection, answer (NOOA)
src/seshat/scan.py             orchestrator: run row, seeds, queue, pool, budget
src/seshat/cli.py              scan status units claims concept drift ask
scripts/smoke_codeact.py       two-tool CodeAct against the Spark, by hand
```

The model is used at the four generation points in `src/seshat/agents/` and nowhere
else. Everything in `ledger/`, `graph.py`, `verify.py`, `units.py`, `scan.py` and
`cli.py` is deterministic and tested without a model.

**Testing without the Spark and without Node.** `.codegraph/codegraph.db` is a plain
SQLite file, so the fixture repo commits its index and tests open it read-only. No MCP
daemon runs in tests. Agent tasks test their control flow with
`nooa.unifiedllm.FakeLLMClient` installed via `set_llm`; tests that need a real
model are marked `integration` and skip unless `LLM_HOST` is set.

## Out of scope

Everything plan §10 lists after phase one: behavioral verifiers, the prose ablation
arm, vectors, fleet merge, non-Python targets, governance controls from candidate
rules. Also: running the dogfood scan in CI, and any `DEC-N` seeded from
`decisions.md` (governance rules come from `finding-triage`, not from plans).

## Decisions

All design decisions are in `decisions.md` (Q1–Q38) and are cited by task. Added in
this planning session, no ADR (no alternative was live long enough to re-litigate):

- Fixture target with a committed codegraph index instead of Node in CI.
- `FakeLLMClient` for agent control-flow tests; `integration` marker for the Spark.
- Verifier tautology gate is deterministic code in `verify.py`, not a prompt rule alone.
- `ask` is its own task after the CLI, since it edits the same module.
- The Spark smoke test is a script plus skip-gated tests, run by a human.

## Tasks

| id | title | depends_on |
|---|---|---|
| T-01 | Fixture target repo with committed codegraph index | [] |
| T-02 | Package skeleton, console script, role config | [] |
| T-03 | Ledger schema and typed store | [T-02] |
| T-04 | Graph helper API with ast decorator fallback | [T-01, T-02] |
| T-05 | Verifier runner with tautology gate | [T-03, T-04] |
| T-06 | Unit enumeration, ast_hash, drift diff | [T-03, T-04] |
| T-07 | Verifier author agent | [T-03] |
| T-08 | Worker agent | [T-05, T-07] |
| T-09 | Scan orchestrator | [T-06, T-08] |
| T-10 | Reflection agent and candidate rules | [T-03] |
| T-11 | Read-only CLI | [T-09, T-10] |
| T-12 | Answer agent and `seshat ask` | [T-11] |
| T-13 | Spark smoke script and integration tests | [T-08] |

Parallel lanes: {T-01, T-02} → {T-03, T-04} → {T-05, T-06, T-07, T-10} → T-08 →
{T-09, T-13} → T-11 → T-12.

## Open questions

- Whether `qwen3.8-27b` can drive CodeAct at all. T-13 answers it; if not, the worker
  and answer agents move to `PurePythonStrategy` in config (plan §8). Owner: Ryan.
- Whether `hosted_vllm/…` through LiteLLM honours `extra_body.chat_template_kwargs`
  for `--no-thinking`. T-13 checks it. Owner: Ryan.
- The dogfood acceptance (plan §9, five questions and the drift edit) runs by hand on
  `~/code/labs-OO-Agents` after T-12 merges. Owner: Ryan.
