# Seshat — decision log (grilling session, 2026-09-04)

Every question asked during planning, with the settled answer. Intended as seed
material for the project's governance ledger once the repo exists. Numbering
matches the session. Facts that shaped an answer are noted inline.

## Round 1

| # | Question | Decision |
|---|---|---|
| Q1 | First target repo | Dogfood: `labs-OO-Agents` (cloned to `~/code/labs-OO-Agents`). NeMo proper only after the loop works. |
| Q2 | Unit of knowledge | Function/class is the leaf; module rollups after leaves. Concepts are a separate pool (see Q16). |
| Q3 | Claims vs summaries | Claims. One falsifiable sentence + verifier + status. Summary is derived. |
| Q4 | Verifier tiers | Rephrased as Q17. |
| Q5 | ADR / lint-rule emission | Deferred. `candidate_rule` flag + sightings counter only. |
| Q6 | Drift mechanics | AST-level content hash per unit; rescan only changed units; rerun dependent verifiers. `--full` reruns everything. |
| Q7 | Fleet shape | `repo_id` on every row, one SQLite per repo, identical schema. Merge is a later tool. |
| Q8 | How much NOOA | Use it faithfully (agent classes, `...` methods, MCP client, memory). Own the ledger schema. |
| Q9 | Scan termination | Budget dial with progress reporting. See Q34. |
| Q10 | Languages | Python only. Verifiers target the graph helper API, so other languages come later without rewriting rows. |
| Q11 | Ablation | Rephrased as Q19. |
| Q12 | Acceptance test | Five English questions written before the run; DB must answer with citations, no vectors. See Q37. |
| Q13 | Model | DGX Spark, vLLM, `hosted_vllm/qwen3.8-27b`. See Q20. |
| Q14 | Codegraph access | Scanner uses MCP (all eight tools via `CODEGRAPH_MCP_TOOLS`). Verifiers read `.codegraph/codegraph.db` directly through the helper API. |
| Q15 | NOOA memory as ledger | Rephrased as Q21. |

## Round 2

| # | Question | Decision |
|---|---|---|
| Q16 | Two pools | Pool 1: unit claims with verifiers. Pool 2: concepts with evidence links to claims. Concepts written by a reflection pass from confirmed claims only. Citation walks concept → claim → unit → file/lines/sha. |
| Q17 | Run target code in phase one? | No. Structural verifiers only. `kind` column reserves `behavioral`; a later agent adds it. |
| Q18 | Sequential vs parallel workers | Queue + worker-count flag, default 1. |
| Q19 | Predictor-vs-prose ablation | Tag rows with `mode`; build the prose arm later. |
| Q20 | Local model plumbing | vLLM on the Spark via `LLM_HOST`; thinking on by default, `--no-thinking` flag. Model string per role in config; all-local first. Fact: CodeAct needs native tool calling; `PurePythonStrategy` is the fallback. |
| Q21 | Decay vs rule of three | Decay in `nooa-memory` is recency × recall count (Ebbinghaus), not evidence-based. Working memory decays; ledger never does. Promotion to ledger requires a passing verifier. |
| Q22 | What a citation contains | Claim id, unit qualified name, file path, line span, verified sha, verifier last status. |
| Q23 | Where the project lives | Fresh repo on GitHub, stamped with `new-project`. The existing scaffold was a playground. |
| Q24 | Phase-one review surface | Read-only CLI subcommands plus a chat CLI. |

## Round 3

| # | Question | Decision |
|---|---|---|
| Q25 | Who writes concepts | Own small `ReflectionAgent` writes concepts into the ledger. NOOA's built-in memory reflection stays on for the working pool only. |
| Q26 | Chat CLI in phase one | Yes. Answer agent over FTS; every sentence cited; refuses when nothing is found. |
| Q27 | Strategy per role | Worker and answer: CodeAct. Verifier author and reflection: Predict with typed returns. Orchestration: plain Python. |
| Q28 | Verifier form | Python source stored in the row, run against the owned graph helper API, with expected result. |
| Q29 | Unit identity | `(file_path, qualified_name)`; change = AST hash. Fact: codegraph node ids hash the line number and churn on edits. |
| Q30 | Docs and READMEs | Seeds into working memory before any unit; worker turns doc statements into structural claims with `source='readme'`. |
| Q31 | Reviewer agent | None. Verifier is the reviewer; one retry, then refuted. Refuted rows are kept. |
| Q32 | Queue priority | Inbound call count desc, boost for units named in doc seeds. |
| Q33 | Run identity | `runs` row per scan; NOOA trace session named by run id; status line + `status` subcommand. |
| Q34 | Budget units | Units, minutes, and tokens; whichever hits first. Defaults small enough that a first run ends while watching. |

## Round 4

| # | Question | Decision |
|---|---|---|
| Q35 | Ledger location | Inside the target repo at `.seshat/ledger.db`, gitignored, beside `.codegraph/`. |
| Q36 | Name | `seshat` (Egyptian goddess of measurement, record keeping, and the "stretching of the cord" survey rite). |
| Q37 | Acceptance questions | Approved as drafted; see `plan.md` §9. |
| Q38 | Session deliverable | `plan.md` and this file. Research doc unchanged. |

## Facts gathered (for the record)

- `~/code/nvidia-object-oriented-agents` is a `new-project` scaffold with four quickstart scripts, not a NOOA clone. Scripts use `QWEN_HOST`; project will use `LLM_HOST`.
- `~/code/new-project` is the skill directory. The codegraph MCP is `@colbymchenry/codegraph` (npm, bundled Node runtime, telemetry on by default: set `CODEGRAPH_TELEMETRY=0`).
- Codegraph schema: `nodes`, `edges`, `files`, `unresolved_refs`, `nodes_fts` (FTS5). Edge kinds: contains, calls, instantiates, references, imports, extends, decorates. External/stdlib calls sit in `unresolved_refs`. Python decorators came back empty. Index of the NOOA repo: ~1k files, 28k nodes, 79k edges, ~3 s.
- `nooa-memory`: SQLite, hashing embedder (no neural embeddings), types `info|skill|episode|intent|todo|reflection|scratch`, decay from `last_accessed_at` and recall count, immune if type protected or importance ≥ 8. Reflection = merge dups → LLM reconcile → kNN edges → rescore → LLM abstraction (episodes → new memories) → prune. Prompts are caller-supplied callables.
- NOOA multi-agent is plain Python; parallel via `asyncio.gather`. Executor is in-process `exec`, no default timeout; sandbox backend exists, off by default.
- NOOA LLM access is LiteLLM; `api_base`, `extra_body` pass straight through.
