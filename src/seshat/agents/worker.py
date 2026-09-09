"""The worker: the first of the four model generation points (plan §5 step 6).

One worker turn on one unit: read the unit through the graph helper API and
working memory, conjecture 2-5 structural claims, hand each to the verifier
author (T-07) and T-05's `verify_and_record`, retry a failure once, and
persist only what a verifier actually passed. Working memory (`nooa-memory`,
`seshat.memory.WorkingMemory`) holds hypotheses and dead ends; the ledger
holds nothing that has not been checked — see AGENTS.md "Always"/"Never" and
tasks/seshat-phase-one/T-08-worker-agent.md.

`Worker.survey` is the one `CodeActStrategy` generation point in this module:
its docstring is the prompt, its `...` body is the generation call (see
`nooa/ellipsis_detection.py`). Every other method on `Worker` is a plain
Python method with a real body — CodeAct's `execute_python` tool lets the
model call them directly (`self.unit_brief()`, `self.propose_claim(...)`,
...) inside the code it writes; NOOA needs no separate registration for
that (AGENTS.md: "methods with bodies are tools for free").
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from nooa import Agent
from nooa.decorators import strategy
from nooa.runtime.middleware import LLMCallContext, LLMCallNext
from nooa.strategies import CodeActStrategy

from seshat.agents.verifier_author import VerifierAuthor, author_with_retry
from seshat.config import Settings
from seshat.graph import Graph, Node
from seshat.ledger.models import Claim, Unit, Verifier
from seshat.ledger.store import Ledger
from seshat.memory import WorkingMemory
from seshat.units import UnitReport
from seshat.verify import verify_and_record

if TYPE_CHECKING:
    from nooa.mcp import MCPTool

# The env var codegraph 1.6.0 reads to *replace* (never extend) its default
# tool list, which is `explore` alone — omitting it here means the model
# never sees `codegraph_explore` at all. Verified against the installed
# binary: these six surface; `files`, `status`, `all` do not (task scope
# item 2). `search` and `impact` are codegraph's own tool names for what
# `Graph.search` and inbound-call impact analysis cover on our side.
_CODEGRAPH_MCP_TOOLS = 'explore,node,callers,callees,search,impact'


@dataclass
class _TokenMeter:
    """Accumulates `total_tokens` off every `LLMResponse.usage` a worker's turn sees.

    This is genuinely "NOOA's own token accounting", not a Seshat invention:
    `usage` is the field `nooa.unifiedllm.LLMResponse` already carries on
    every response (real or `FakeLLMClient`-scripted). NOOA itself keeps no
    running total anywhere reachable from a plain `Agent` without the full
    Harbor tracing/harness-metrics plumbing (see `nooa.runtime.token_usage`,
    which needs a callback `FakeLLMClient` never fires) — so `run_unit`
    reads this meter instead of a hardcoded constant, and a hermetic test
    with a scripted `usage` dict makes that real: `tokens` tracks whatever
    the fake reported, never a literal.

    Fed by `Worker._track_tokens`, an `llm_call` middleware handler
    (`EventManager.intercept`, `nooa/runtime/middleware.py`) rather than by
    wrapping the LLM client itself. A first version of this wrapped
    `self.llm` in a duck-typed proxy so it could observe `.usage` on every
    response; that wrapping was itself the bug a code review caught:
    `nooa/runtime/actor.py`'s `_resolve_provider_formatter` does
    `isinstance(llm_client, ResponsesClient)` to pick the wire-format
    formatter for the Responses API, and a wrapped client is never an
    instance of the real class, so that check would go permanently `False`
    for any role ever pointed at a `ResponsesClient` — a silent wrong-wire-
    format send, not an exception. `llm_call` middleware wraps the *call*
    (`ctx.response` is set by the real, unwrapped client's own `acall`
    before this handler ever runs — see `ActorRuntime.generate` in
    `nooa/runtime/actor.py`), so `self.llm`/`self._llm` is always the exact
    object `set_llm` installed, and every `isinstance` check anywhere in the
    runtime keeps seeing it.
    """

    total: int = 0

    def add(self, usage: dict[str, int] | None) -> None:
        if usage:
            self.total += usage.get('total_tokens', 0)


def _read_span(repo_root: Path, node: Node) -> str:
    """The exact source lines `node` spans, or `''` if the file can't be read.

    Fails closed toward "cannot read this unit" rather than raising: a
    missing file is `OSError` (matches `seshat.units.ast_hash`'s own
    failure direction); a file that exists but is not UTF-8 raises
    `UnicodeDecodeError` from `read_text()` — this is a plain source-span
    read for a prompt, not a hash whose correctness matters, so both cases
    get the same empty-string fallback rather than crashing the worker's
    whole turn over one unreadable file.
    """
    try:
        lines = (repo_root / node.file_path).read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return ''
    return '\n'.join(lines[node.start_line - 1 : node.end_line])


class Worker(Agent):
    """You are Seshat's worker: you read one unit of a codebase you did not write and
    conjecture falsifiable claims about it, then verify each one before it counts.

    Call `unit_brief()` first — it gives you the unit's own source, callers, callees,
    decorators and external refs, already read off the code graph. Call `recall(query)`
    for anything relevant a previous unit's turn remembered. If `unit_brief()` and
    `recall()` are not enough, the codegraph MCP tools read the live index directly:
    call `codegraph_explore` first, then the narrower `codegraph_node` /
    `codegraph_callers` / `codegraph_callees` / `codegraph_search` / `codegraph_impact`
    only as needed.

    A claim is one falsifiable sentence about the unit — never a summary, never a
    paraphrase of a README line without checking it. `propose_claim(text, source)`
    stores it as `conjectured`; `verify_claim(claim_id)` is the only thing that can
    make it `confirmed` or `refuted` — nothing you say here reaches the ledger any
    other way. `remember(text, kind)` is for dead ends and structural notes that
    never became a claim; never store a claim's own text as a memory instead of
    verifying it.
    """

    def __init__(
        self,
        llm: Any,
        memory: WorkingMemory,
        ledger: Ledger,
        graph: Graph,
        run_id: str,
        verifier_agent: VerifierAuthor,
        *,
        author_with_retry_fn: Any = author_with_retry,
        codegraph: MCPTool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(llm=llm, **kwargs)
        self.memory = memory
        self.ledger = ledger
        self.graph = graph
        self.run_id = run_id
        self.verifier_agent = verifier_agent
        self._author_with_retry = author_with_retry_fn
        self.codegraph = codegraph
        self._unit: Unit | None = None
        self._claims: dict[str, Claim] = {}
        self._token_meter = _TokenMeter()
        # See `_TokenMeter`'s docstring: this observes the real, unwrapped
        # `self.llm` mid-call rather than replacing it, so every `isinstance`
        # check the runtime ever does on `self.llm`/`self._llm` (e.g.
        # `_resolve_provider_formatter`'s `ResponsesClient` check) keeps
        # seeing the exact object `set_llm` installed.
        self.event_manager.intercept('llm_call', self._track_tokens)

    async def _track_tokens(self, ctx: LLMCallContext, nxt: LLMCallNext) -> LLMCallContext:
        """`llm_call` middleware: run the real call, then meter its `usage`."""
        ctx = await nxt(ctx)
        if ctx.response is not None:
            self._token_meter.add(ctx.response.usage)
        return ctx

    @property
    def tokens_used(self) -> int:
        """Total `total_tokens` accumulated since the last `begin_unit` call."""
        return self._token_meter.total

    # -- unit context ----------------------------------------------------

    def begin_unit(self, unit: Unit) -> None:
        """Set the unit this turn's tools operate on; clear the claim cache and token meter.

        Called by `run_unit` before `survey`; a test can call it directly to
        exercise `propose_claim`/`verify_claim` without driving a full
        CodeAct turn through the model. The token meter resets here too, so
        `tokens_used` after a turn reflects only that turn's calls, not every
        turn this `Worker` has ever run.
        """
        self._unit = unit
        self._claims = {}
        self._token_meter = _TokenMeter()

    def _require_unit(self) -> Unit:
        if self._unit is None:
            raise RuntimeError('no unit set: call begin_unit(unit) first')
        return self._unit

    # -- tools (plain methods; CodeAct calls these directly) -------------

    def unit_brief(self) -> str:
        """The current unit's own source, callers, callees, decorators and external refs."""
        unit = self._require_unit()
        node = self.graph.node(unit.qualified_name, unit.file_path)
        source = _read_span(self.graph.repo_root, node) if node is not None else ''
        callers = [n.qualified_name for n in self.graph.callers(unit.qualified_name)]
        callees = [n.qualified_name for n in self.graph.callees(unit.qualified_name)]
        decorators = self.graph.decorators(unit.qualified_name)
        external_refs = self.graph.external_refs(unit.qualified_name)
        return (
            f'{unit.qualified_name} ({unit.kind}) at {unit.file_path}:{unit.start_line}-{unit.end_line}\n\n'
            f'{source}\n\n'
            f'callers: {callers}\n'
            f'callees: {callees}\n'
            f'decorators: {decorators}\n'
            f'external_refs: {external_refs}\n'
        )

    def recall(self, query: str) -> list[str]:
        """Recall relevant working memory (see `WorkingMemory.recall`)."""
        return self.memory.recall(query)

    def remember(self, text: str, kind: str = 'scratch') -> None:
        """Remember `text` (a dead end or a structural note) in working memory."""
        self.memory.remember(text, kind)

    def propose_claim(self, text: str, source: Literal['code', 'readme', 'docstring']) -> str:
        """Store `text` as a `conjectured` claim about the current unit; return its id."""
        unit = self._require_unit()
        claim = Claim(
            id='',
            repo_id='',
            unit_id=unit.id,
            text=text,
            kind='structural',
            source=source,
            mode='claims',
            status='conjectured',
            confidence=0.5,
            candidate_rule=0,
            rule_sightings=0,
            created_run=self.run_id,
            verified_run=None,
            verified_sha=None,
            retries=0,
        )
        stored = self.ledger.add_claim(claim)
        self._claims[stored.id] = stored
        return stored.id

    async def verify_claim(self, claim_id: str) -> dict:
        """Author a verifier for `claim_id`, run it, retry once on failure.

        `pass` on the first attempt -> `confirmed`, `verified_sha` set to
        the unit's current `ast_hash`, `retries=0`. `fail`/`error` -> one
        more author call with the failure shown as feedback, rerun; a
        second failure -> `refuted`, `retries=1`. Returns
        `{'status': ..., 'reason': ...}`.
        """
        unit = self._require_unit()
        claim = self._claims[claim_id]
        unit_source = _brief_source(self, unit)
        neighbours = _brief_neighbours(self, unit)

        spec = await self._author_with_retry(self.verifier_agent, claim.text, unit, unit_source, neighbours)
        verifier = self.ledger.add_verifier(
            Verifier(
                id='',
                repo_id='',
                claim_id=claim.id,
                source=spec.source,
                expected=spec.expected_json,
                depends_on=list(spec.depends_on),
            )
        )
        result = verify_and_record(self.ledger, verifier, self.graph, self.run_id)
        if result.status == 'pass':
            updated = self.ledger.set_claim_status(
                claim.id, 'confirmed', self.run_id, verified_sha=unit.ast_hash, retries=0
            )
            self._claims[claim.id] = updated
            return {'status': 'confirmed', 'reason': None}

        feedback = result.error or f'expected {verifier.expected!r}, got {result.actual!r}'
        spec2 = await self._author_with_retry(
            self.verifier_agent, claim.text, unit, unit_source, neighbours, feedback=feedback
        )
        verifier2 = self.ledger.add_verifier(
            Verifier(
                id='',
                repo_id='',
                claim_id=claim.id,
                source=spec2.source,
                expected=spec2.expected_json,
                depends_on=list(spec2.depends_on),
            )
        )
        result2 = verify_and_record(self.ledger, verifier2, self.graph, self.run_id)
        if result2.status == 'pass':
            updated = self.ledger.set_claim_status(
                claim.id, 'confirmed', self.run_id, verified_sha=unit.ast_hash, retries=1
            )
            self._claims[claim.id] = updated
            return {'status': 'confirmed', 'reason': None}

        updated = self.ledger.set_claim_status(claim.id, 'refuted', self.run_id, retries=1)
        self._claims[claim.id] = updated
        reason = result2.error or 'verifier failed twice'
        return {'status': 'refuted', 'reason': reason}

    # -- generation point -------------------------------------------------

    @strategy(CodeActStrategy())
    async def survey(self, unit: Unit) -> UnitReport:
        """Survey `unit` (already set via `begin_unit`; also passed here for the prompt).

        1. Call `unit_brief()` to read the unit's own source, callers, callees,
           decorators and external refs.
        2. Call `recall(query)` for anything a previous unit's turn remembered
           that bears on this one.
        3. Conjecture 2-5 structural claims about the unit and store each with
           `propose_claim(text, source)` — `source` is `'code'` for something
           read straight from the unit's own body, `'docstring'` for something
           read from its docstring, `'readme'` only for a statement recalled
           from a doc seed (never invent a `'readme'` claim from nothing).
        4. Call `verify_claim(claim_id)` on every claim you proposed, in any
           order.
        5. `remember(text, kind)` any dead end: a claim that got refuted, or a
           structural fact you noticed but could not turn into a falsifiable
           claim. Never `remember` a claim's own text instead of verifying it.
        6. Return `UnitReport(claims_confirmed, claims_refuted, notes)`: the
           confirmed claim ids, the refuted claim ids, and your own notes —
           never claim text, never a summary paragraph.

        If `unit_brief()` and `recall()` genuinely are not enough, the
        codegraph MCP tools read the live `.codegraph` index directly: call
        `codegraph_explore` first, then the narrower `codegraph_node` /
        `codegraph_callers` / `codegraph_callees` / `codegraph_search` /
        `codegraph_impact` tools.
        """
        ...


def _brief_source(worker: Worker, unit: Unit) -> str:
    """The unit's own source text, read the same way `unit_brief` does."""
    node = worker.graph.node(unit.qualified_name, unit.file_path)
    return _read_span(worker.graph.repo_root, node) if node is not None else ''


def _brief_neighbours(worker: Worker, unit: Unit) -> str:
    """A short rendering of the unit's callers/callees, for the verifier author's prompt."""
    callers = [n.qualified_name for n in worker.graph.callers(unit.qualified_name)]
    callees = [n.qualified_name for n in worker.graph.callees(unit.qualified_name)]
    return f'callers: {callers}; callees: {callees}'


async def attach_codegraph(repo: Path) -> MCPTool:
    """Connect the codegraph MCP server (`codegraph serve --mcp --no-watch`) rooted at `repo`.

    Not exercised by the hermetic acceptance suite — same shape as T-07's
    `make_verifier_author`, which also only matters for a live run. Uses
    `MCPManager.create_stdio_server` (which builds an `MCPStdioClient`
    internally) rather than `MCPManager.create_from_server` + a `.mcp.json`,
    because there is no config file here — see task scope item 2 and
    `nooa/mcp/tool.py`'s `create_stdio_server` docstring on why it, not the
    sync `create_from_server`, is the one to await from inside an already-
    running event loop.

    `env` starts from the current process environment (not a bare override)
    so the spawned `codegraph` binary still resolves on `PATH` — passing a
    bare dict as a subprocess `env` replaces the whole environment, it does
    not merge with it.
    """
    from nooa.mcp import MCPManager

    env = {
        **os.environ,
        'CODEGRAPH_TELEMETRY': '0',
        'CODEGRAPH_MCP_TOOLS': _CODEGRAPH_MCP_TOOLS,
    }
    return await MCPManager.create_stdio_server(
        'codegraph',
        command='codegraph',
        args=['serve', '--mcp', '--no-watch', '--path', str(repo)],
        env=env,
    )


async def run_unit(worker: Worker, unit: Unit, ledger: Ledger, graph: Graph, run_id: str) -> UnitReport:
    """One worker turn on `unit`: `survey`, then mark it `scanned`.

    Wires `worker` to `ledger`/`graph`/`run_id` for this call (a worker turns
    over many units across a run) and returns `survey`'s `UnitReport` with
    `tokens` filled in from `worker.tokens_used` — NOOA's own token
    accounting on the LLM responses this turn actually made, not a constant.
    """
    worker.ledger = ledger
    worker.graph = graph
    worker.run_id = run_id
    worker.begin_unit(unit)

    report = await worker.survey(unit)

    ledger.set_unit_status(unit.id, 'scanned', run_id)

    return replace(report, tokens=worker.tokens_used)


def make_worker(
    settings: Settings,
    memory: WorkingMemory,
    ledger: Ledger,
    graph: Graph,
    run_id: str,
    verifier_agent: VerifierAuthor,
    *,
    codegraph: MCPTool | None = None,
) -> Worker:
    """Build a `Worker` wired to the `worker` role's model."""
    from nooa.unifiedllm import CompletionClient

    llm = CompletionClient(**settings.llm_kwargs('worker'))
    return Worker(llm, memory, ledger, graph, run_id, verifier_agent, codegraph=codegraph)
