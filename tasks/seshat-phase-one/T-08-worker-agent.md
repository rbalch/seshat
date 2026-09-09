---
id: T-08
plan: seshat-phase-one
title: Worker agent
status: todo
depends_on: [T-05, T-07]
files:
  - src/seshat/agents/worker.py
  - src/seshat/memory.py
  - src/seshat/units.py
  - src/seshat/ledger/store.py
  - tests/agents/test_worker.py
rules: []
---

## Goal

One worker turn for one unit (plan §5 step 6): read the unit through the codegraph
MCP tools, conjecture claims, get a verifier for each, run it, retry once on
failure with the refutation shown, and persist the outcome through the ledger's
typed methods. Working memory (`nooa-memory`) holds hypotheses and notes; the
ledger holds only what a verifier passed.

## Scope

1. `src/seshat/memory.py`: `open_working_memory(repo: Path)` returns a
   `nooa-memory` store at `<repo>/.seshat/memory.db` with the hashing embedder,
   plus `seed_docs(memory, repo) -> list[str]` that stores each paragraph of
   `README.md` and `docs/**/*.md` as an `info` memory tagged `source=readme` and
   returns the set of code identifiers (`CamelCase` or `snake_case` tokens with a
   dot or parenthesis nearby) it found, for queue boosting. The dot or
   parenthesis is a *filter* — it marks the preceding token as code rather than
   prose — and is never part of the captured string: `` `OrderRepository.get` ``
   in the text yields `OrderRepository`, not `OrderRepository.get`.
2. `Worker(nooa.Agent)`, `CodeActStrategy`, thinking on per settings. Tools (methods
   with bodies):
   - `unit_brief() -> str`: the unit's source (lines from the graph span), its
     callers, callees, decorators, external refs, via `Graph`;
   - `recall(query) -> list[str]` from working memory;
   - `remember(text, kind)` into working memory;
   - `propose_claim(text: str, source: Literal['code','readme','docstring']) -> str`
     stores a `conjectured` claim and returns its id;
   - `verify_claim(claim_id) -> dict`: calls the verifier author (T-07) with the
     claim and brief, runs T-05 `verify_and_record`; on `pass` → claim
     `confirmed` with `verified_sha`; on `fail`/`error` → one more author call with
     the failure as feedback, rerun; second failure → `refuted`, `retries=1`.
     Returns `{status, reason}`.
   - the codegraph MCP server attached as an `MCPStdioClient` running
     `codegraph serve --mcp --no-watch` in the target with `CODEGRAPH_TELEMETRY=0`
     and `CODEGRAPH_MCP_TOOLS=explore,node,callers,callees,search,impact`.
     Codegraph 1.6.0 lists `codegraph_explore` alone by default, and this env var
     **replaces** that default rather than extending it — omit `explore` from the
     list and the model never sees `codegraph_explore` at all. Verified against
     the installed binary: the six named above all surface, and `files`,
     `status`, `all` do not. Tell the model in the prompt to call
     `codegraph_explore` first, then the narrower tools.
   The generation method `survey(self, unit: Unit) -> UnitReport: ...` with a
   docstring prompt: read the unit, recall memory, propose 2–5 structural claims,
   call `verify_claim` on each, remember dead ends, return
   `UnitReport(claims_confirmed, claims_refuted, notes)`.
3. `run_unit(worker, unit, ledger, graph, run_id) -> UnitReport` wraps `survey`,
   then sets the unit `scanned` with `last_scanned_run`, and returns the report
   plus tokens used from NOOA's token accounting.
4. Claim `mode='claims'`, `kind='structural'` always in phase one.
5. `Ledger.set_claim_status` gains `retries: int | None = None` and writes that
   column when it is not `None`, leaving it untouched when it is. Today the
   method writes status, verified run and `verified_sha` only, and `add_claim`
   is insert-only and rejects any status but `conjectured`, so there is no typed
   path to record a retry at all. Same shape as the `F-20` defect in
   `docs/ledger-findings.md`: a status write that cannot write a field the
   status carries. Existing callers keep their behaviour.
6. `UnitReport(claims_confirmed, claims_refuted, notes, tokens)` is defined in
   `src/seshat/units.py`, not in `agents/worker.py`. It is a plain frozen
   dataclass and `units.py` imports no model, so T-09's deterministic
   orchestrator can import it without reaching into an agent module.

## Non-scope

- No queue, budget or run bookkeeping (T-09). No reflection. No candidate rules.
- No reviewer agent (decisions Q31). No behavioral verifiers.
- Do not write claims to working memory or hypotheses to the ledger.

## Acceptance

- `uv run pytest tests/agents/test_worker.py -q` → exit 0, hermetic, against a tmp
  copy of `fixture_target`, with the verifier author replaced by a stub object
  exposing the same `author_with_retry` signature, and `FakeLLMClient` on the
  worker, covers:
  - `seed_docs` stores at least two memories and returns a set containing
    `OrderRepository`;
  - `propose_claim` writes a `conjectured` row with `source='readme'` when told so;
  - `verify_claim` with a stub returning a passing verifier → claim `confirmed`,
    `verified_sha` set, `retries == 0`;
  - stub returning a failing verifier then a passing one → `confirmed`,
    `retries == 1`, and the stub's second call received feedback text containing
    the first failure;
  - stub returning two failing verifiers → `refuted`, row kept, verifier row's
    `last_status == 'fail'`;
  - a stub verifier with `tautology` error is treated like a failure (retry once);
  - `run_unit` with a `FakeLLMClient` scripted to end the CodeAct turn immediately
    sets the unit `scanned` and returns a `UnitReport`;
  - that same `UnitReport` carries a token count read from NOOA's token
    accounting, not a constant: the test asserts it is greater than zero and
    that it tracks the fake's accounted usage, so a hardcoded `0` or a literal
    fails.
- `uv run pytest -m integration tests/agents/test_worker.py -q` → skipped without
  `LLM_HOST`; with it, one real `survey` on `OrderRepository.get` produces at
  least one claim row in any status.
- `make check` → exit 0

## Context

- plan §2 (worker row, retry rule), §3 (two pools), §5 step 6, §11 "Doc seeds
  leaking". Decisions Q8, Q14, Q21, Q30, Q31. `AGENTS.md` Never: a claim enters the
  ledger only after its verifier passes; a README statement is a hypothesis until
  then.
- NOOA CodeAct needs native tool calling; if the fake cannot drive a full CodeAct
  turn, the acceptance for `run_unit` may use a scripted response that returns a
  final result with no tool calls. Do not weaken the `verify_claim` tests.
- MCP client: `nooa/mcp/client.py` `MCPStdioClient` (command, args, env). Read
  `labs-OO-Agents/examples/quickstart` on GitHub for the attach pattern if unsure.
- `nooa-memory` is installed (`nooa_memory`); read its README in site-packages for
  the store constructor and the `info` type. Decay stays on; nothing here is meant
  to be durable.

## Manual QA

After T-13, look at one worker's rows in `.seshat/ledger.db` and check the
verifier angle differs from the claim's source.
