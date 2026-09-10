"""Acceptance tests for T-08: the Worker agent.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-08-worker-agent.md. Committed alone, before any
implementation exists, per the project's red-then-green contract.

Hermetic: every test opens a tmp copy of `fixture_target`'s committed
`.codegraph/codegraph.db` read-only through `seshat.graph.Graph`, a fresh
`.seshat/ledger.db` under `tmp_path`, and installs `FakeLLMClient` (never
touching the network). The verifier author is replaced by a stub object
exposing `author_with_retry`'s exact signature
(`agent, claim_text, unit, unit_source, neighbours, *, feedback=None`), never
the real `seshat.agents.verifier_author.author_with_retry`.

The one `-m integration` test needs a live `LLM_HOST` and is skipped without one.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from nooa.unifiedllm import FakeLLMClient, LLMResponse

from seshat.agents.verifier_author import VerifierAuthor
from seshat.agents.worker import Worker, _read_span, run_unit
from seshat.graph import Graph, Node
from seshat.ledger.models import Unit, UnitKind
from seshat.ledger.store import Ledger
from seshat.memory import open_working_memory, seed_docs
from seshat.units import UnitReport, unit_id

RUN_ID = 'run1'


# -- shared fixtures ---------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, fixture_target: Path) -> Path:
    """A tmp copy of the fixture target, so nothing writes into the committed tree."""
    dest = tmp_path / 'target'
    shutil.copytree(fixture_target, dest)
    return dest


@pytest.fixture
def graph(repo: Path) -> Iterator[Graph]:
    with Graph.open(repo) as g:
        yield g


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[Ledger]:
    with Ledger.open(tmp_path / 'ledger_repo') as l:
        l.create_run(id=RUN_ID, mode='claims')
        yield l


def _order_repository_get_unit(graph: Graph, repo: Path) -> Unit:
    from seshat.units import ast_hash as compute_ast_hash

    node = graph.node('OrderRepository.get')
    assert node is not None
    return Unit(
        id=unit_id(node.file_path, node.qualified_name),
        repo_id='',
        file_path=node.file_path,
        qualified_name=node.qualified_name,
        kind=cast(UnitKind, node.kind),
        start_line=node.start_line,
        end_line=node.end_line,
        ast_hash=compute_ast_hash(repo, node),
        inbound_calls=1,
        first_seen_run=RUN_ID,
        last_seen_run=RUN_ID,
        last_scanned_run=RUN_ID,
        status='pending',
    )


@pytest.fixture
def unit(graph: Graph, repo: Path, ledger: Ledger) -> Unit:
    u = _order_repository_get_unit(graph, repo)
    ledger.upsert_unit(u, RUN_ID)
    return u


class StubVerifierAuthor:
    """A stand-in for `verifier_author.author_with_retry` with the exact same signature.

    Scripted with a list of `VerifierSpec`s (one per call); records every
    `feedback` argument it was given so tests can assert what the retry saw.
    """

    def __init__(self, specs: list) -> None:
        self._specs = list(specs)
        self.feedbacks: list[str | None] = []

    async def __call__(self, agent, claim_text, unit, unit_source, neighbours, *, feedback=None):
        self.feedbacks.append(feedback)
        return self._specs.pop(0)


@dataclass
class _Spec:
    source: str
    expected_json: str
    depends_on: list[str] = field(default_factory=list)
    angle: str = 'a different angle'


_PASSING_SOURCE = """
def check(graph):
    return sorted(n.qualified_name for n in graph.callers('OrderRepository.get'))
"""
_PASSING_EXPECTED = json.dumps(['SpecialOrder.apply_discount'])

_FAILING_EXPECTED = json.dumps(['NoSuchCaller'])

_TAUTOLOGY_SOURCE = """
def check(graph):
    return graph.node('OrderRepository.get')
"""


def _passing_spec() -> _Spec:
    return _Spec(source=_PASSING_SOURCE, expected_json=_PASSING_EXPECTED)


def _failing_spec() -> _Spec:
    return _Spec(source=_PASSING_SOURCE, expected_json=_FAILING_EXPECTED)


def _tautology_spec() -> _Spec:
    return _Spec(source=_TAUTOLOGY_SOURCE, expected_json=json.dumps({}))


def _make_worker(
    ledger: Ledger, graph: Graph, repo: Path, specs: list, *, llm=None
) -> tuple[Worker, StubVerifierAuthor]:
    memory = open_working_memory(repo)
    stub = StubVerifierAuthor(specs)
    worker = Worker(
        llm or FakeLLMClient(),
        memory,
        ledger,
        graph,
        RUN_ID,
        # never touched directly (the stub stands in for author_with_retry); cast
        # past VerifierAuthor's real constructor requirements for the test double.
        verifier_agent=cast(VerifierAuthor, object()),
        author_with_retry_fn=stub,
    )
    return worker, stub


# -- seed_docs (memory.py, exercised through the worker's own doc-seeding path) --


def test_seed_docs_stores_at_least_two_memories_and_finds_order_repository(repo: Path) -> None:
    memory = open_working_memory(repo)

    identifiers = seed_docs(memory, repo)

    assert memory.store.count() >= 2
    assert 'OrderRepository' in identifiers


# -- propose_claim -------------------------------------------------------------


def test_propose_claim_writes_conjectured_row_with_given_source(
    ledger: Ledger, graph: Graph, repo: Path, unit: Unit
) -> None:
    worker, _ = _make_worker(ledger, graph, repo, specs=[])
    worker.begin_unit(unit)

    claim_id = worker.propose_claim('OrderRepository.get raises OrderNotFound when absent.', 'readme')

    rows = ledger.claims_for_unit(unit.id)
    assert len(rows) == 1
    assert rows[0].id == claim_id
    assert rows[0].status == 'conjectured'
    assert rows[0].source == 'readme'


# -- _read_span -----------------------------------------------------------------


def test_read_span_fails_closed_on_a_non_utf8_source_file(graph: Graph, repo: Path, unit: Unit) -> None:
    """Regression: `_read_span` must catch `UnicodeDecodeError`, not just `OSError`.

    A source file that exists but isn't valid UTF-8 must not crash the
    worker's whole turn over one unreadable span — same failure direction
    as a missing file (`''`), not an uncaught exception.

    Exercises `_read_span` directly rather than through `unit_brief()`:
    `unit_brief()` also calls `Graph.decorators()`, which has its own,
    separate unguarded `read_text()` on the same file (`graph.py`'s ast
    fallback path) — a real gap, but in a module T-08 does not own and
    this fix round did not touch; reported to the orchestrator rather than
    patched here, so this test isolates the one function this finding is
    actually about.
    """
    node = graph.node(unit.qualified_name)
    assert node is not None
    (repo / unit.file_path).write_bytes(b'\xff\xfe not valid utf-8 \x00\x01')

    assert _read_span(repo, node) == ''


def test_read_span_returns_real_source_for_a_declared_latin1_file(repo: Path) -> None:
    """T-14: a coding-declared latin-1 file must put real source in the prompt,

    not the empty string T-08 put there (see `_read_span`'s docstring).
    """
    source = '# -*- coding: latin-1 -*-\ndef coût():\n    return 1\n'.encode('latin-1')
    (repo / 'declared_latin1.py').write_bytes(source)
    node = Node(qualified_name='coût', file_path='declared_latin1.py', kind='function', start_line=2, end_line=3)

    span = _read_span(repo, node)

    assert span != ''
    assert 'coût' in span
    assert '�' not in span
    assert 'return 1' in span


# -- verify_claim ---------------------------------------------------------------


def test_verify_claim_pass_confirms_with_verified_sha_and_zero_retries(
    ledger: Ledger, graph: Graph, repo: Path, unit: Unit
) -> None:
    worker, stub = _make_worker(ledger, graph, repo, specs=[_passing_spec()])
    worker.begin_unit(unit)
    claim_id = worker.propose_claim('OrderRepository.get is only called by SpecialOrder.apply_discount.', 'code')

    result = asyncio.run(worker.verify_claim(claim_id))

    assert result['status'] == 'confirmed'
    row = ledger.claims_for_unit(unit.id)[0]
    assert row.status == 'confirmed'
    assert row.verified_sha == unit.ast_hash
    assert row.retries == 0
    assert len(stub.feedbacks) == 1


def test_verify_claim_fail_then_pass_confirms_with_one_retry_and_feedback(
    ledger: Ledger, graph: Graph, repo: Path, unit: Unit
) -> None:
    worker, stub = _make_worker(ledger, graph, repo, specs=[_failing_spec(), _passing_spec()])
    worker.begin_unit(unit)
    claim_id = worker.propose_claim('OrderRepository.get is only called by NoSuchCaller.', 'code')

    result = asyncio.run(worker.verify_claim(claim_id))

    assert result['status'] == 'confirmed'
    row = ledger.claims_for_unit(unit.id)[0]
    assert row.status == 'confirmed'
    assert row.retries == 1
    assert len(stub.feedbacks) == 2
    assert stub.feedbacks[0] is None
    second_feedback = stub.feedbacks[1]
    assert second_feedback is not None
    assert 'NoSuchCaller' in second_feedback


def test_verify_claim_fails_twice_refutes_and_keeps_the_row(
    ledger: Ledger, graph: Graph, repo: Path, unit: Unit
) -> None:
    worker, _stub = _make_worker(ledger, graph, repo, specs=[_failing_spec(), _failing_spec()])
    worker.begin_unit(unit)
    claim_id = worker.propose_claim('OrderRepository.get is only called by NoSuchCaller.', 'code')

    result = asyncio.run(worker.verify_claim(claim_id))

    assert result['status'] == 'refuted'
    row = ledger.claims_for_unit(unit.id)[0]
    assert row.id == claim_id  # the row is kept, not deleted
    assert row.status == 'refuted'
    assert row.retries == 1

    verifiers = [v for v in ledger.all_verifiers() if v.claim_id == claim_id]
    assert verifiers
    assert verifiers[-1].last_status == 'fail'


def test_verify_claim_tautology_error_is_treated_as_a_failure_and_retried(
    ledger: Ledger, graph: Graph, repo: Path, unit: Unit
) -> None:
    worker, stub = _make_worker(ledger, graph, repo, specs=[_tautology_spec(), _passing_spec()])
    worker.begin_unit(unit)
    claim_id = worker.propose_claim('OrderRepository.get is only called by SpecialOrder.apply_discount.', 'code')

    result = asyncio.run(worker.verify_claim(claim_id))

    assert result['status'] == 'confirmed'
    row = ledger.claims_for_unit(unit.id)[0]
    assert row.retries == 1
    assert len(stub.feedbacks) == 2
    second_feedback = stub.feedbacks[1]
    assert second_feedback is not None
    assert 'tautology' in second_feedback


# -- run_unit -------------------------------------------------------------------


def _final_response(payload: dict, usage: dict) -> LLMResponse:
    content = json.dumps(payload)
    return LLMResponse(
        raw_response=None,
        content=content,
        tool_calls=[],
        finish_reason='stop',
        assistant_message={'role': 'assistant', 'content': content},
        reasoning=None,
        usage=usage,
    )


def test_run_unit_sets_scanned_and_returns_a_unit_report(ledger: Ledger, graph: Graph, repo: Path, unit: Unit) -> None:
    usage = {'prompt_tokens': 40, 'completion_tokens': 8, 'total_tokens': 48}
    payload = {'claims_confirmed': [], 'claims_refuted': [], 'notes': ['nothing conjectured']}
    llm = FakeLLMClient(scripted_responses=[_final_response(payload, usage)])
    worker, _ = _make_worker(ledger, graph, repo, specs=[], llm=llm)

    report = asyncio.run(run_unit(worker, unit, ledger, graph, RUN_ID))

    assert isinstance(report, UnitReport)
    scanned = ledger.unit(unit.id)
    assert scanned is not None
    assert scanned.status == 'scanned'


def test_run_unit_reports_tokens_from_nooas_own_accounting_not_a_constant(
    ledger: Ledger, graph: Graph, repo: Path, unit: Unit
) -> None:
    usage = {'prompt_tokens': 40, 'completion_tokens': 8, 'total_tokens': 48}
    payload = {'claims_confirmed': [], 'claims_refuted': [], 'notes': []}
    llm = FakeLLMClient(scripted_responses=[_final_response(payload, usage)])
    worker, _ = _make_worker(ledger, graph, repo, specs=[], llm=llm)

    report = asyncio.run(run_unit(worker, unit, ledger, graph, RUN_ID))

    assert report.tokens > 0
    assert report.tokens == usage['total_tokens']


def test_token_accounting_never_replaces_the_installed_llm_client(ledger: Ledger, graph: Graph, repo: Path) -> None:
    """Regression for the code-review finding on `_CountingLLM`.

    Token accounting must observe the LLM call, never stand in for the
    client: `nooa.runtime.actor._resolve_provider_formatter` does an
    `isinstance(llm_client, ResponsesClient)` check to pick the wire format,
    and a wrapper class defeats it silently (no exception, just the wrong
    formatter). Constructing a `Worker` around a real `ResponsesClient` and
    running it through the exact function the runtime calls is a stronger
    proof than inspecting `type(worker.llm)` in isolation — it demonstrates
    the actual downstream behaviour the reviewer named.
    """
    from nooa.context_blocks.formatter import ResponsesProviderFormatter
    from nooa.runtime.actor import _resolve_provider_formatter
    from nooa.unifiedllm import ResponsesClient

    real_client = ResponsesClient(model='openai/gpt-5.3-codex')
    worker, _ = _make_worker(ledger, graph, repo, specs=[], llm=real_client)

    assert worker.llm is real_client

    default_formatter = object()
    resolved = _resolve_provider_formatter(worker.llm, default_formatter)
    assert isinstance(resolved, ResponsesProviderFormatter)


# -- Ledger.set_claim_status(retries=None) contract (task scope item 5) --------


def test_set_claim_status_with_no_retries_kwarg_leaves_the_column_untouched(
    ledger: Ledger, graph: Graph, repo: Path, unit: Unit
) -> None:
    """Pins the exact `F-20`-shaped contract scope item 5 exists for.

    `retries=None` (the default) must leave an already-written `retries`
    value alone, not silently reset it — the caller-visible difference
    between "the caller has nothing new to say about retries" and "the
    caller is asserting zero retries". A version of `set_claim_status`
    that maps `None` to `0` passes every other test in this suite and in
    `tests/ledger/test_store.py`/`test_store_fixes.py` (49 tests, none of
    which call `set_claim_status` without `retries` after first setting it
    to a nonzero value) — this is the one assertion that tells the two
    implementations apart.
    """
    worker, _ = _make_worker(ledger, graph, repo, specs=[])
    worker.begin_unit(unit)
    claim_id = worker.propose_claim('OrderRepository.get raises OrderNotFound.', 'code')

    with_retry = ledger.set_claim_status(claim_id, 'confirmed', RUN_ID, verified_sha='sha1', retries=1)
    assert with_retry.retries == 1

    untouched = ledger.set_claim_status(claim_id, 'refuted', RUN_ID)

    assert untouched.retries == 1
    assert untouched.status == 'refuted'


# -- integration ----------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv('LLM_HOST'), reason='needs a live LLM_HOST')
def test_live_survey_on_order_repository_get_produces_at_least_one_claim_row(
    ledger: Ledger, graph: Graph, repo: Path, unit: Unit
) -> None:
    from seshat.agents.verifier_author import make_verifier_author
    from seshat.agents.worker import make_worker
    from seshat.config import Settings

    settings = Settings.load()
    memory = open_working_memory(repo)
    verifier_agent = make_verifier_author(settings)
    worker = make_worker(settings, memory, ledger, graph, RUN_ID, verifier_agent)

    asyncio.run(run_unit(worker, unit, ledger, graph, RUN_ID))

    rows = ledger.claims_for_unit(unit.id)
    assert len(rows) >= 1
