---
id: T-02
plan: seshat-phase-one
title: Package skeleton, console script, role config
status: done
depends_on: []
files:
  - pyproject.toml
  - src/seshat/__init__.py
  - src/seshat/config.py
  - src/seshat/cli.py
  - .env.example
  - tests/test_config.py
  - tests/test_cli_entry.py
rules: []
---

## Goal

`uv run seshat --help` works, and there is one place that says which model string,
API base and thinking setting each of the four model roles uses. Every agent task
reads its model from here and nowhere else.

## Scope

1. Add `[project.scripts] seshat = "seshat.cli:main"` to `pyproject.toml`. `main`
   prints usage and exits 0 with no subcommands yet (T-11 fills them in). Use
   `argparse`; no new dependency.
2. `src/seshat/config.py`:
   - `Role = Literal['worker', 'verifier_author', 'reflection', 'answer']`.
   - `RoleConfig(model: str, api_base: str, thinking: bool)` frozen dataclass.
   - `Settings.load(env: Mapping[str, str] | None = None) -> Settings` reads
     `LLM_HOST` (required; raise `ConfigError` naming the variable if missing),
     `SESHAT_MODEL` (default `hosted_vllm/qwen3.8-27b`), and per-role overrides
     `SESHAT_MODEL_WORKER`, `SESHAT_MODEL_VERIFIER_AUTHOR`, `SESHAT_MODEL_REFLECTION`,
     `SESHAT_MODEL_ANSWER`. `api_base` is `f'{LLM_HOST}/v1'`.
   - `Settings.role(name: Role) -> RoleConfig`.
   - `Settings.llm_kwargs(role) -> dict` returns the kwargs to hand NOOA's LLM
     constructor: `model`, `api_base`, and when `thinking` is False,
     `extra_body={'chat_template_kwargs': {'enable_thinking': False}}`.
   - `Settings.with_thinking(False)` returns a copy with thinking off for all roles.
3. Add `LLM_HOST=` and the `SESHAT_MODEL*` names to `.env.example` with one-line
   comments. Set `CODEGRAPH_TELEMETRY=0` there too.
4. Add a `pytest` marker `integration` in `pyproject.toml` (`--strict-markers` is
   on) with the description "needs LLM_HOST and a live model".

## Non-scope

- No subcommands, no ledger, no agents. No NOOA import in this task.
- Do not read `.env` files at runtime; the caller sets the environment.

## Acceptance

- `uv run seshat --help` → exit 0, output contains `seshat`.
- `uv run pytest tests/test_config.py tests/test_cli_entry.py -q` → exit 0, covers:
  - missing `LLM_HOST` raises `ConfigError` whose message contains `LLM_HOST`;
  - default model for every role is `hosted_vllm/qwen3.8-27b` and `api_base` is
    `<LLM_HOST>/v1`;
  - `SESHAT_MODEL_ANSWER=x` changes only the answer role;
  - `llm_kwargs` omits `extra_body` when thinking is on and includes the exact
    `chat_template_kwargs` dict when off.
- `make check` → exit 0

## Context

- plan §8 (model and runtime), decisions Q13, Q20.
- NOOA reaches the model through LiteLLM; `api_base` and `extra_body` pass through
  unchanged (decisions, "Facts gathered"). Do not wrap or rename them.

## Manual QA

None.
