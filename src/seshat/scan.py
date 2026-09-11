"""The scan orchestrator: plan.md §5 steps 1-7 and 10, end to end, in plain Python.

`run_scan` indexes the target, opens the ledger and graph, seeds working memory,
syncs units against the ledger and reruns the verifiers that touch anything that
moved, builds the work queue, drives a small `asyncio.gather` worker pool over
it under a units/minutes/tokens budget, calls the `after_scan` hook (T-10 plugs
reflection in there), and closes the run. No model is imported here — the one
`Worker` generation point comes in through `worker_factory`, already built by
the caller. See AGENTS.md ("if a model creeps into the orchestration, the run
stops being measurable") and tasks/seshat-phase-one/T-09-scan-orchestrator.md.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from nooa.tracing import set_session

from seshat.config import Settings
from seshat.graph import Graph
from seshat.ledger.models import Run
from seshat.ledger.store import Ledger
from seshat.memory import open_working_memory, seed_docs
from seshat.units import build_queue, enumerate_units, sync_units, verifiers_to_rerun
from seshat.verify import verify_and_record

__all__ = ['IndexFailed', 'Run', 'ScanOptions', 'run_scan']


class IndexFailed(Exception):
    """Raised when `codegraph init`/`codegraph sync` exits non-zero."""


@dataclass(frozen=True)
class ScanOptions:
    """What one `run_scan` call is asked to do, and its budgets.

    `thinking` is a plain `bool` here; `runs.thinking` is an `INTEGER` column
    and `Ledger.create_run(thinking: int = 0, ...)` expects an `int` — this
    module is the one place that converts, at the `create_run` call site.
    """

    units: int = 5
    minutes: float = 10
    tokens: int = 200_000
    workers: int = 1
    thinking: bool = True
    full: bool = False
    model: str | None = None


def _default_indexer(repo: Path) -> None:
    """Run `codegraph init` (first time) or `codegraph sync` (already indexed).

    Raises `IndexFailed` with the process's stderr on a non-zero exit.
    """
    already_indexed = (repo / '.codegraph').exists()
    command = ['codegraph', 'sync'] if already_indexed else ['codegraph', 'init']
    env = {**os.environ, 'CODEGRAPH_TELEMETRY': '0'}
    result = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise IndexFailed(f'{" ".join(command)} exited {result.returncode}: {result.stderr}')


def _commit_sha(repo: Path) -> str:
    """`git rev-parse HEAD` at `repo`, or `'nogit'` when that fails (no repo, no commits)."""
    try:
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=False)
    except OSError:
        return 'nogit'
    if result.returncode != 0:
        return 'nogit'
    return result.stdout.strip() or 'nogit'


@dataclass
class _Stats:
    """Mutable counters accumulated across the worker pool, guarded by `_drive_pool`'s `lock`."""

    units_done: int = 0
    claims_confirmed: int = 0
    claims_refuted: int = 0
    tokens_used: int = 0


def _status_line(
    done: int,
    queued: int,
    qualified_name: str,
    confirmed: int,
    refuted: int,
    tokens: int,
    unreadable: int,
    elapsed: float,
) -> str:
    return (
        f'[{done}/{queued}] {qualified_name} +{confirmed} -{refuted} '
        f'tokens={tokens} unreadable={unreadable} elapsed={elapsed:.1f}s'
    )


# Cap on how many unreadable files one line names before falling back to "and
# N more" -- three is enough to point a human at the worst-hit files without
# turning a run over a large mixed-encoding repo into a wall of filenames
# (T-15 scope item 3: a count alone says something is wrong, not where to
# look, but a line of noise on every scan is how a count stops being read).
_UNREADABLE_NAME_CAP = 3


def _unreadable_names_line(ledger: Ledger, unreadable_unit_ids: list[str]) -> str | None:
    """A line naming up to `_UNREADABLE_NAME_CAP` unreadable files, or `None` when there are none.

    One file can produce more than one unreadable unit (its module, any
    class, any function/method all fail `ast_hash` together), so this
    resolves ids to `file_path` and de-duplicates before applying the cap --
    a human wants to know which *files* to look at, not how many AST nodes
    each one used to have.
    """
    if not unreadable_unit_ids:
        return None
    names: list[str] = []
    for unit_id in unreadable_unit_ids:
        unit = ledger.unit(unit_id)
        name = unit.file_path if unit is not None else unit_id
        if name not in names:
            names.append(name)
    shown = names[:_UNREADABLE_NAME_CAP]
    remainder = len(names) - len(shown)
    line = f'unreadable ({len(names)}): {", ".join(shown)}'
    if remainder > 0:
        line += f' and {remainder} more'
    return line


def run_scan(
    repo: Path,
    options: ScanOptions,
    settings: Settings,
    *,
    worker_factory: Callable[[], Any],
    after_scan: Callable[[Ledger, Run], None] | None = None,
    indexer: Callable[[Path], None] = _default_indexer,
) -> Run:
    """Index, run row, seeds, unit sync, queue, worker pool, budget, close.

    `worker_factory()` returns one fresh worker instance per unit (the
    CyberGym pattern); scan.py drives it through the module-level free
    function `seshat.agents.worker.run_unit` — a `Worker` has no `run_unit`
    method of its own. Steps are numbered per the task's Scope section.
    """
    repo = Path(repo).resolve()
    started_at = time.monotonic()

    # 1. index
    indexer(repo)

    # 2. ledger, graph, run row
    ledger = Ledger.open(repo)
    graph = Graph.open(repo)
    run = ledger.create_run(
        commit_sha=_commit_sha(repo),
        model=options.model,
        thinking=int(options.thinking),
        workers=options.workers,
        budget_units=options.units,
        budget_minutes=int(options.minutes),
        budget_tokens=options.tokens,
        status='running',
        mode='claims',
    )
    set_session(run.id)

    # Declared before the try so the except block below always has real
    # counters to report, however early the failure happens — `queue` empty
    # and `stats` all-zero is then the honest answer, not a hardcoded one.
    # `unreadable_count` follows the same rule (T-15): it stays 0 until
    # `sync_units` actually reports one, so a crash before that point reports
    # zero unreadable honestly rather than a stale or guessed count.
    queue: list = []
    stats = _Stats()
    unreadable_count = 0

    try:
        # 3. seed docs into working memory
        memory = open_working_memory(repo)
        seed_names = set(seed_docs(memory, repo))

        # 4. enumerate + sync units, rerun the verifiers that touch what moved
        units = enumerate_units(graph, repo)
        diff = sync_units(ledger, units, run.id)
        unreadable_count = len(diff.unreadable)
        naming_line = _unreadable_names_line(ledger, diff.unreadable)
        if naming_line is not None:
            print(naming_line)
        for verifier in verifiers_to_rerun(ledger, diff, full=options.full):
            verify_and_record(ledger, verifier, graph, run.id)

        # 5. queue
        queue = build_queue(ledger, seed_names)

        # 6-7. worker pool, driven under budget. `stats` is mutated in place
        # by `_drive_pool`/`worker_loop` as each unit finishes, so it still
        # holds real, as-of-the-crash counters if a unit raises partway
        # through the pool run and this `except` catches it below.
        final_status = _drive_pool(
            queue, options, worker_factory, ledger, graph, run, stats, started_at, unreadable_count
        )
    except BaseException as exc:
        # Deliberately no `after_scan` call here: reflection (T-10) runs over
        # a completed scan's claims, and a run that crashed mid-pool has no
        # such thing to reflect on. Do not "helpfully" move this into a
        # `finally` — that would hand T-10 a run with an undefined amount of
        # work done and no way to tell that apart from a real completion.
        elapsed = time.monotonic() - started_at
        print(
            _status_line(
                stats.units_done,
                len(queue),
                repo.name,
                stats.claims_confirmed,
                stats.claims_refuted,
                stats.tokens_used,
                unreadable_count,
                elapsed,
            )
            + f' error={exc}'
        )
        ledger.close_run(run.id, 'failed')
        graph.close()
        ledger.close()
        raise

    run = ledger.update_run(
        run.id,
        units_done=stats.units_done,
        claims_confirmed=stats.claims_confirmed,
        claims_refuted=stats.claims_refuted,
        tokens_used=stats.tokens_used,
    )

    # 8. reflection hook
    if after_scan is not None:
        after_scan(ledger, replace(run, status=final_status))

    # 9. close
    run = ledger.close_run(run.id, final_status)

    graph.close()
    ledger.close()

    return run


def _drive_pool(
    queue: list,
    options: ScanOptions,
    worker_factory: Callable[[], Any],
    ledger: Ledger,
    graph: Graph,
    run: Run,
    stats: _Stats,
    started_at: float,
    unreadable_count: int,
) -> str:
    """Run `options.workers` coroutines over `queue`, one `worker_factory()` per unit.

    `stats` is the caller's own counters object, mutated in place as each
    unit finishes — so `run_scan`'s except block still sees real,
    as-of-the-crash numbers if a unit raises and this function never
    returns. `started_at` is the caller's scan-start clock reading, not a
    fresh one taken here, for the same reason: the failure status line's
    elapsed time has to be elapsed-since-the-scan-began, not
    elapsed-since-the-pool-started.

    Returns the status the run should end in: `'stopped_budget'` (units,
    minutes or tokens, whichever is hit first), or `'stopped_complete'` when
    the queue drains with no budget hit. An unhandled exception from a unit
    propagates straight out of `asyncio.gather` (and this function) to
    `run_scan`'s caller.
    """
    from seshat.agents.worker import run_unit

    # Not load-bearing today: every critical section below awaits nothing,
    # so under this module's cooperative, no-threads model nothing can
    # interleave inside one regardless of the lock. It stays anyway — the
    # moment either section gains an `await` (a slower `ledger.update_run`,
    # an added `await` in the print/accounting block, ...), two workers can
    # interleave there and lose an update. Proven, not hypothetical: forcing
    # a yield point inside the section without this lock reproduces exactly
    # that (21 counted where 11 was correct).
    lock = asyncio.Lock()
    index = 0
    stop_reason: list[str | None] = [None]
    queued = len(queue)

    def _budget_exhausted() -> bool:
        if stats.units_done >= options.units:
            return True
        if (time.monotonic() - started_at) / 60.0 >= options.minutes:
            return True
        return stats.tokens_used >= options.tokens

    async def worker_loop() -> None:
        nonlocal index
        while True:
            async with lock:
                if stop_reason[0] is not None:
                    return
                if index >= len(queue):
                    return
                if _budget_exhausted():
                    stop_reason[0] = 'stopped_budget'
                    return
                unit = queue[index]
                index += 1

            worker = worker_factory()
            report = await run_unit(worker, unit, ledger, graph, run.id)

            async with lock:
                stats.units_done += 1
                stats.claims_confirmed += len(report.claims_confirmed)
                stats.claims_refuted += len(report.claims_refuted)
                stats.tokens_used += report.tokens
                elapsed = time.monotonic() - started_at
                print(
                    _status_line(
                        stats.units_done,
                        queued,
                        unit.qualified_name,
                        len(report.claims_confirmed),
                        len(report.claims_refuted),
                        stats.tokens_used,
                        unreadable_count,
                        elapsed,
                    )
                )
                ledger.update_run(
                    run.id,
                    units_done=stats.units_done,
                    claims_confirmed=stats.claims_confirmed,
                    claims_refuted=stats.claims_refuted,
                    tokens_used=stats.tokens_used,
                )
                if _budget_exhausted():
                    stop_reason[0] = 'stopped_budget'

    asyncio.run(_gather_workers(worker_loop, max(1, options.workers)))

    return stop_reason[0] or 'stopped_complete'


async def _gather_workers(worker_loop: Callable[[], Any], workers: int) -> None:
    await asyncio.gather(*(worker_loop() for _ in range(workers)))
