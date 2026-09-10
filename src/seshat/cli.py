"""seshat console script (plan.md §7, minus `ask` — T-12 fills that in).

Six subcommands: `scan` runs T-09's `run_scan` with the real worker factory
and T-10's reflection hook; `status`, `units`, `claims`, `concept`, `drift`
read the ledger through `Ledger`'s typed methods and print it — no SQL here,
see `seshat/ledger/store.py` and AGENTS.md. `argparse` only; no rich/click/
typer.

`worker_factory`, `reflect_after_scan` and `indexer` are module-level names
(scope item 1 of tasks/seshat-phase-one/T-11-readonly-cli.md) precisely so a
test can `monkeypatch.setattr(cli, 'worker_factory', ...)` /
`monkeypatch.setattr(cli, 'reflect_after_scan', ...)` /
`monkeypatch.setattr(cli, 'indexer', ...)` and drive `scan` through a stub
worker, a `FakeLLMClient`-backed reflection pass, and a no-op indexer, with
no model, no network, and no `codegraph` subprocess — `main(argv)` itself
stays argv-only, with no test-only parameter. `indexer` defaults to
`seshat.scan`'s own real indexer (`codegraph init`/`codegraph sync`), so an
unpatched `seshat scan` still indexes for real; only a test patches it away.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from seshat.agents.reflection import reflect_after_scan
from seshat.config import ConfigError, Settings
from seshat.graph import Graph
from seshat.ledger.models import Citation, Claim, Concept
from seshat.ledger.store import Ledger
from seshat.render import format_citation
from seshat.scan import IndexFailed, ScanOptions, run_scan
from seshat.scan import _default_indexer as indexer

__all__ = ['build_parser', 'indexer', 'main', 'reflect_after_scan', 'worker_factory']


# -- the worker factory: module-level so a test can patch it ----------------


def worker_factory(repo: Path, settings: Settings) -> Callable[[], Any]:
    """Build a zero-arg factory that hands back one fresh `Worker` per unit.

    Memory and the verifier author are built once, here, and shared across
    every unit's worker — `ledger`, `graph` and `run_id` are placeholders on
    construction because `seshat.agents.worker.run_unit` overwrites all
    three on every call before `survey` ever runs (see that module: `worker.
    ledger = ledger; worker.graph = graph; worker.run_id = run_id`).
    """
    from nooa.unifiedllm import CompletionClient

    from seshat.agents.verifier_author import make_verifier_author
    from seshat.agents.worker import Worker
    from seshat.memory import open_working_memory

    memory = open_working_memory(repo)
    verifier_agent = make_verifier_author(settings)
    llm = CompletionClient(**settings.llm_kwargs('worker'))

    # `run_unit` (seshat.agents.worker) overwrites `.ledger`/`.graph`/`.run_id`
    # on every call before `survey` runs, so these three constructor
    # arguments are placeholders, never read before being replaced; `cast`
    # says that honestly instead of a bare type-ignore comment.
    placeholder_ledger = cast(Ledger, None)
    placeholder_graph = cast(Graph, None)

    def factory() -> Worker:
        return Worker(
            llm, memory, ledger=placeholder_ledger, graph=placeholder_graph, run_id='', verifier_agent=verifier_agent
        )

    return factory


# -- argument parsing ---------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='seshat',
        description='seshat: a ledger of verified claims about a codebase.',
    )
    subparsers = parser.add_subparsers(dest='command', metavar='{scan,status,units,claims,concept,drift}')

    scan_parser = subparsers.add_parser('scan', help='scan a repo and grow its ledger')
    scan_parser.add_argument('repo')
    scan_parser.add_argument('--units', type=int, default=5)
    scan_parser.add_argument('--minutes', type=float, default=10)
    scan_parser.add_argument('--tokens', type=int, default=200_000)
    scan_parser.add_argument('--workers', type=int, default=1)
    scan_parser.add_argument('--no-thinking', action='store_true')
    scan_parser.add_argument('--full', action='store_true')
    scan_parser.add_argument('--model', default=None)

    status_parser = subparsers.add_parser('status', help="print the repo's last run")
    status_parser.add_argument('repo')

    units_parser = subparsers.add_parser('units', help='list every unit in the ledger')
    units_parser.add_argument('repo')
    units_parser.add_argument('--changed', action='store_true', help='only units with status changed|vanished')

    claims_parser = subparsers.add_parser('claims', help="list one unit's claims")
    claims_parser.add_argument('repo')
    claims_parser.add_argument('qualified_name')

    concept_parser = subparsers.add_parser('concept', help='print one concept and its evidence')
    concept_parser.add_argument('repo')
    concept_parser.add_argument('id_or_query')

    subparsers.add_parser('drift', help='print stale claims and concepts, grouped by unit').add_argument('repo')

    return parser


# -- scan ---------------------------------------------------------------------


def _cmd_scan(args: argparse.Namespace) -> int:
    repo = Path(args.repo)

    try:
        settings = Settings.load()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    options = ScanOptions(
        units=args.units,
        minutes=args.minutes,
        tokens=args.tokens,
        workers=args.workers,
        thinking=not args.no_thinking,
        full=args.full,
        model=args.model,
    )

    factory = worker_factory(repo, settings)
    after_scan = reflect_after_scan(settings)

    try:
        run = run_scan(repo, options, settings, worker_factory=factory, after_scan=after_scan, indexer=indexer)
    except IndexFailed as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 -- a worker's own failure is not this CLI's to type-narrow
        print(f'scan failed: {exc}', file=sys.stderr)
        return 1

    print(
        f'run {run.id}: {run.status} units_done={run.units_done} '
        f'confirmed={run.claims_confirmed} refuted={run.claims_refuted} tokens={run.tokens_used}'
    )
    return 0 if run.status.startswith('stopped_') else 1


# -- read-only commands ---------------------------------------------------


def _cmd_status(ledger: Ledger) -> int:
    run = ledger.last_run()
    if run is None:
        print('No runs yet.')
        return 0
    print(f'id: {run.id}')
    print(f'status: {run.status}')
    print(f'commit_sha: {run.commit_sha}')
    print(f'started_at: {run.started_at}')
    print(f'finished_at: {run.finished_at}')
    print(f'model: {run.model}')
    print(f'thinking: {run.thinking}')
    print(f'workers: {run.workers}')
    print(f'budget_units: {run.budget_units}')
    print(f'budget_minutes: {run.budget_minutes}')
    print(f'budget_tokens: {run.budget_tokens}')
    print(f'units_done: {run.units_done}')
    print(f'claims_confirmed: {run.claims_confirmed}')
    print(f'claims_refuted: {run.claims_refuted}')
    print(f'tokens_used: {run.tokens_used}')
    print(f'mode: {run.mode}')
    return 0


def _claim_counts(ledger: Ledger, unit_id: str) -> tuple[int, int, int]:
    claims = ledger.claims_for_unit(unit_id)
    confirmed = sum(1 for c in claims if c.status == 'confirmed')
    refuted = sum(1 for c in claims if c.status == 'refuted')
    stale = sum(1 for c in claims if c.status == 'stale')
    return confirmed, refuted, stale


def _cmd_units(ledger: Ledger, changed_only: bool) -> int:
    units = ledger.units()
    if changed_only:
        units = [u for u in units if u.status in ('changed', 'vanished')]
    for unit in units:
        confirmed, refuted, stale = _claim_counts(ledger, unit.id)
        print(
            f'{unit.qualified_name}\t{unit.file_path}\t{unit.status}\t'
            f'confirmed={confirmed} refuted={refuted} stale={stale}'
        )
    return 0


def _claim_line(ledger: Ledger, claim: Claim) -> str:
    """The short form: `[{status}] {text}  — {citation}`. Used by `drift` and `concept`."""
    citation: Citation = ledger.citation(claim.id)
    return f'[{claim.status}] {claim.text}  — {format_citation(citation)}'


def _claim_detail_line(ledger: Ledger, claim: Claim) -> str:
    """The `claims` command's per-claim form: `[{status}] {claim_id} {text}  — {citation}`.

    `claims` is the per-claim detail view, so it is the one place the claim
    id itself is printed — AGENTS.md's Always list requires a citation to
    carry the claim id; `drift`'s grouped lines and `concept`'s evidence list
    stay in the shorter `_claim_line` form (scope item 4).
    """
    citation: Citation = ledger.citation(claim.id)
    return f'[{claim.status}] {claim.id} {claim.text}  — {format_citation(citation)}'


def _cmd_claims(ledger: Ledger, qualified_name: str) -> int:
    matches = [u for u in ledger.units() if u.qualified_name == qualified_name]
    if not matches:
        print(f'No unit named {qualified_name!r}', file=sys.stderr)
        return 1
    unit = matches[0]
    for claim in ledger.claims_for_unit(unit.id):
        print(_claim_detail_line(ledger, claim))
    return 0


def _cmd_concept(ledger: Ledger, id_or_query: str) -> int:
    concept = ledger.concept(id_or_query)
    if concept is None:
        hits = ledger.search_concepts(id_or_query, limit=1)
        concept = hits[0] if hits else None
    if concept is None:
        print(f'No concept found for {id_or_query!r}', file=sys.stderr)
        return 1

    print(concept.title)
    print(concept.body)
    print('Evidence:')
    for claim_id in ledger.concept_evidence(concept.id):
        citation = ledger.citation(claim_id)
        print(f'  {format_citation(citation)}')
    return 0


def _cmd_drift(ledger: Ledger) -> int:
    report = ledger.stale_report()
    stale_claims = cast(list[Claim], report['claims'])
    stale_concepts = cast(list[Concept], report['concepts'])

    if not stale_claims and not stale_concepts:
        print('No drift.')
        return 0

    by_unit: dict[str, list[Claim]] = {}
    for claim in stale_claims:
        by_unit.setdefault(claim.unit_id, []).append(claim)

    for unit_id, claims in by_unit.items():
        unit = ledger.unit(unit_id)
        heading = unit.qualified_name if unit is not None else unit_id
        print(f'{heading}:')
        for claim in claims:
            print(f'  {_claim_line(ledger, claim)}')

    if stale_concepts:
        print('concepts:')
        for concept in stale_concepts:
            print(f'  [{concept.status}] {concept.title}')

    return 0


# -- dispatch -------------------------------------------------------------


def _ledger_db_path(repo: Path) -> Path:
    return repo / '.seshat' / 'ledger.db'


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == 'scan':
        return _cmd_scan(args)

    repo = Path(args.repo)
    db_path = _ledger_db_path(repo)
    if not db_path.exists():
        print(f'No ledger at {db_path}; run seshat scan', file=sys.stderr)
        return 2

    with Ledger.open(repo) as ledger:
        if args.command == 'status':
            return _cmd_status(ledger)
        if args.command == 'units':
            return _cmd_units(ledger, args.changed)
        if args.command == 'claims':
            return _cmd_claims(ledger, args.qualified_name)
        if args.command == 'concept':
            return _cmd_concept(ledger, args.id_or_query)
        if args.command == 'drift':
            return _cmd_drift(ledger)

    parser.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
