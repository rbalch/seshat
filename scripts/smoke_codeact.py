#!/usr/bin/env python3
"""A hand-run smoke test that proves `hosted_vllm/qwen3.8-27b` on the DGX Spark can
drive a NOOA CodeAct turn with native tool calling, and that `--no-thinking` reaches
the model (plan §8, §12; tasks/seshat-phase-one/T-13-spark-smoke.md).

A two-tool agent (`add(a, b)`, `lookup(name)` over a small dict) is asked, in one
generation method, to call both and report the results. Every run of this script
drives that agent twice: once with the `worker` role's default thinking setting, once
with thinking forced off (`--no-thinking` reaching the wire via
`Settings.llm_kwargs`'s `extra_body={'chat_template_kwargs': {'enable_thinking':
False}}` -- see `src/seshat/config.py`). Reads `Settings` from the environment
(`LLM_HOST` required); `--strategy pure-python` swaps in `PurePythonStrategy` for
comparison against the default `CodeActStrategy`.

Usage::

    LLM_HOST=http://<spark-host>:<port> uv run python scripts/smoke_codeact.py
    LLM_HOST=... uv run python scripts/smoke_codeact.py --strategy pure-python

Exit 0 only if both tools were called in both modes. A failing smoke is a finding
about the model/strategy (plan §8's capability-ladder question), not a bug to be
patched around here -- see README.md "Running against the Spark".
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

from nooa import Agent
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy
from nooa.strategies.pure_python import PurePythonStrategy

from seshat.config import ConfigError, Settings

# The two-tool fact table `lookup` reads. Deliberately tiny and hand-written -- this
# script proves tool-calling works, not that the model knows anything real.
_FACTS = {
    'seshat': 'a ledger of verified claims about a codebase',
    'spark': 'the DGX Spark box this script is meant to run against',
}


@dataclass(frozen=True)
class SmokeResult:
    """One run's outcome: both tool-call flags, the answer, tokens, elapsed seconds."""

    add_called: bool
    lookup_called: bool
    answer: str
    tokens: int
    elapsed: float


class _SmokeTools:
    """`add`/`lookup`: the two tools every generation method below must call.

    Mixed in ahead of `Agent` so `CodeActSmokeAgent`/`PurePythonSmokeAgent` share one
    tool implementation and one token meter, differing only in which `@strategy`
    decorates their `run` method.
    """

    def __init__(self, llm: object) -> None:
        super().__init__(llm=llm)  # type: ignore[call-arg]
        self.add_called = False
        self.lookup_called = False
        self.tokens_used = 0
        self.event_manager.intercept('llm_call', self._track_tokens)  # type: ignore[attr-defined]

    async def _track_tokens(self, ctx: object, nxt: object) -> object:
        ctx = await nxt(ctx)  # type: ignore[operator]
        usage = getattr(ctx, 'response', None)
        usage = getattr(usage, 'usage', None) if usage is not None else None
        if usage:
            self.tokens_used += usage.get('total_tokens', 0)
        return ctx

    def add(self, a: int, b: int) -> int:
        """Add two integers and return the sum."""
        self.add_called = True
        return a + b

    def lookup(self, name: str) -> str:
        """Look up `name` in a small fact table; returns 'unknown' if absent."""
        self.lookup_called = True
        return _FACTS.get(name, 'unknown')


class CodeActSmokeAgent(_SmokeTools, Agent):
    """The two-tool smoke agent, driven by `CodeActStrategy` (the default)."""

    @strategy(CodeActStrategy())
    async def run(self) -> str:
        """Call both add(3, 4) and lookup('seshat'), then return one sentence that
        names both results, e.g. "3 + 4 = 7; seshat is a ledger of verified claims
        about a codebase."
        """
        ...


class PurePythonSmokeAgent(_SmokeTools, Agent):
    """The same smoke agent, driven by `PurePythonStrategy` for comparison."""

    @strategy(PurePythonStrategy())
    async def run(self) -> str:
        """Call both add(3, 4) and lookup('seshat'), then return one sentence that
        names both results, e.g. "3 + 4 = 7; seshat is a ledger of verified claims
        about a codebase."
        """
        ...


_STRATEGY_AGENTS: dict[str, type] = {
    'codeact': CodeActSmokeAgent,
    'pure-python': PurePythonSmokeAgent,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='smoke_codeact.py',
        description=(
            'Two-tool CodeAct smoke test against a live LLM_HOST (plan §8/§12). '
            'Runs the agent once with thinking on and once with thinking off.'
        ),
    )
    parser.add_argument(
        '--strategy',
        choices=sorted(_STRATEGY_AGENTS),
        default='codeact',
        help=(
            "Agent strategy to smoke-test (default: %(default)s). 'pure-python' "
            'swaps in PurePythonStrategy for comparison.'
        ),
    )
    return parser


async def _run_once(agent_cls: type, settings: Settings, *, thinking: bool) -> SmokeResult:
    from nooa.unifiedllm import CompletionClient

    role_settings = settings.with_thinking(thinking)
    llm = CompletionClient(**role_settings.llm_kwargs('worker'))
    agent = agent_cls(llm)

    start = time.monotonic()
    answer = await agent.run()
    elapsed = time.monotonic() - start

    return SmokeResult(
        add_called=agent.add_called,
        lookup_called=agent.lookup_called,
        answer=str(answer),
        tokens=agent.tokens_used,
        elapsed=elapsed,
    )


async def _run_both_modes(agent_cls: type, settings: Settings) -> list[tuple[bool, SmokeResult]]:
    results = []
    for thinking in (True, False):
        result = await _run_once(agent_cls, settings, thinking=thinking)
        results.append((thinking, result))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    agent_cls = _STRATEGY_AGENTS[args.strategy]

    try:
        settings = Settings.load()
    except ConfigError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    model = settings.role('worker').model
    runs = asyncio.run(_run_both_modes(agent_cls, settings))

    ok = True
    for thinking, result in runs:
        mode = 'thinking' if thinking else 'no-thinking'
        print(
            f'[{mode}] model={model} strategy={args.strategy} '
            f'add_called={result.add_called} lookup_called={result.lookup_called} '
            f'answer={result.answer!r} tokens={result.tokens} elapsed={result.elapsed:.2f}s'
        )
        if not (result.add_called and result.lookup_called):
            ok = False

    if not ok:
        print(
            'FAILED: at least one mode did not call both tools. This is a finding '
            'about the model/strategy (switch strategy in config), not a bug in this '
            'script -- see README.md "Running against the Spark".',
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
