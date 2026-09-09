---
id: T-07
plan: seshat-phase-one
title: Verifier author agent
status: done
depends_on: [T-03]
files:
  - src/seshat/agents/__init__.py
  - src/seshat/agents/verifier_author.py
  - tests/agents/test_verifier_author.py
rules: []
---

## Goal

A NOOA `Predict` agent that turns one claim about one unit into a typed
`VerifierSpec(source, expected_json, depends_on)`: Python against the graph helper
API plus the result it expects. This is the second of the four generation points.

## Scope

1. `VerifierSpec` pydantic model: `source: str`, `expected_json: str`,
   `depends_on: list[str]` (unit ids the check touches), `angle: str` (one line:
   what the check looks at that the claim did not).
2. `VerifierAuthor(nooa.Agent)` with `PredictStrategy` and a single generation
   method `author(self, claim_text: str, unit: Unit, unit_source: str,
   neighbours: str) -> VerifierSpec: ...` whose docstring is the prompt. The
   docstring must state: the `Graph` API (copy the nine signatures from plan §6
   verbatim), that `check(graph)` is the required entry point, that only `json`
   and `re` may be imported, and that the check must come from a different angle
   than the claim's source (callers rather than the body, subclasses rather than
   the class, …). Include one worked example.
3. `make_verifier_author(settings: Settings) -> VerifierAuthor` builds it with
   `settings.llm_kwargs('verifier_author')`.
4. `author_with_retry(agent, claim_text, unit, unit_source, neighbours,
   *, feedback: str | None = None) -> VerifierSpec`: one call, and if the result
   fails pydantic validation or `source` has no `def check(`, one retry with the
   error appended; a second failure raises `VerifierAuthorError`.

## Non-scope

- Do not run the verifier here (T-05 does). Do not persist (T-08 does).
- No CodeAct, no tools, no MCP. This role is one shot by design (decisions Q27).

## Acceptance

- `uv run pytest tests/agents/test_verifier_author.py -q` → exit 0, all hermetic
  with `nooa.unifiedllm.FakeLLMClient` installed via `agent.set_llm(...)`, covers:
  - a scripted response carrying a valid `VerifierSpec` payload → `author` returns
    it with the four fields intact;
  - a first response missing `def check(` then a valid one → `author_with_retry`
    returns the second and `fake.call_count == 2`;
  - two bad responses → `VerifierAuthorError`;
  - the prompt sent to the fake (`fake.last_messages`) contains `callers(` and
    `def check(graph)` (the API and the entry point are in the prompt).
- `uv run pytest -m integration tests/agents/test_verifier_author.py -q` → skipped
  when `LLM_HOST` is unset; with it set, one real call returns a `VerifierSpec`
  whose `source` contains `def check(graph)`.
- `make check` → exit 0

## Context

- plan §2 row "Verifier author", §6, §11 "27B model writing verifiers". Decisions
  Q27, Q28.
- NOOA: agent = one class, a method whose body is `...` is a generation point, the
  docstring is the prompt, typed return via pydantic. Read
  `.venv/lib/python3.13/site-packages/nooa/strategies/predict.py` and
  `nooa/unifiedllm/fake.py` before writing tests; the fake takes a list of
  `LLMResponse` and records `last_messages`.
- `ruff` ignores `PIE790` on purpose: do not "fix" the `...` body.
- `Unit` comes from `src/seshat/ledger/models.py` (T-03).

## Manual QA

None until T-13.
