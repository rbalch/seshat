"""Acceptance tests for T-07: the verifier author agent.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-07-verifier-author-agent.md. Committed alone, before
any implementation exists, per the project's red-then-green contract.

Hermetic tests install `nooa.unifiedllm.FakeLLMClient` via `agent.set_llm(...)`
and never touch the network; see `.venv/.../nooa/unifiedllm/fake.py` for the
fake's `last_messages` / `call_count` bookkeeping and
`.venv/.../nooa/strategies/predict.py` for how a `@strategy(PredictStrategy())`
method's docstring becomes the prompt.

The one `-m integration` test needs a live `LLM_HOST` and is skipped without
one.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from nooa.errors import GenerationError
from nooa.unifiedllm import FakeLLMClient, LLMResponse

from seshat.agents.verifier_author import (
    VerifierAuthor,
    VerifierAuthorError,
    VerifierSpec,
    _has_check_entry_point,
    author_with_retry,
    make_verifier_author,
)
from seshat.config import Settings
from seshat.ledger.models import Unit

VALID_SOURCE = """
def check(graph):
    return sorted(n.qualified_name for n in graph.callers('OrderRepository.get'))
"""

NO_CHECK_SOURCE = """
def not_check(graph):
    return 1
"""

# A bare substring check on 'def check(' is defeated by this: the literal text
# appears (in a comment) but there is no such function. See fix round 1, item 2.
CHECK_LOOKALIKE_SOURCE = """
# TODO: implement def check(graph)
def not_check(graph):
    return 1
"""


def _unit() -> Unit:
    return Unit(
        id='u1',
        repo_id='r1',
        file_path='repository.py',
        qualified_name='OrderRepository.get',
        kind='method',
        start_line=15,
        end_line=20,
        ast_hash='deadbeef',
        inbound_calls=1,
        first_seen_run='run1',
        last_seen_run='run1',
        last_scanned_run='run1',
        status='scanned',
    )


def _response(payload: dict) -> LLMResponse:
    content = json.dumps(payload)
    return LLMResponse(
        raw_response=None,
        content=content,
        tool_calls=[],
        finish_reason='stop',
        assistant_message={'role': 'assistant', 'content': content},
        reasoning=None,
        usage=None,
    )


def _valid_payload(source: str = VALID_SOURCE) -> dict:
    return {
        'source': source,
        'expected_json': json.dumps(['OrderService.place']),
        'depends_on': ['u1'],
        'angle': 'checks callers of the method rather than its own body',
    }


def _malformed_response() -> LLMResponse:
    """Content that fails schema parsing outright, not just business validation.

    `_valid_payload(source=NO_CHECK_SOURCE)` still parses fine as a `VerifierSpec` —
    it just fails our own entry-point guard — so it never engages NOOA's own
    internal validation-retry loop. This one does: it is not valid JSON at all,
    which is what `PredictStrategy`'s `max_retries` governs.
    """
    return LLMResponse(
        raw_response=None,
        content='not json at all',
        tool_calls=[],
        finish_reason='stop',
        assistant_message={'role': 'assistant', 'content': 'not json at all'},
        reasoning=None,
        usage=None,
    )


def _agent(*responses: LLMResponse) -> VerifierAuthor:
    agent = VerifierAuthor(llm=FakeLLMClient())
    agent.set_llm(FakeLLMClient(scripted_responses=list(responses)))
    return agent


def test_author_returns_valid_verifier_spec_with_four_fields_intact() -> None:
    payload = _valid_payload()
    agent = _agent(_response(payload))

    result = asyncio.run(agent.author('claim text', _unit(), 'def get(self): ...', 'neighbours'))

    assert isinstance(result, VerifierSpec)
    assert result.source == payload['source']
    assert result.expected_json == payload['expected_json']
    assert result.depends_on == payload['depends_on']
    assert result.angle == payload['angle']


def test_author_with_retry_recovers_from_one_missing_check_response() -> None:
    bad_payload = _valid_payload(source=NO_CHECK_SOURCE)
    good_payload = _valid_payload()
    agent = _agent(_response(bad_payload), _response(good_payload))

    result = asyncio.run(author_with_retry(agent, 'claim text', _unit(), 'def get(self): ...', 'neighbours'))

    assert isinstance(result, VerifierSpec)
    assert result.source == good_payload['source']
    assert agent.llm.call_count == 2


def test_author_with_retry_raises_after_two_bad_responses() -> None:
    bad_payload = _valid_payload(source=NO_CHECK_SOURCE)
    agent = _agent(_response(bad_payload), _response(bad_payload))

    with pytest.raises(VerifierAuthorError):
        asyncio.run(author_with_retry(agent, 'claim text', _unit(), 'def get(self): ...', 'neighbours'))


def test_prompt_contains_graph_api_and_entry_point() -> None:
    agent = _agent(_response(_valid_payload()))

    asyncio.run(agent.author('claim text', _unit(), 'def get(self): ...', 'neighbours'))

    fake = agent.llm
    prompt_text = json.dumps(fake.last_messages)
    assert 'callers(' in prompt_text
    assert 'def check(graph)' in prompt_text


def test_author_is_one_shot_malformed_response_causes_exactly_one_call() -> None:
    """`author` must not let NOOA's own internal validation-retry loop run.

    `PredictStrategy` defaults to `max_retries=10`: an unparseable response
    would otherwise cost up to 10 calls into the LLM before `author` ever
    raises, contradicting "one shot by design" (decisions Q27) and this
    module's own docstring. `author` must constrain the strategy so exactly
    one call happens before the error propagates.
    """
    agent = _agent(_malformed_response(), _malformed_response(), _malformed_response())

    with pytest.raises(GenerationError):
        asyncio.run(agent.author('claim text', _unit(), 'def get(self): ...', 'neighbours'))

    assert agent.llm.call_count == 1


def test_has_check_entry_point_rejects_comment_only_lookalike() -> None:
    """A bare substring match on `'def check('` is defeated by a comment.

    `_has_check_entry_point` must parse `source` and require an actual
    top-level `def check` — not merely the text `def check(` appearing
    anywhere, including inside a comment beside a differently-named
    function.
    """
    assert _has_check_entry_point(CHECK_LOOKALIKE_SOURCE) is False


def test_has_check_entry_point_fails_closed_on_syntax_error() -> None:
    """Source that does not even parse must fail the guard, not pass it."""
    assert _has_check_entry_point('def check(graph:\n    this is not python') is False


def test_has_check_entry_point_accepts_real_check_function() -> None:
    assert _has_check_entry_point(VALID_SOURCE) is True


def test_has_check_entry_point_rejects_async_check() -> None:
    """`src/seshat/verify.py`'s `_find_check_function` only ever matches
    `ast.FunctionDef`, never `ast.AsyncFunctionDef` — T-05 always rejects an
    async `check`. This guard must agree, or a spec with an async `check`
    sails past validation here, burns no retry, and only fails a stage
    later in T-05, far from its cause.
    """
    source = """
async def check(graph):
    return sorted(n.qualified_name for n in graph.callers('OrderRepository.get'))
"""
    assert _has_check_entry_point(source) is False


def test_has_check_entry_point_accepts_extra_defaulted_parameter() -> None:
    """T-05 calls `check(graph)` positionally with one argument, so a `check`
    with further parameters that all default is fine — T-05's own
    `_find_check_function` only requires a non-empty `args.args`, not
    exactly one. Rejecting this here is over-strict: it forces a needless
    retry (and can burn the one-shot budget) on a spec that would have run
    fine.
    """
    source = """
def check(graph, extra=1):
    return sorted(n.qualified_name for n in graph.callers('OrderRepository.get'))
"""
    assert _has_check_entry_point(source) is True


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv('LLM_HOST'), reason='needs a live LLM_HOST')
def test_live_author_returns_verifier_spec_with_check_entry_point() -> None:
    settings = Settings.load()
    agent = make_verifier_author(settings)

    result = asyncio.run(
        agent.author(
            'OrderRepository.get looks up an order by id',
            _unit(),
            'def get(self, order_id):\n    return self._orders[order_id]',
            'callers: OrderService.place',
        )
    )

    assert isinstance(result, VerifierSpec)
    assert 'def check(graph)' in result.source
