---
id: T-05
plan: seshat-phase-one
title: Verifier runner with tautology gate
status: in_review
depends_on: [T-03, T-04]
files:
  - src/seshat/verify.py
  - tests/test_verify.py
rules: []
---

## Goal

Given a verifier's Python source and expected JSON, run it in-process against a
`Graph` and say pass, fail or error. Reject, before running, any verifier that only
re-queries the unit its claim was derived from. This is what promotes a conjecture
to a confirmed claim, so it is the reviewer of the whole system.

## Scope

1. `VerifierResult(status: Literal['pass','fail','error'], actual: Any | None,
   error: str | None)`.
2. `run_verifier(source: str, expected_json: str, graph: Graph, *,
   unit_qualified_name: str) -> VerifierResult`:
   - the source must define `def check(graph) -> Any`; anything else → `error`;
   - the namespace the source runs in exposes only builtins, `json`, `re`, and the
     `Graph`/`Node` types; an `import` of any other module → `error` before
     execution (walk the `ast`, do not rely on catching `ImportError`);
   - result is compared to `json.loads(expected_json)` after a canonical pass
     (`Node` → dict of its five fields, lists sorted where they were sets);
   - equal → `pass`; unequal → `fail` with `actual` filled; exception → `error`
     with the exception text.
3. Tautology gate, `is_tautological(source, unit_qualified_name) -> str | None`:
   returns a reason string when the source's only graph calls are `graph.node(...)`
   on `unit_qualified_name` (either name form), or when it makes no graph call at
   all. Runs before execution; a tautological verifier returns
   `VerifierResult('error', None, 'tautology: …')`.
4. `verify_and_record(ledger: Ledger, verifier: Verifier, graph: Graph, run_id)
   -> VerifierResult` runs it and calls `ledger.record_verifier_run`. It does not
   change the claim's status; the worker (T-08) decides confirmed/refuted.

## Non-scope

- No model. No retry logic. No claim status changes. No subprocess or timeout:
  structural verifiers never run target code (plan §8, `AGENTS.md` Never).
- Do not sandbox beyond the import gate; that is the phase-1.5 behavioral agent's job.

## Acceptance

- `uv run pytest tests/test_verify.py -q` → exit 0, against `fixture_target`, covers:
  - a verifier calling `graph.subclasses('OrderRepository')` with matching expected → `pass`;
  - same verifier with wrong expected → `fail` and `actual` shows the real list;
  - source without `check` → `error`;
  - source with `import os` → `error` and `os` never executes (assert message
    mentions `import`);
  - source raising → `error` with the exception text;
  - a verifier whose only call is `graph.node('OrderRepository.get')` for unit
    `OrderRepository.get` → `error` with `tautology` in the message;
  - the same source for a different unit name → not tautological;
  - `verify_and_record` writes `last_status` and `last_run` on the verifier row.
- `make check` → exit 0

## Context

- plan §2 (verifier is the reviewer), §6, §11 "Verifier tautology". Decisions Q17,
  Q28, Q31. `AGENTS.md` "Always": a check from a different angle than the claim.
- NOOA's executor is in-process `exec` with no timeout; this module is Seshat's own
  `exec`, not NOOA's, so it can be tested without an agent.

## Manual QA

None.
