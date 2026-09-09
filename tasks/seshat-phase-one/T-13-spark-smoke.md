---
id: T-13
plan: seshat-phase-one
title: Spark smoke script and integration tests
depends_on: [T-08]
files:
  - scripts/smoke_codeact.py
  - tests/integration/test_spark.py
  - README.md
rules: []
---

## Goal

A way to prove, by hand, that `hosted_vllm/qwen3.8-27b` on the Spark can drive a
NOOA CodeAct turn with native tool calling and that `--no-thinking` reaches the
model. The result decides whether the worker and answer agents stay on CodeAct or
move to `PurePythonStrategy` (plan §8, spec open questions).

## Scope

1. `scripts/smoke_codeact.py`: a two-tool CodeAct agent (`add(a, b)` and
   `lookup(name)` over a dict) with one generation method that must call both.
   Reads `Settings` from the environment, runs once with thinking on and once with
   `--no-thinking`, prints: model, whether each tool was called, the answer, tokens
   used, elapsed seconds. Exit 0 only if both tools were called in both modes.
   `--strategy pure-python` swaps in `PurePythonStrategy` for comparison.
2. `tests/integration/test_spark.py`, all marked `integration`:
   - the smoke agent calls both tools;
   - `VerifierAuthor.author` on a fixture claim returns a `VerifierSpec` whose
     source passes T-05's import and tautology gates;
   - `Worker.survey` on `OrderRepository.get` in a tmp fixture copy produces at
     least one claim row and at least one verifier row with `last_status` set;
   - `no-thinking`: the request body sent to the model carries
     `chat_template_kwargs.enable_thinking == false` (capture via a LiteLLM
     callback or by pointing `api_base` at a local recording HTTP stub).
3. README section "Running against the Spark": `LLM_HOST`, the smoke command, how
   to run the integration tests, and what a failing smoke means (switch strategy in
   config, not a bug).

## Non-scope

- Do not make CI run the integration tests. Do not add retries or fallbacks that
  hide a flailing model; the flailing is the finding.
- Do not touch the agents' strategies here; report, and the human changes config.

## Acceptance

- `uv run pytest tests/integration -q` → all skipped with `LLM_HOST` unset, exit 0.
- `uv run pytest tests/integration -q -m integration` with `LLM_HOST` set → exit 0
  on the Spark, or a failure whose message names which of the four checks failed.
- `uv run python scripts/smoke_codeact.py --help` → exit 0 (argument parsing is
  testable without a model; add that one hermetic test).
- `make check` → exit 0

## Context

- plan §8 and §12 (this was meant to be the first thing built; it moved late so
  every piece it exercises exists). Decisions Q13, Q20. Spec open questions 1–2.
- NOOA strategies: `nooa/strategies/codeact.py`, `pure_python.py`. LiteLLM passes
  `extra_body` through untouched.

## Manual QA

Ryan runs the smoke script on the Spark and records the outcome in the spec's
open questions. That outcome, not this task, decides the strategy.
