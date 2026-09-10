"""Acceptance tests for T-10: the Reflection agent and candidate rules.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-10-reflection-agent.md. Committed alone, before any
implementation exists, per the project's red-then-green contract.

Hermetic: a fresh `.seshat/ledger.db` under `tmp_path`, pre-filled with
confirmed, refuted and conjectured claims across four units, and a
`ReflectionAgent` driven entirely by `nooa.unifiedllm.FakeLLMClient` via
`agent.set_llm(...)` — no network, no live `LLM_HOST` required. See
`tests/agents/test_verifier_author.py` for the same fake-LLM shape.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from nooa.unifiedllm import FakeLLMClient, LLMResponse

from seshat.agents.reflection import (
    ReflectionAgent,
    ReflectionSummary,
    run_reflection,
)
from seshat.candidates import flag_candidates
from seshat.ledger.models import Claim, Unit
from seshat.ledger.store import Ledger

RUN_ID = 'run1'


# -- shared fixtures ---------------------------------------------------------


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[Ledger]:
    with Ledger.open(tmp_path / 'ledger_repo') as l:
        l.create_run(id=RUN_ID, mode='claims')
        yield l


def _unit(ledger: Ledger, unit_id: str, qualified_name: str) -> Unit:
    unit = Unit(
        id=unit_id,
        repo_id='',
        file_path=f'{unit_id}.py',
        qualified_name=qualified_name,
        kind='function',
        start_line=1,
        end_line=5,
        ast_hash='deadbeef',
        inbound_calls=0,
        first_seen_run=RUN_ID,
        last_seen_run=RUN_ID,
        last_scanned_run=RUN_ID,
        status='scanned',
    )
    return ledger.upsert_unit(unit, RUN_ID)


def _add_claim(ledger: Ledger, unit_id: str, text: str, status: str) -> Claim:
    claim = Claim(
        id='',
        repo_id='',
        unit_id=unit_id,
        text=text,
        kind='structural',
        source='code',
        mode='claims',
        status='conjectured',
        confidence=0.9,
        candidate_rule=0,
        rule_sightings=0,
        created_run=RUN_ID,
        verified_run=None,
        verified_sha=None,
        retries=0,
    )
    stored = ledger.add_claim(claim)
    if status != 'conjectured':
        stored = ledger.set_claim_status(stored.id, status, RUN_ID, verified_sha='deadbeef')
    return stored


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


def _agent(*responses: LLMResponse) -> ReflectionAgent:
    agent = ReflectionAgent(llm=FakeLLMClient())
    agent.set_llm(FakeLLMClient(scripted_responses=list(responses)))
    return agent


def _output(concepts: list[dict] | None = None, patterns: list[dict] | None = None) -> dict:
    return {'concepts': concepts or [], 'patterns': patterns or []}


# -- fixture ledger: four units, confirmed/refuted/conjectured claims -------


def _seed_four_units(ledger: Ledger) -> dict[str, list[Claim]]:
    """Four units, each with one confirmed, one refuted and one conjectured claim."""
    claims: dict[str, list[Claim]] = {}
    for i in range(1, 5):
        unit_id = f'u{i}'
        _unit(ledger, unit_id, f'mod.unit{i}')
        confirmed = _add_claim(ledger, unit_id, f'unit{i} does X', 'confirmed')
        refuted = _add_claim(ledger, unit_id, f'unit{i} does Y', 'refuted')
        conjectured = _add_claim(ledger, unit_id, f'unit{i} does Z', 'conjectured')
        claims[unit_id] = [confirmed, refuted, conjectured]
    return claims


# -- bullet: one concept citing two confirmed claims -> row + two evidence --


def test_concept_citing_two_confirmed_claims_writes_concept_and_evidence(ledger: Ledger) -> None:
    claims = _seed_four_units(ledger)
    c1 = claims['u1'][0]
    c2 = claims['u2'][0]

    payload = _output(
        concepts=[
            {
                'title': 'X across units',
                'body': f'Both units do X [{c1.id}] [{c2.id}]',
                'evidence': [c1.id, c2.id],
            }
        ]
    )
    agent = _agent(_response(payload))

    summary = asyncio.run(run_reflection(agent, ledger, RUN_ID, batch_size=40))

    assert summary.concepts_written == 1
    assert summary.concepts_discarded == 0

    row = ledger.conn.execute('SELECT * FROM concepts').fetchone()
    assert row is not None
    evidence_rows = ledger.conn.execute(
        'SELECT claim_id FROM concept_evidence WHERE concept_id = ?', (row['id'],)
    ).fetchall()
    assert {r['claim_id'] for r in evidence_rows} == {c1.id, c2.id}


# -- bullet: concept citing a refuted claim id -> dropped, rest kept --------


def test_concept_citing_refuted_claim_drops_it_but_still_writes(ledger: Ledger) -> None:
    claims = _seed_four_units(ledger)
    confirmed = claims['u1'][0]
    refuted = claims['u1'][1]

    payload = _output(
        concepts=[
            {
                'title': 'X on unit1',
                'body': f'unit1 does X [{confirmed.id}], maybe Y [{refuted.id}]',
                'evidence': [confirmed.id, refuted.id],
            }
        ]
    )
    agent = _agent(_response(payload))

    summary = asyncio.run(run_reflection(agent, ledger, RUN_ID, batch_size=40))

    assert summary.concepts_written == 1
    assert summary.concepts_discarded == 0

    row = ledger.conn.execute('SELECT * FROM concepts').fetchone()
    assert row is not None
    evidence_rows = ledger.conn.execute(
        'SELECT claim_id FROM concept_evidence WHERE concept_id = ?', (row['id'],)
    ).fetchall()
    assert {r['claim_id'] for r in evidence_rows} == {confirmed.id}


# -- bullet: concept with all-invalid evidence -> not written, counted -----


def test_concept_with_all_invalid_evidence_is_discarded_and_counted(ledger: Ledger) -> None:
    claims = _seed_four_units(ledger)
    refuted = claims['u1'][1]
    conjectured = claims['u1'][2]

    payload = _output(
        concepts=[
            {
                'title': 'bogus concept',
                'body': f'made up [{refuted.id}] [{conjectured.id}] [not-a-real-id]',
                'evidence': [refuted.id, conjectured.id, 'not-a-real-id'],
            }
        ]
    )
    agent = _agent(_response(payload))

    summary = asyncio.run(run_reflection(agent, ledger, RUN_ID, batch_size=40))

    assert summary.concepts_written == 0
    assert summary.concepts_discarded == 1

    row = ledger.conn.execute('SELECT * FROM concepts').fetchone()
    assert row is None


# -- bullet: pattern on three units, no exceptions -> flagged --------------


def test_pattern_on_three_units_no_exceptions_flags_candidate_rule(ledger: Ledger) -> None:
    claims = _seed_four_units(ledger)
    cited = [claims['u1'][0], claims['u2'][0], claims['u3'][0]]

    payload = _output(
        patterns=[
            {
                'description': 'each unit does X the same way',
                'claim_ids': [c.id for c in cited],
                'exceptions': [],
            }
        ]
    )
    agent = _agent(_response(payload))

    summary = asyncio.run(run_reflection(agent, ledger, RUN_ID, batch_size=40))

    assert summary.claims_flagged == 3
    for c in cited:
        row = ledger.conn.execute('SELECT candidate_rule, rule_sightings FROM claims WHERE id = ?', (c.id,)).fetchone()
        assert row['candidate_rule'] == 1
        assert row['rule_sightings'] == 3


# -- bullet: same pattern on two units -> nothing flagged -------------------


def test_pattern_on_two_units_flags_nothing(ledger: Ledger) -> None:
    claims = _seed_four_units(ledger)
    cited = [claims['u1'][0], claims['u2'][0]]

    payload = _output(
        patterns=[
            {
                'description': 'two units do X the same way',
                'claim_ids': [c.id for c in cited],
                'exceptions': [],
            }
        ]
    )
    agent = _agent(_response(payload))

    summary = asyncio.run(run_reflection(agent, ledger, RUN_ID, batch_size=40))

    assert summary.claims_flagged == 0
    for c in cited:
        row = ledger.conn.execute('SELECT candidate_rule, rule_sightings FROM claims WHERE id = ?', (c.id,)).fetchone()
        assert row['candidate_rule'] == 0
        assert row['rule_sightings'] == 0


# -- bullet: three units but one exception string -> nothing flagged -------


def test_pattern_on_three_units_with_one_exception_flags_nothing(ledger: Ledger) -> None:
    claims = _seed_four_units(ledger)
    cited = [claims['u1'][0], claims['u2'][0], claims['u3'][0]]

    payload = _output(
        patterns=[
            {
                'description': 'nearly every unit does X the same way',
                'claim_ids': [c.id for c in cited],
                'exceptions': ['unit3 does it differently'],
            }
        ]
    )
    agent = _agent(_response(payload))

    summary = asyncio.run(run_reflection(agent, ledger, RUN_ID, batch_size=40))

    assert summary.claims_flagged == 0
    for c in cited:
        row = ledger.conn.execute('SELECT candidate_rule, rule_sightings FROM claims WHERE id = ?', (c.id,)).fetchone()
        assert row['candidate_rule'] == 0
        assert row['rule_sightings'] == 0


# -- bullet: batch_size=2 over five claims -> fake.call_count == 3 ----------


def test_batch_size_two_over_five_claims_calls_fake_three_times(ledger: Ledger) -> None:
    for i in range(1, 6):
        unit_id = f'v{i}'
        _unit(ledger, unit_id, f'mod.vunit{i}')
        _add_claim(ledger, unit_id, f'vunit{i} does X', 'confirmed')

    empty = _output()
    agent = _agent(_response(empty), _response(empty), _response(empty))

    summary = asyncio.run(run_reflection(agent, ledger, RUN_ID, batch_size=2))

    assert agent.llm.call_count == 3
    assert summary.batches == 3


# -- ReflectionSummary shape --------------------------------------------


def test_reflection_summary_has_exactly_four_integer_fields() -> None:
    summary = ReflectionSummary(concepts_written=1, concepts_discarded=2, claims_flagged=3, batches=4)
    assert summary.model_dump() == {
        'concepts_written': 1,
        'concepts_discarded': 2,
        'claims_flagged': 3,
        'batches': 4,
    }


# -- flag_candidates direct unit test (module-level function in candidates.py) --


def test_flag_candidates_returns_count_of_flagged_claims(ledger: Ledger) -> None:
    from seshat.agents.reflection import PatternDraft

    claims = _seed_four_units(ledger)
    cited = [claims['u1'][0], claims['u2'][0], claims['u3'][0]]
    pattern = PatternDraft(description='x', claim_ids=[c.id for c in cited], exceptions=[])

    count = flag_candidates(ledger, [pattern], RUN_ID)

    assert count == 3
