# Seshat — brownfield codebase surveyor (phase-one plan)

Seshat is a NOOA-based agent that surveys an existing codebase and produces a
**ledger of verified claims** about it. Each claim carries executable code that
re-checks it, so a later run detects drift without a full rescan. Confirmed claims
are rolled up into **concepts** with citations. A chat CLI answers questions from
the ledger and cites its sources down to file and line.

Phase one answers two questions: *what does the database end up looking like*, and
*what does the scanning loop look like*. Vectorization and fleet-wide search are
phase two.

Companion docs: `nooa-research.md` (background, the reframe from black box to glass
box, the falsifier ladder) and `decisions.md` (every settled question, with answer).

---

## 1. Core reframe (settled in research, restated)

- Code is a **glass box**. The loop is one round per unit: read → conjecture →
  one check → persist. Not blind probing.
- The atomic record is a **claim**: one falsifiable sentence plus a verifier.
  A "summary" is the rendered set of confirmed claims. Never stored as prose.
- The map is **descriptive** ("is"). ADRs are **prescriptive** ("should"). A
  structural invariant that already holds everywhere is a *candidate* rule for a
  governance ledger. Seshat flags candidates; it does not write rules.
- Verifiers are proof-of-work and a **staleness detector**. The deliverable is the
  verified ledger plus its citation graph.

## 2. Roles and where the model is used

Everything is one Python package. NOOA supplies the agent classes; the model is
used at exactly four generation points. Everything else is deterministic code.

| Role | NOOA strategy | Model? | Job |
|---|---|---|---|
| Orchestrator | plain Python | no | run bookkeeping, priority queue, worker pool, budget, progress |
| Worker | CodeAct (thinking on) | yes | for one unit: read it via codegraph tools, conjecture N claims, ask for verifiers, record results |
| Verifier author | Predict → typed `Verifier` | yes | one shot: turn a claim into Python against the graph helper API, with expected result |
| Reflection agent | Predict over a claim batch | yes | read confirmed claims, emit typed `Concept` objects with evidence ids |
| Answer agent | CodeAct (thinking on) | yes | search the ledger via tools, answer with a citation on every sentence, refuse if nothing found |

Worker pool size is a flag, default 1. Parallel workers use `asyncio.gather` with
one worker instance per unit, the CyberGym pattern.

No reviewer agent. The verifier is the reviewer. A refuted claim gets one retry
with the refutation shown to the worker, then it is recorded as refuted. Refuted
claims are kept: they are data about where the model misreads code.

## 3. Two pools of memory

| | Working memory | Ledger |
|---|---|---|
| Store | `nooa-memory` (SQLite, hashing embedder) | own SQLite schema (`.seshat/ledger.db` in target repo) |
| Decay | yes (recency × recall count, Ebbinghaus) | never |
| Holds | doc seeds, hypotheses, style notes, dead ends, episodes | units, claims, verifiers, concepts, runs |
| Written by | worker via `remember()`; NOOA reflection on top | typed tool methods on the agent classes |
| Reflection | NOOA built-in stays on, for tinkering | own `ReflectionAgent` writes concepts |

**Promotion rule:** a hypothesis becomes a claim only when its verifier passes.
Concepts may cite only confirmed claims. Nothing in the ledger decays; drift is
detected by rerunning verifiers, not by forgetting.

Why not put claims in NOOA memory: its decay is driven by time since last access
and how often a memory was recalled. A true claim nobody asks about for two weeks
starts to fade, which is exactly the row a drift scan needs a year later. The only
escape hatches (protected type list, importance ≥ 8) mean fighting the library.

## 4. Ledger schema (SQLite, one file per target repo)

Every row carries `repo_id` and is stamped with the `run_id` that wrote it, so a
future central store is a union of per-repo files.

```sql
runs(
  id TEXT PK, repo_id, commit_sha, started_at, finished_at,
  model, thinking INT, workers INT,
  budget_units INT, budget_minutes INT, budget_tokens INT,
  units_done INT, claims_confirmed INT, claims_refuted INT, tokens_used INT,
  mode TEXT,              -- 'claims' now; 'prose' arm reserved for the ablation
  status TEXT             -- running | stopped_budget | stopped_complete | failed
)

units(
  id TEXT PK,             -- sha of (file_path, qualified_name)
  repo_id, file_path, qualified_name, kind,      -- class | function | method | module
  start_line, end_line,
  ast_hash TEXT,          -- comments/whitespace stripped; drives incremental rescan
  inbound_calls INT,      -- queue priority
  first_seen_run, last_seen_run, last_scanned_run,
  status TEXT             -- pending | scanned | changed | vanished
)

claims(
  id TEXT PK, repo_id, unit_id → units,
  text TEXT,              -- one falsifiable sentence
  kind TEXT,              -- structural (phase one) | behavioral (later)
  source TEXT,            -- code | readme | docstring
  mode TEXT,              -- claims | prose (ablation tag)
  status TEXT,            -- conjectured | confirmed | refuted | stale
  confidence REAL,
  candidate_rule INT, rule_sightings INT,   -- rule-of-three input; nothing more
  created_run, verified_run, verified_sha,
  retries INT
)

verifiers(
  id TEXT PK, repo_id, claim_id → claims,
  source TEXT,            -- Python; runs against the graph helper API only
  expected TEXT,          -- JSON of the expected result
  depends_on TEXT,        -- JSON list of unit ids the check touches (invalidation)
  last_run, last_status,  -- pass | fail | error
  last_error TEXT
)

concepts(
  id TEXT PK, repo_id, title, body TEXT,
  created_run, status     -- current | stale (any evidence claim went stale)
)

concept_evidence(concept_id → concepts, claim_id → claims, PRIMARY KEY(concept_id, claim_id))

-- FTS5 over claims.text and concepts.title/body for the answer agent.
```

**Citation** = claim id, unit qualified name, file path, line span, `verified_sha`,
the claim's own status, and the verifier's `last_status`. A stale citation announces
itself inline.

## 5. The scanning loop

```
seshat scan <repo> [--units N] [--minutes M] [--tokens T] [--workers W]
                   [--no-thinking] [--full] [--model ...]
```

1. **Index.** `codegraph init` in the target (≈3 s per 1k files). Open
   `.codegraph/codegraph.db` read-only through the graph helper API. Set
   `CODEGRAPH_TELEMETRY=0`.
2. **Run row.** Create `runs` row; name the NOOA trace session by run id.
3. **Seed working memory.** README and docs go in first, as memories, not claims.
   The worker is told to turn doc statements into structural claims where it can;
   such claims get `source='readme'`.
4. **Enumerate units.** From codegraph nodes of kind class/function/method plus
   file-as-module. Compute `ast_hash`, upsert `units`. Existing rows whose hash
   changed → `status='changed'`; rows no longer present → `vanished`; every
   claim on a changed/vanished unit → `stale`. Rerun every verifier whose
   `depends_on` touches a changed unit (`--full` reruns all).
5. **Queue.** Pending + changed units, ordered by `inbound_calls` desc, with a
   boost for units named in a doc seed. Leaves-up composition falls out of this:
   callees are confirmed before callers, and a caller's claims may reference them.
6. **Worker turn** (per unit, CodeAct):
   - Recall relevant working memory.
   - Read the unit via codegraph MCP tools (`node`, `callers`, `callees`,
     `search`, `impact`, plus `explore`; the five named tools surface only via
     `CODEGRAPH_MCP_TOOLS`, see T-08).
   - Conjecture claims. For each, call the verifier author (Predict) to get
     `Verifier(source, expected, depends_on)`.
   - Run the verifier in-process against the helper API. Pass → `confirmed`.
     Fail → one retry with the failure shown; fail again → `refuted`.
   - Persist claims and verifiers via typed tool methods. Write hypotheses and
     notes to working memory.
7. **Budget check** after each unit: units, minutes, tokens, whichever first.
   Update run counters; print a status line.
8. **Reflection.** `ReflectionAgent` reads confirmed claims in batches, emits
   `Concept` objects with evidence claim ids. Also let NOOA memory's own
   post-task reflection run on the working pool.
9. **Candidate rules.** Any structural claim pattern that holds across ≥ 3 units
   with zero exceptions sets `candidate_rule=1` and `rule_sightings`. Nothing
   else; the governance ledger decides.
10. **Close run.** Status, counts, elapsed.

**Rescan** is the same command. Steps 4–5 make it incremental by construction.

## 6. The graph helper API (verifier contract)

Verifiers import only this. Codegraph's internal schema is never referenced, so
the graph backend can change without rewriting rows.

```python
class Graph:
    def node(self, qualified_name: str, file_path: str | None = None) -> Node | None
    def callers(self, qualified_name: str) -> list[Node]
    def callees(self, qualified_name: str) -> list[Node]
    def imports(self, file_path: str) -> list[str]          # resolved file→file edges
    def external_refs(self, qualified_name: str) -> list[str] # unresolved calls: stdlib, third-party
    def subclasses(self, qualified_name: str) -> list[Node]
    def decorators(self, qualified_name: str) -> list[str]
    def search(self, fts_query: str) -> list[Node]
    def files(self, glob: str) -> list[str]
```

Codegraph facts that shape it: node ids are line-sensitive hashes and churn on
any edit above a symbol, so identity is `(file_path, qualified_name)` with
`Class::method` normalized to `Class.method`. Calls to anything outside the repo
live in `unresolved_refs`, not `edges`, hence `external_refs()`. Edge kinds
available: contains, calls, instantiates, references, imports, extends,
decorates, each with a confidence score.

## 7. CLI

```
seshat scan   <repo> [...]        # section 5
seshat status <repo>              # current/last run counters
seshat units  <repo> [--changed]  # list units, status, claim counts
seshat claims <repo> <unit>       # claims + verifier status for one unit
seshat concept <repo> <id|query>  # concept body with citations
seshat drift  <repo>              # stale claims and concepts since last run
seshat ask    <repo>              # chat REPL over the ledger (answer agent)
```

Answer-agent contract: every sentence carries at least one citation; no citation
found → say so, do not improvise.

## 8. Model and runtime

- DGX Spark, vLLM, `hosted_vllm/qwen3.8-27b`, `api_base=f"{LLM_HOST}/v1"`.
- Thinking on by default; `--no-thinking` sets
  `extra_body={'chat_template_kwargs': {'enable_thinking': False}}`.
- Model string per role in config, so any role can move to a frontier model in
  one line. All-local first; if workers flail at CodeAct on a 27B model that is a
  finding, not a bug (the "does the gap widen on weaker models" test).
- CodeAct needs native tool calling. First smoke test on the Spark is a
  two-tool CodeAct method. Fallback: `PurePythonStrategy`.
- NOOA executor is in-process `exec` with no default timeout. Acceptable for
  structural verifiers, which never execute target code.

## 9. Phase-one acceptance

Scan `~/code/labs-OO-Agents` (dogfood). The ledger, via `seshat ask`, must
answer with citations:

1. Which methods in the examples are generation points, and what durable state
   does each one write to?
2. What does an agent class need in order to attach an MCP server, and which
   quickstart shows it?
3. What decides whether a memory gets pruned, and which types are immune?
4. Where does model-generated code actually execute, and what is the default
   timeout?
5. Which classes subclass `Agent` outside the examples directory?

Questions 3 and 4 turn on a single constant in source; a README summary gets
them wrong.

Then edit one function, rescan, and confirm `seshat drift` points at exactly the
rotted rows and nothing else.

## 10. Phases

- **Phase 1 (this plan):** ledger schema, scanning loop, structural verifiers,
  reflection agent, CLI incl. `ask` with FTS. Target: NOOA repo.
- **Phase 1.5:** behavioral verifier agent (import-and-call pure functions,
  subprocess, timeout). Adds `kind='behavioral'` claims. Prose-notes ablation arm.
- **Phase 2:** embed verified claims and concepts (not raw code); vector search
  layered over the same citation graph. Merge tool for many per-repo ledgers.
  Second language via the same graph helper API.
- **Phase 3:** candidate rules → governance-harness controls (a control is
  already a Python script that exits non-zero, same shape as a verifier).

## 11. Risks to watch

- **27B model writing verifiers.** Structured Predict output helps; the retry
  budget and the refuted rows tell you how bad it is.
- **Hallucinated rules flooding candidates.** Rule-of-three gate plus zero
  exceptions; apply the "does the middle bin honestly fatten" test from the
  governance doc before promoting anything.
- **Verifier tautology.** A verifier that restates the claim by querying the same
  fact it was derived from proves nothing. The worker prompt must ask for a check
  from a *different* angle (callers rather than the body, etc.). Watch for this in
  the first run's rows.
- **Codegraph gaps.** Decorators came back empty on Python nodes; external calls
  are unresolved. The helper API hides this, but claims about decorators need a
  fallback (tree-sitter or `ast`) before they can be verified.
- **Doc seeds leaking as facts.** A README statement is a hypothesis with
  `source='readme'` until a verifier passes. The answer agent must not cite
  working memory.

## 12. Next concrete step

Create the GitHub repo, stamp it with `new-project`, add `nooa[memory,mcp]`,
smoke-test a two-tool CodeAct method against the Spark, then build in this
order: ledger schema → graph helper API → one worker turn on one unit → queue
and budget → reflection → CLI → `ask`.
