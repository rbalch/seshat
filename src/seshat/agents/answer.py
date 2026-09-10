"""The answer agent: the fourth of the four model generation points (plan §2/§7).

`seshat ask` is a REPL over the ledger. `AnswerAgent` searches confirmed claims
and concepts through tools and answers with at least one citation per
sentence — never from the model's own knowledge, never from working memory.
`AnswerAgent.answer` is the one `CodeActStrategy` generation point in this
module: its docstring is the prompt, its `...` body is the generation call
(see `seshat.agents.worker.Worker.survey` for the same shape). Every other
method is a plain Python method with a real body, so CodeAct's
`execute_python` tool can call it directly (AGENTS.md: "methods with bodies
are tools for free").

`validate_answer` is the enforcement point AGENTS.md's "Never" list names:
"never let the answer agent cite working memory, or write a sentence with no
citation." It is deterministic Python, never the model, that drops an
unknown citation id, replaces an emptied-out sentence with a placeholder,
and collapses the whole answer to "Nothing in the ledger answers that." when
every sentence lost its citation — this agent imports no working-memory
module and has no recall/remember tool at all (task scope item 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nooa import Agent
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy

from seshat.ledger.store import Ledger
from seshat.render import format_citation

__all__ = ['Answer', 'AnswerAgent', 'Sentence', 'render_answer', 'validate_answer']

NOTHING_IN_LEDGER = 'Nothing in the ledger answers that.'
UNCITED_PLACEHOLDER = '[uncited sentence removed]'


@dataclass(frozen=True)
class Sentence:
    """One sentence of an answer and the bare claim/concept ids backing it.

    `citations` holds bare ids only — never a rendered display string —
    because `validate_answer` looks each one up in the ledger to decide
    whether it still exists.
    """

    text: str
    citations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Answer:
    """What `AnswerAgent.answer` returns: a sequence of cited sentences."""

    sentences: list[Sentence] = field(default_factory=list)


def _claim_citation_display(ledger: Ledger, claim_id: str) -> str | None:
    """`format_citation` of `claim_id`'s row, or `None` if `claim_id` is not a claim id."""
    try:
        citation = ledger.citation(claim_id)
    except KeyError:
        return None
    return format_citation(citation)


def _concept_citation_display(ledger: Ledger, concept_id: str) -> str | None:
    """A concept's citation display: every evidence claim's own `format_citation`, joined.

    A `Concept` has no `qualified_name`/`file_path`/line span of its own —
    those live on the claims (and, through them, the units) it cites as
    evidence — so a concept can never be rendered by `format_citation`
    directly. Returns `None` for an unknown concept id or one with no
    renderable evidence left.
    """
    concept = ledger.concept(concept_id)
    if concept is None:
        return None
    displays = [d for d in (_claim_citation_display(ledger, cid) for cid in ledger.concept_evidence(concept.id)) if d]
    return '; '.join(displays) if displays else None


def _citation_display(ledger: Ledger, citation_id: str) -> str | None:
    """`citation_id`'s rendered display, whether it names a claim or a concept, else `None`."""
    display = _claim_citation_display(ledger, citation_id)
    if display is not None:
        return display
    return _concept_citation_display(ledger, citation_id)


def _citation_exists(ledger: Ledger, citation_id: str) -> bool:
    return _citation_display(ledger, citation_id) is not None


def validate_answer(answer: Answer, ledger: Ledger) -> Answer:
    """Deterministic enforcement, three stages in order (task scope item 2).

    (a) Drop any citation id that does not exist in the ledger.
    (b) A sentence left with no citation is replaced by the uncited
        placeholder, itself uncited.
    (c) If every sentence lost its citation at (a) — no sentence survives
        (b) with at least one citation — the whole answer collapses to the
        single "nothing in the ledger" sentence, with no citations.

    A placeholder sentence never counts as a cited sentence, so stage (c)'s
    check is done against the *pre-placeholder* survivors, not the sentence
    count.
    """
    survivors: list[Sentence] = []
    any_cited = False
    for sentence in answer.sentences:
        kept = [cid for cid in sentence.citations if _citation_exists(ledger, cid)]
        if kept:
            any_cited = True
            survivors.append(Sentence(text=sentence.text, citations=kept))
        else:
            survivors.append(Sentence(text=UNCITED_PLACEHOLDER, citations=[]))

    if not any_cited:
        return Answer(sentences=[Sentence(text=NOTHING_IN_LEDGER, citations=[])])
    return Answer(sentences=survivors)


def render_answer(answer: Answer, ledger: Ledger) -> str:
    """Each sentence, followed by its citations rendered through `format_citation`."""
    lines: list[str] = []
    for sentence in answer.sentences:
        displays = [d for d in (_citation_display(ledger, cid) for cid in sentence.citations) if d]
        if displays:
            cites = ' '.join(f'[{d}]' for d in displays)
            lines.append(f'{sentence.text} {cites}')
        else:
            lines.append(sentence.text)
    return '\n'.join(lines)


class AnswerAgent(Agent):
    """You are Seshat's answer agent: you answer questions about a codebase using only
    what the ledger has verified, never your own knowledge of the code and never
    anything recalled from working memory (this agent has none).

    Call `search_claims(query)` and `search_concepts(query)` to find relevant rows by
    full-text search. Call `claims_for(qualified_name)` when the question names a
    specific symbol. Call `concept(id)` to read one concept's body and its evidence.
    Every tool returns hits with two fields: `id` (a bare claim or concept id) and
    `citation_display` (that id already rendered as a citation) — cite the `id`, never
    the display string.

    Every sentence you write must carry at least one citation id in
    `Sentence.citations`, drawn only from ids a tool actually returned. If your search
    finds nothing relevant, say so plainly — do not answer from anything you already
    know about the code. `validate_answer` (deterministic, not you) will drop any
    citation id that turns out not to exist and remove any sentence left uncited, so
    a fabricated id buys nothing.
    """

    def __init__(self, llm: Any, ledger: Ledger, **kwargs: Any) -> None:
        super().__init__(llm=llm, **kwargs)
        self.ledger = ledger

    # -- tools (plain methods; CodeAct calls these directly) -------------

    def search_claims(self, query: str) -> list[dict]:
        """Full-text search over claims; each hit carries `id` and `citation_display`."""
        return [
            {'id': claim.id, 'citation_display': format_citation(self.ledger.citation(claim.id))}
            for claim in self.ledger.search_claims(query)
        ]

    def search_concepts(self, query: str) -> list[dict]:
        """Full-text search over concepts; each hit carries `id` and `citation_display`."""
        hits: list[dict] = []
        for concept in self.ledger.search_concepts(query):
            display = _concept_citation_display(self.ledger, concept.id)
            hits.append({'id': concept.id, 'citation_display': display or concept.title})
        return hits

    def claims_for(self, qualified_name: str) -> list[dict]:
        """Every claim for the unit named `qualified_name`; `[]` if no such unit exists."""
        matches = [u for u in self.ledger.units() if u.qualified_name == qualified_name]
        if not matches:
            return []
        unit = matches[0]
        return [
            {'id': claim.id, 'citation_display': format_citation(self.ledger.citation(claim.id))}
            for claim in self.ledger.claims_for_unit(unit.id)
        ]

    def concept(self, id: str) -> dict:
        """One concept's title, body and evidence; `{}` if `id` names no concept."""
        found = self.ledger.concept(id)
        if found is None:
            return {}
        evidence = [
            {'id': claim_id, 'citation_display': format_citation(self.ledger.citation(claim_id))}
            for claim_id in self.ledger.concept_evidence(found.id)
        ]
        return {
            'id': found.id,
            'citation_display': _concept_citation_display(self.ledger, found.id) or found.title,
            'title': found.title,
            'body': found.body,
            'evidence': evidence,
        }

    # -- generation point -------------------------------------------------

    @strategy(CodeActStrategy())
    async def answer(self, question: str) -> Answer:
        """Answer `question` using only what the ledger's tools return.

        1. Call `search_claims(question)` and `search_concepts(question)` first;
           if `question` names a specific symbol, also call `claims_for(name)`.
        2. Widen the search with different phrasings if the first pass finds
           nothing — never fall back to what you already know about the code.
        3. Build `Answer(sentences=[...])`: each `Sentence(text, citations)` cites
           only ids a tool actually returned, in `citations`, never in `text`.
        4. If nothing relevant turns up after searching, return a single
           `Sentence` saying so, with no citations — `validate_answer` will turn
           that into the standard "nothing in the ledger" wording either way.

        Return the `Answer`. Never write a sentence with no citation unless it is
        exactly the "nothing found" sentence.
        """
        ...
