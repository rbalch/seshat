"""Acceptance tests for T-12: the Answer agent and `seshat ask`.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-12-answer-agent-ask.md. Committed alone, before any
implementation exists, per the project's red-then-green contract.

Hermetic: every test opens a fresh `.seshat/ledger.db` under `tmp_path`
(plain sqlite, no codegraph, no git) and installs `FakeLLMClient` where a
model is involved. The one `-m integration` test needs a live `LLM_HOST`
and is skipped without one.

Ledger fixture honesty: `stale_claim_id` is set `confirmed` and *then*
`stale` via `set_claim_status` (the same two-call shape T-03's own tests use
at tests/ledger/test_store.py:350-356), so the `[STALE]` test exercises a
claim whose `claim_status` really is `'stale'` in the ledger — not a claim
that merely looks stale by naming. `all_unknown_ids` below is deliberately
disjoint from every id `ledger` fixture ever issues (a fresh uuid4-shaped
string), so the "every citation unknown" collapse test is distinct from the
mixed-citations test: one exercises "some ids survive filtering", the other
"zero ids survive filtering" — these are different code paths in
`validate_answer` and a fixture that could not tell them apart would let a
wrong implementation pass either test.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from nooa.unifiedllm import FakeLLMClient, LLMResponse

from seshat import cli
from seshat.ledger.models import Claim, Concept, Unit
from seshat.ledger.store import Ledger

RUN_ID = 'run1'
UNKNOWN_ID = '00000000-unknown-does-not-exist'


# -- ledger fixture helpers (built inline, never via tests/fixtures/target) --


def make_unit(unit_id: str, **overrides) -> Unit:
    fields = {
        'id': unit_id,
        'repo_id': '',
        'file_path': 'demo/orders.py',
        'qualified_name': 'OrderRepository.get',
        'kind': 'method',
        'start_line': 10,
        'end_line': 20,
        'ast_hash': 'deadbeef',
        'inbound_calls': 1,
        'first_seen_run': RUN_ID,
        'last_seen_run': RUN_ID,
        'last_scanned_run': RUN_ID,
        'status': 'pending',
    }
    fields.update(overrides)
    return Unit(**fields)


def make_claim(unit_id: str, text: str, **overrides) -> Claim:
    fields = {
        'id': '',
        'repo_id': '',
        'unit_id': unit_id,
        'text': text,
        'kind': 'structural',
        'source': 'code',
        'mode': 'claims',
        'status': 'conjectured',
        'confidence': 0.9,
        'candidate_rule': 0,
        'rule_sightings': 0,
        'created_run': RUN_ID,
        'verified_run': None,
        'verified_sha': None,
        'retries': 0,
    }
    fields.update(overrides)
    return Claim(**fields)


def make_concept(**overrides) -> Concept:
    fields = {
        'id': '',
        'repo_id': '',
        'title': 'OrderRepository lifecycle',
        'body': 'OrderRepository.get raises OrderNotFound when the id is missing.',
        'created_run': RUN_ID,
        'status': 'current',
    }
    fields.update(overrides)
    return Concept(**fields)


class LedgerIds:
    """The ids the `ledger` fixture below issued, keyed by role."""

    def __init__(self) -> None:
        self.order_not_found: str = ''
        self.fresh: str = ''
        self.stale: str = ''
        self.concept: str = ''
        self.concept_stale_evidence: str = ''


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[tuple[Ledger, LedgerIds]]:
    """A ledger with a few confirmed claims, one stale claim, and two concepts.

    `concept` (fresh evidence, `order_not_found`) and `concept_stale_evidence`
    (evidence is `stale`, moved to `'stale'` *after* the concept was created —
    the same "confirmed at creation, drifts later" order a real scan produces)
    let the concept-citation tests tell a genuinely stale evidence claim apart
    from a genuinely fresh one, the same way the claim-citation tests already do.
    """
    with Ledger.open(tmp_path / 'target-repo') as l:
        l.create_run(id=RUN_ID, mode='claims')
        unit = make_unit('u1', repo_id=l.repo_id)
        l.upsert_unit(unit, RUN_ID)

        ids = LedgerIds()

        order_not_found = l.add_claim(
            make_claim(unit.id, 'OrderRepository.get raises OrderNotFound when the id is missing.')
        )
        l.set_claim_status(order_not_found.id, 'confirmed', RUN_ID, verified_sha='sha1')
        ids.order_not_found = order_not_found.id

        fresh = l.add_claim(make_claim(unit.id, 'OrderRepository.save writes the record to the repository.'))
        l.set_claim_status(fresh.id, 'confirmed', RUN_ID, verified_sha='sha1')
        ids.fresh = fresh.id

        # confirmed, then explicitly moved to 'stale' — a genuinely stale row,
        # not merely a name that sounds stale.
        stale = l.add_claim(make_claim(unit.id, 'OrderRepository.get validates the customer id.'))
        l.set_claim_status(stale.id, 'confirmed', RUN_ID, verified_sha='sha1')
        ids.stale = stale.id

        concept = l.add_concept(make_concept(), evidence_claim_ids=[order_not_found.id])
        ids.concept = concept.id

        concept_stale_evidence = l.add_concept(
            make_concept(title='OrderRepository validation'), evidence_claim_ids=[stale.id]
        )
        ids.concept_stale_evidence = concept_stale_evidence.id

        # only now does the evidence claim actually go stale — after both
        # concepts exist, so `concept_stale_evidence`'s evidence is stale and
        # `concept`'s evidence (a different claim) is not.
        l.set_claim_status(stale.id, 'stale', RUN_ID)

        yield l, ids


# -- validate_answer ----------------------------------------------------------


def test_validate_answer_drops_unknown_citation_ids_and_removes_uncited_sentences(
    ledger: tuple[Ledger, LedgerIds],
) -> None:
    from seshat.agents.answer import Answer, Sentence, validate_answer

    l, ids = ledger
    answer = Answer(
        sentences=[
            Sentence(text='OrderRepository.get raises OrderNotFound.', citations=[ids.order_not_found]),
            Sentence(text='This sentence cites nothing real.', citations=[UNKNOWN_ID]),
        ]
    )

    result = validate_answer(answer, l)

    assert len(result.sentences) == 2
    assert result.sentences[0].citations == [ids.order_not_found]
    assert result.sentences[1].text == '[uncited sentence removed]'
    assert result.sentences[1].citations == []


def test_validate_answer_mixed_survivors_does_not_collapse(ledger: tuple[Ledger, LedgerIds]) -> None:
    """Worked example from the task file: one real id, two unknown ids -> 3 sentences, no collapse."""
    from seshat.agents.answer import Answer, Sentence, validate_answer

    l, ids = ledger
    answer = Answer(
        sentences=[
            Sentence(text='Real one.', citations=[ids.order_not_found]),
            Sentence(text='Fake one.', citations=[UNKNOWN_ID]),
            Sentence(text='Also fake.', citations=[UNKNOWN_ID + '-2']),
        ]
    )

    result = validate_answer(answer, l)

    assert len(result.sentences) == 3
    assert result.sentences[0].citations == [ids.order_not_found]
    assert result.sentences[1].text == '[uncited sentence removed]'
    assert result.sentences[2].text == '[uncited sentence removed]'


def test_validate_answer_collapses_when_every_citation_id_is_unknown(ledger: tuple[Ledger, LedgerIds]) -> None:
    """Distinct from the mixed case: every single citation id is unknown -> full collapse."""
    from seshat.agents.answer import Answer, Sentence, validate_answer

    l, _ids = ledger
    answer = Answer(
        sentences=[
            Sentence(text='Made up fact one.', citations=[UNKNOWN_ID]),
            Sentence(text='Made up fact two.', citations=[UNKNOWN_ID + '-2']),
        ]
    )

    result = validate_answer(answer, l)

    assert len(result.sentences) == 1
    assert result.sentences[0].text == 'Nothing in the ledger answers that.'
    assert result.sentences[0].citations == []


# -- render_answer --------------------------------------------------------------


def test_render_answer_marks_a_stale_claims_citation_stale(ledger: tuple[Ledger, LedgerIds]) -> None:
    from seshat.agents.answer import Answer, Sentence, render_answer

    l, ids = ledger
    answer = Answer(sentences=[Sentence(text='The customer id gets validated.', citations=[ids.stale])])

    rendered = render_answer(answer, l)

    assert 'The customer id gets validated.' in rendered
    assert '[STALE]' in rendered


def test_render_answer_does_not_mark_a_fresh_claims_citation_stale(ledger: tuple[Ledger, LedgerIds]) -> None:
    from seshat.agents.answer import Answer, Sentence, render_answer

    l, ids = ledger
    answer = Answer(sentences=[Sentence(text='Orders get saved.', citations=[ids.fresh])])

    rendered = render_answer(answer, l)

    assert '[STALE]' not in rendered


# -- concept ids as citations (T-12 review round: coverage gap) --------------


def test_validate_answer_keeps_a_real_concept_id_and_drops_an_unknown_one(
    ledger: tuple[Ledger, LedgerIds],
) -> None:
    """Concept ids and claim ids are both looked up by `validate_answer`; neither is special-cased."""
    from seshat.agents.answer import Answer, Sentence, validate_answer

    l, ids = ledger
    answer = Answer(
        sentences=[
            Sentence(text='OrderRepository has a documented lifecycle.', citations=[ids.concept]),
            Sentence(text='This concept does not exist.', citations=[UNKNOWN_ID]),
        ]
    )

    result = validate_answer(answer, l)

    assert len(result.sentences) == 2
    assert result.sentences[0].citations == [ids.concept]
    assert result.sentences[1].text == '[uncited sentence removed]'
    assert result.sentences[1].citations == []


def test_render_answer_marks_a_concept_citation_stale_when_its_evidence_is_stale(
    ledger: tuple[Ledger, LedgerIds],
) -> None:
    """The assertion that matters: a concept citation must consult `format_citation`
    on its evidence, not just print the concept's own id or title.
    """
    from seshat.agents.answer import Answer, Sentence, render_answer

    l, ids = ledger
    stale_evidence_answer = Answer(
        sentences=[Sentence(text='The customer id gets validated.', citations=[ids.concept_stale_evidence])]
    )
    fresh_evidence_answer = Answer(
        sentences=[Sentence(text='OrderRepository has a documented lifecycle.', citations=[ids.concept])]
    )

    stale_rendered = render_answer(stale_evidence_answer, l)
    fresh_rendered = render_answer(fresh_evidence_answer, l)

    assert '[STALE]' in stale_rendered
    assert '[STALE]' not in fresh_rendered


def test_render_answer_both_a_concept_id_and_a_claim_id_survive_and_render(
    ledger: tuple[Ledger, LedgerIds],
) -> None:
    """A claim id and a concept id cited by the same answer both survive validation and both render."""
    from seshat.agents.answer import Answer, Sentence, render_answer, validate_answer

    l, ids = ledger
    answer = Answer(
        sentences=[
            Sentence(text='OrderRepository.get raises OrderNotFound.', citations=[ids.order_not_found]),
            Sentence(text='OrderRepository has a documented lifecycle.', citations=[ids.concept]),
        ]
    )

    validated = validate_answer(answer, l)
    assert validated.sentences[0].citations == [ids.order_not_found]
    assert validated.sentences[1].citations == [ids.concept]

    rendered = render_answer(validated, l)
    assert 'OrderRepository.get raises OrderNotFound.' in rendered
    assert 'OrderRepository has a documented lifecycle.' in rendered
    # both lines carry a rendered citation, not a bare id or an empty bracket
    assert f'[{ids.order_not_found}]' not in rendered
    assert f'[{ids.concept}]' not in rendered


# -- search_claims tool ------------------------------------------------------


def test_search_claims_returns_a_hit_with_a_citation_string(ledger: tuple[Ledger, LedgerIds]) -> None:
    from seshat.agents.answer import AnswerAgent

    l, ids = ledger
    agent = AnswerAgent(FakeLLMClient(), l)

    hits = agent.search_claims('OrderNotFound')

    assert len(hits) == 1
    assert hits[0]['id'] == ids.order_not_found
    assert isinstance(hits[0]['citation_display'], str)
    assert hits[0]['citation_display']
    assert 'citation_display' in hits[0] and 'id' in hits[0]
    assert hits[0]['id'] != hits[0]['citation_display']


# -- ask -q -----------------------------------------------------------------


def _scripted_answer_response(question_ids: LedgerIds) -> LLMResponse:
    import json

    payload = {
        'sentences': [
            {
                'text': 'OrderRepository.get raises OrderNotFound when the id is missing.',
                'citations': [question_ids.order_not_found],
            }
        ]
    }
    content = json.dumps(payload)
    return LLMResponse(
        raw_response=None,
        content=content,
        tool_calls=[],
        finish_reason='stop',
        assistant_message={'role': 'assistant', 'content': content},
        reasoning=None,
        usage={'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
    )


def test_ask_q_prints_the_sentence_and_its_citation_and_exits_zero(
    ledger: tuple[Ledger, LedgerIds],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from seshat.agents.answer import AnswerAgent

    l, ids = ledger
    repo = l.repo_root

    def fake_factory(ledger_arg: Ledger, settings, *, model: str | None = None) -> AnswerAgent:
        llm = FakeLLMClient(scripted_responses=[_scripted_answer_response(ids)])
        return AnswerAgent(llm, ledger_arg)

    monkeypatch.setattr(cli, 'answer_agent_factory', fake_factory)
    monkeypatch.setenv('LLM_HOST', 'http://example.invalid')

    exit_code = cli.main(['ask', str(repo), '-q', 'Why does OrderRepository.get fail?'])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert 'OrderRepository.get raises OrderNotFound when the id is missing.' in out
    assert 'OrderRepository.get' in out  # the qualified name from the citation


# -- no memory affordance -----------------------------------------------------


def test_answer_agent_defines_no_recall_or_remember_method() -> None:
    from seshat.agents.answer import AnswerAgent

    assert not hasattr(AnswerAgent, 'recall')
    assert not hasattr(AnswerAgent, 'remember')


def test_answer_module_imports_nothing_from_seshat_memory_and_never_names_memory_db() -> None:
    import seshat.agents.answer as answer_module

    source = Path(answer_module.__file__).read_text()
    assert 'seshat.memory' not in source
    assert 'memory.db' not in source


# -- seshat --help lists ask --------------------------------------------------


def test_seshat_help_lists_ask(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(['--help'])
    out = capsys.readouterr().out
    assert 'ask' in out


# -- integration ---------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv('LLM_HOST'), reason='needs a live LLM_HOST')
def test_ask_a_real_question_over_a_scanned_fixture_returns_at_least_one_cited_sentence(
    ledger: tuple[Ledger, LedgerIds],
) -> None:
    import asyncio

    from seshat.agents.answer import AnswerAgent, validate_answer
    from seshat.config import Settings

    l, _ids = ledger
    settings = Settings.load()
    from nooa.unifiedllm import CompletionClient

    llm = CompletionClient(**settings.llm_kwargs('answer'))
    agent = AnswerAgent(llm, l)

    answer = asyncio.run(agent.answer('Why does OrderRepository.get fail?'))
    validated = validate_answer(answer, l)

    assert any(s.citations for s in validated.sentences)
