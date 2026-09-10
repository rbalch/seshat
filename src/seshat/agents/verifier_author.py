"""The verifier author: the second of the four model generation points.

Turns one claim about one unit into a `VerifierSpec` — Python source whose
`def check(graph)` re-checks the claim against the graph helper API, plus the
JSON result it expects. `VerifierAuthor.author` is a NOOA `Predict` generation
method (`nooa.Agent` + `@strategy(PredictStrategy())`): its docstring is the
prompt sent to the model, and its `...` body is the generation point itself —
see `nooa/ellipsis_detection.py` and AGENTS.md. This module never runs the
verifier it writes (T-05 does that) and never persists anything (T-08 does).

No CodeAct, no tools, no MCP: this role is one shot by design (decisions
Q27) — `author` makes exactly one call into the LLM (`PredictConfig(max_retries=1)`
below constrains NOOA's own validation-retry loop, which otherwise defaults to
10), with exactly one retry at the `author_with_retry` layer above it.
"""

from __future__ import annotations

import ast

from nooa import Agent
from nooa.config.strategy_config import PredictConfig
from nooa.decorators import strategy
from nooa.strategies import PredictStrategy
from pydantic import BaseModel, Field

from seshat.config import Settings
from seshat.ledger.models import Unit

# `PredictConfig.max_retries` counts total attempts, not additional retries: `1`
# means the validation-retry loop in nooa/strategies/predict.py runs exactly
# once (`range(1, max_retries + 1)`), so a malformed response raises straight
# from `author()` instead of NOOA silently re-prompting up to its default of
# 10 times. Verified by experiment against the installed nooa 0.0.10. This
# role is one shot by design (decisions Q27); `author_with_retry` below is
# where *our* one retry happens, not NOOA's.
_ONE_SHOT = PredictConfig(max_retries=1)


class VerifierAuthorError(Exception):
    """Raised by `author_with_retry` when two attempts both fail validation."""


class VerifierSpec(BaseModel):
    """One verifier, authored against one claim about one unit.

    `source` is Python defining `check(graph)`; `expected_json` is the JSON
    text of the value `check` should return when the claim holds;
    `depends_on` names the unit ids the check actually reads (for the
    dependency ordering in plan §2); `angle` is one line naming what the
    check looks at that the claim's own source did not (see AGENTS.md
    "Always: a check from a different angle").
    """

    source: str
    expected_json: str
    depends_on: list[str] = Field(default_factory=list)
    angle: str


def _has_check_entry_point(source: str) -> bool:
    """Whether `source` defines a top-level `def check(graph)` entry point.

    Parses `source` with `ast` rather than substring-matching `'def check('`
    — that bare substring check is defeated by e.g. a comment mentioning
    `def check(graph)` beside a differently-named function, which would
    sail the retry guard and only be caught later, and further away from
    its cause, by T-05's runner. Never imports `seshat.verify` for this —
    that module is the exec-bearing runner (DEC-2) and pulling it in here
    would drag its confined surface across the module boundary for the
    sake of this check.

    This predicate must agree with `_find_check_function` in
    `src/seshat/verify.py`, which is the authoritative one — it is the
    version that actually runs the source — copied here rather than
    imported for the DEC-2 reason above: a top-level `ast.FunctionDef`
    (never `ast.AsyncFunctionDef`; T-05 always rejects an async `check`)
    named `check` with a non-empty `args.args`. T-05 then calls it as
    `check(graph)`, so any further parameters must default or the call
    raises at run time — same as `_find_check_function`, this does not
    check for that separately, so `def check(graph, extra=1)` passes here
    exactly as it does in T-05.

    Fails closed: source that does not even parse (`SyntaxError`) is
    treated as missing the entry point, never as passing.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    return any(
        isinstance(node, ast.FunctionDef) and node.name == 'check' and bool(node.args.args) for node in tree.body
    )


class VerifierAuthor(Agent):
    """Writes one verifier for one claim about one unit of Python code."""

    @strategy(PredictStrategy(config=_ONE_SHOT))
    async def author(
        self,
        claim_text: str,
        unit: Unit,
        unit_source: str,
        neighbours: str,
    ) -> VerifierSpec:
        """Author one `VerifierSpec` for a single claim about a single unit.

        You are given the claim's text, the `Unit` it is about, that unit's
        own source (`unit_source` — likely where the claim came from), and a
        short rendering of its neighbours (callers/callees/subclasses,
        already read off the graph).

        ## The graph helper API

        The `check(graph)` function you write receives one argument,
        `graph`, an instance of `seshat.graph.Graph`. These are the only
        methods it has, with these exact signatures (plan.md §6):

            def node(self, qualified_name: str, file_path: str | None = None) -> Node | None
            def callers(self, qualified_name: str) -> list[Node]
            def callees(self, qualified_name: str) -> list[Node]
            def imports(self, file_path: str) -> list[str]          # resolved file->file edges
            def external_refs(self, qualified_name: str) -> list[str] # unresolved calls: stdlib, third-party
            def subclasses(self, qualified_name: str) -> list[Node]
            def decorators(self, qualified_name: str) -> list[str]
            def search(self, fts_query: str) -> list[Node]
            def files(self, glob: str) -> list[str]

        `Node` has `qualified_name`, `file_path`, `kind`, `start_line`,
        `end_line`. Nothing else reaches the graph: no filesystem access, no
        codegraph tables, no running the target's own code.

        ## The entry point

        `def check(graph)` is the required entry point. Your `source` must
        define a top-level function named exactly `check` taking one
        parameter `graph`, and returning the value the claim predicts. Only
        two imports are ever allowed in `source`: `json` and `re`. Anything
        else — `import os`, `__import__`, `open`, `eval`, `exec` — is
        rejected before your source is ever run (see `seshat.verify`).

        ## The angle requirement

        Your check must look at the code from a *different angle* than the
        claim's source. If the claim was derived from a function's own
        body, check its callers instead of re-reading the body; if it was
        derived from reading a class, check its subclasses instead of the
        class itself. A check that re-derives the claim from the same place
        it came from proves nothing — it will pass whether or not the claim
        is true.

        ## Worked example

        Claim: "`OrderRepository.get` is only ever called by
        `OrderService`." The claim was read from `OrderRepository.get`'s own
        body, so the check looks at its callers instead:

            def check(graph):
                return sorted(n.qualified_name for n in graph.callers('OrderRepository.get'))

        `expected_json` for that check: `["OrderService.place"]` — the JSON
        text the check's return value should match once canonicalized.

        ## What to return

        A `VerifierSpec`: `source` (the `check(graph)` function, following
        every rule above), `expected_json` (the JSON text the check should
        produce when the claim holds), `depends_on` (the ids of any units
        the check itself queries), and `angle` (one line naming the
        different angle you checked from).
        """
        ...


def make_verifier_author(settings: Settings) -> VerifierAuthor:
    """Build a `VerifierAuthor` wired to the `verifier_author` role's model."""
    from nooa.unifiedllm import CompletionClient

    llm = CompletionClient(**settings.llm_kwargs('verifier_author'))
    return VerifierAuthor(llm=llm)


async def author_with_retry(
    agent: VerifierAuthor,
    claim_text: str,
    unit: Unit,
    unit_source: str,
    neighbours: str,
    *,
    feedback: str | None = None,
) -> VerifierSpec:
    """One `author` call; on a bad result, one retry with the error appended.

    "Bad" means either pydantic validation failed (raised by the underlying
    `PredictStrategy`) or the returned `source` has no `def check(` entry
    point. A second failure raises `VerifierAuthorError` rather than
    retrying again — this role is one shot by design (decisions Q27).
    """
    claim_with_feedback = claim_text if feedback is None else f'{claim_text}\n\nPrevious attempt failed: {feedback}'

    try:
        result = await agent.author(claim_with_feedback, unit, unit_source, neighbours)
    except Exception as exc:  # any generation failure (validation, GenerationError) is retryable once
        if feedback is not None:
            raise VerifierAuthorError(f'verifier author failed twice: {exc}') from exc
        return await author_with_retry(
            agent,
            claim_text,
            unit,
            unit_source,
            neighbours,
            feedback=str(exc),
        )

    if not _has_check_entry_point(result.source):
        error = "source has no 'def check(' entry point"
        if feedback is not None:
            raise VerifierAuthorError(f'verifier author failed twice: {error}')
        return await author_with_retry(
            agent,
            claim_text,
            unit,
            unit_source,
            neighbours,
            feedback=error,
        )

    return result
