"""The reflection agent: the third of the four model generation points.

After a scan, confirmed claims are rolled into `Concept` rows with evidence
links, and structural patterns that hold across three or more units with no
exception get `candidate_rule=1` and a sightings count — `flag_candidates` in
`seshat/candidates.py` is what actually sets those two columns. Seshat
flags; it never writes a rule (AGENTS.md "Never: emit a governance rule");
the memory note that the rule of three is a heuristic for humans applies
here only as a threshold on a flag, never as anything closer to a decision.

`ReflectionAgent.reflect` is a NOOA `Predict` generation method
(`nooa.Agent` + `@strategy(PredictStrategy())`): its docstring is the prompt
sent to the model, its `...` body is the generation point itself — same
shape as `seshat.agents.verifier_author.VerifierAuthor.author`, see that
module and `nooa/ellipsis_detection.py`.

`run_reflection` and `flag_candidates` (imported lazily below to avoid a
cycle: `candidates.py` imports `PatternDraft` from here) are plain,
deterministic Python — the model is used at exactly the one generation
point, `reflect`, per AGENTS.md's "Orchestration ... is deterministic
Python" architecture rule.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from nooa import Agent
from nooa.decorators import strategy
from nooa.strategies import PredictStrategy
from pydantic import BaseModel, Field

from seshat.config import Settings
from seshat.ledger.models import Claim, Concept, Run
from seshat.ledger.store import Ledger


class ConceptDraft(BaseModel):
    """One concept the model proposes, grouping related confirmed claims.

    `body` is prose that cites the claims it draws on by id in square
    brackets (e.g. `[abc123]`); `evidence` lists exactly those ids.
    `run_reflection` keeps only the ids among `evidence` that are also in
    the current batch before writing the row (scope item 3) — every other
    id is dropped rather than trusted, since a batch is the only claim set
    this draft could truthfully have cited.
    """

    title: str
    body: str
    evidence: list[str] = Field(default_factory=list)


class PatternDraft(BaseModel):
    """One structural pattern the model reports recurring across units.

    `exceptions` is free text naming any unit where the pattern did not
    hold; an empty list means none were found. `flag_candidates`
    (`seshat/candidates.py`) is the only thing that turns a `PatternDraft`
    into `candidate_rule`/`rule_sightings` on the claims it cites.
    """

    description: str
    claim_ids: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)


class ReflectionOutput(BaseModel):
    """What one `reflect` call returns: concepts to write, patterns to consider flagging."""

    concepts: list[ConceptDraft] = Field(default_factory=list)
    patterns: list[PatternDraft] = Field(default_factory=list)


class ReflectionSummary(BaseModel):
    """Counters from one `run_reflection` call. Exactly these four integer fields."""

    concepts_written: int
    concepts_discarded: int
    claims_flagged: int
    batches: int


class ReflectionAgent(Agent):
    """Groups one scan's confirmed claims into concepts and reports recurring structural patterns."""

    @strategy(PredictStrategy())
    async def reflect(self, claims: list[Claim]) -> ReflectionOutput:
        """Reflect on `claims` — confirmed claims from one batch of a scan.

        Each entry in `claims` carries its own `id` and `text`. Group
        related claims into `ConceptDraft`s: a `title`, a `body` of prose
        that cites the claims it draws on by id in square brackets (e.g.
        `[abc123]`), and `evidence` listing exactly those ids. Cite only
        ids that appear in `claims` — never invent an id, and never cite a
        claim `body` does not actually reference.

        Separately, name any structural pattern you see recur across more
        than one unit as a `PatternDraft`: a `description`, `claim_ids`
        naming the claims that show it, and `exceptions` — report,
        honestly, any unit among those claims where the pattern did not
        hold. An empty `exceptions` list means you looked and found none;
        never leave a real exception out to make a pattern look cleaner
        than it is, and never report a pattern you have not actually seen
        recur.

        Return `ReflectionOutput(concepts, patterns)`.
        """
        ...


def make_reflection_agent(settings: Settings) -> ReflectionAgent:
    """Build a `ReflectionAgent` wired to the `reflection` role's model."""
    from nooa.unifiedllm import CompletionClient

    llm = CompletionClient(**settings.llm_kwargs('reflection'))
    return ReflectionAgent(llm=llm)


async def run_reflection(
    agent: ReflectionAgent,
    ledger: Ledger,
    run_id: str,
    batch_size: int = 40,
) -> ReflectionSummary:
    """Page `ledger.confirmed_claims`, call `reflect` per batch, write concepts, flag candidates.

    `confirmed_claims` returns only `confirmed` rows, so batch membership
    already implies confirmed — there is no ledger-wide lookup for an
    evidence id outside the current page, by design (scope item 3): a
    `ConceptDraft`'s evidence id survives only if it names a claim in the
    batch just reflected on, every other id is dropped. A concept left
    with no surviving evidence is never written and is counted in
    `concepts_discarded` instead of `concepts_written`.
    """
    from seshat.candidates import flag_candidates

    concepts_written = 0
    concepts_discarded = 0
    claims_flagged = 0
    batches = 0
    offset = 0

    while True:
        batch = ledger.confirmed_claims(limit=batch_size, offset=offset)
        if not batch:
            break
        batch_ids = {claim.id for claim in batch}

        output = await agent.reflect(batch)

        for draft in output.concepts:
            evidence = [claim_id for claim_id in draft.evidence if claim_id in batch_ids]
            if not evidence:
                concepts_discarded += 1
                continue
            ledger.add_concept(
                Concept(
                    id='',
                    repo_id='',
                    title=draft.title,
                    body=draft.body,
                    created_run=run_id,
                    status='current',
                ),
                evidence,
            )
            concepts_written += 1

        claims_flagged += flag_candidates(ledger, output.patterns, run_id)

        batches += 1
        offset += batch_size

    return ReflectionSummary(
        concepts_written=concepts_written,
        concepts_discarded=concepts_discarded,
        claims_flagged=claims_flagged,
        batches=batches,
    )


def reflect_after_scan(settings: Settings) -> Callable[[Ledger, Run], None]:
    """Build an `after_scan(ledger, run)` callable, matching T-09's hook signature.

    `scan.run_scan` calls its `after_scan` hook synchronously
    (`Callable[[Ledger, Run], None]`), while `run_reflection` and `reflect`
    are async like every other generation-point caller in this codebase —
    so the callable this returns wraps one `asyncio.run` around the whole
    reflection pass, the same seam `Worker.survey`'s callers cross at
    `run_unit`. One `ReflectionAgent` is built once, at
    `reflect_after_scan` call time, and reused across every `after_scan`
    invocation the returned callable ever receives.
    """
    agent = make_reflection_agent(settings)

    def after_scan(ledger: Ledger, run: Run) -> None:
        asyncio.run(run_reflection(agent, ledger, run.id))

    return after_scan
