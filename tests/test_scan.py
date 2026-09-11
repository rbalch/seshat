"""Acceptance tests for T-09 — the scan orchestrator.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-09-scan-orchestrator.md. Committed alone, before any
implementation exists, per the project's red-then-green contract.

Hermetic: `indexer` is stubbed to a no-op (the fixture copy already has a
`.codegraph/`), and `worker_factory` returns a `StubWorker` — driven through
the real `seshat.agents.worker.run_unit` — that writes one confirmed and one
refuted claim, persists one `Verifier` row with `depends_on=[unit.id]`, and
reports a fixed token count. No model, no network, no nooa.Agent anywhere in
this file.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import seshat.scan as scan_mod
from seshat.config import Settings
from seshat.graph import Graph
from seshat.ledger.models import Claim, Unit, Verifier
from seshat.ledger.store import Ledger
from seshat.scan import IndexFailed, Run, ScanOptions, run_scan
from seshat.units import UnitReport
from seshat.verify import VerifierResult

# -- shared fixtures ----------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, fixture_target: Path) -> Path:
    dest = tmp_path / 'target'
    shutil.copytree(fixture_target, dest)
    return dest


@pytest.fixture
def settings() -> Settings:
    return Settings.load({'LLM_HOST': 'http://example.invalid'})


def _noop_indexer(repo: Path) -> None:
    return None


class StubWorker:
    """A worker double driven through the real `run_unit`.

    Every `survey()` call writes one confirmed claim, one refuted claim, and
    one `Verifier` row with `depends_on=[unit.id]` directly through the
    ledger — it plays the part `verify_claim`/`propose_claim` normally play,
    without a model in sight. `tokens_used` is fixed so counters are
    predictable.
    """

    FIXED_TOKENS = 17

    def __init__(self) -> None:
        self.ledger: Ledger | None = None
        self.graph = None
        self.run_id: str | None = None
        self._unit = None

    def begin_unit(self, unit) -> None:
        self._unit = unit

    @property
    def tokens_used(self) -> int:
        return self.FIXED_TOKENS

    async def survey(self, unit) -> UnitReport:
        assert self.ledger is not None
        assert self.run_id is not None
        confirmed = self.ledger.add_claim(
            Claim(
                id='',
                repo_id='',
                unit_id=unit.id,
                text=f'{unit.qualified_name} does something confirmed',
                kind='structural',
                source='code',
                mode='claims',
                status='conjectured',
                confidence=0.9,
                candidate_rule=0,
                rule_sightings=0,
                created_run=self.run_id,
                verified_run=None,
                verified_sha=None,
                retries=0,
            )
        )
        self.ledger.set_claim_status(confirmed.id, 'confirmed', self.run_id, verified_sha=unit.ast_hash)

        refuted = self.ledger.add_claim(
            Claim(
                id='',
                repo_id='',
                unit_id=unit.id,
                text=f'{unit.qualified_name} does something refuted',
                kind='structural',
                source='code',
                mode='claims',
                status='conjectured',
                confidence=0.1,
                candidate_rule=0,
                rule_sightings=0,
                created_run=self.run_id,
                verified_run=None,
                verified_sha=None,
                retries=0,
            )
        )
        self.ledger.set_claim_status(refuted.id, 'refuted', self.run_id)

        self.ledger.add_verifier(
            Verifier(
                id='',
                repo_id='',
                claim_id=confirmed.id,
                source='def check(graph):\n    return True\n',
                expected='true',
                depends_on=[unit.id],
            )
        )

        return UnitReport(claims_confirmed=[confirmed.id], claims_refuted=[refuted.id], notes=[], tokens=0)


class RaisingWorker(StubWorker):
    async def survey(self, unit) -> UnitReport:
        raise RuntimeError('boom: this worker always fails')


@dataclass
class SpyFactory:
    """Wraps a worker class, recording each call and which unit it processed next."""

    worker_cls: type = StubWorker
    calls: list = field(default_factory=list)
    made: list = field(default_factory=list)

    def __call__(self):
        worker = self.worker_cls()
        self.made.append(worker)
        return worker


@dataclass
class FlakyFactory:
    """Returns `StubWorker` for the first `fail_after` calls, then `RaisingWorker`.

    Lets a test drive some real, counted progress before the crash, so the
    failure status line's done/queued/elapsed can be checked against actual
    numbers rather than against zeros.
    """

    fail_after: int
    made: list = field(default_factory=list)

    def __call__(self):
        worker = RaisingWorker() if len(self.made) >= self.fail_after else StubWorker()
        self.made.append(worker)
        return worker


def _make_after_scan_spy():
    calls: list[tuple[Ledger, Run]] = []

    def after_scan(ledger: Ledger, run: Run) -> None:
        calls.append((ledger, run))

    return after_scan, calls


# -- bullet: units=2 scans exactly two units, ends stopped_budget -------------


def test_units_budget_stops_after_exactly_two_units(repo: Path, settings: Settings) -> None:
    factory = SpyFactory()
    options = ScanOptions(units=2, minutes=10_000, tokens=10_000_000)

    run = run_scan(repo, options, settings, worker_factory=factory, indexer=_noop_indexer)

    assert run.status == 'stopped_budget'
    assert run.units_done == 2
    assert len(factory.made) == 2
    assert run.claims_confirmed == 2
    assert run.claims_refuted == 2
    assert run.tokens_used == 2 * StubWorker.FIXED_TOKENS


# -- bullet: tokens=1 ends after one unit with stopped_budget -----------------


def test_tokens_budget_stops_after_one_unit(repo: Path, settings: Settings) -> None:
    factory = SpyFactory()
    options = ScanOptions(units=10_000, minutes=10_000, tokens=1)

    run = run_scan(repo, options, settings, worker_factory=factory, indexer=_noop_indexer)

    assert run.status == 'stopped_budget'
    assert run.units_done == 1
    assert len(factory.made) == 1


# -- bullet: a large budget drains the queue and ends stopped_complete -------


def test_large_budget_drains_queue_and_completes(repo: Path, settings: Settings) -> None:
    factory = SpyFactory()
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)

    run = run_scan(repo, options, settings, worker_factory=factory, indexer=_noop_indexer)

    assert run.status == 'stopped_complete'
    assert run.units_done == len(factory.made)
    assert run.units_done > 2
    assert run.claims_confirmed == run.units_done
    assert run.claims_refuted == run.units_done
    assert run.tokens_used == run.units_done * StubWorker.FIXED_TOKENS


# -- bullet: a stub that raises -> run failed, exception propagates ----------


def test_raising_worker_fails_run_and_propagates(repo: Path, settings: Settings) -> None:
    factory = SpyFactory(worker_cls=RaisingWorker)
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)

    with pytest.raises(RuntimeError, match='boom'):
        run_scan(repo, options, settings, worker_factory=factory, indexer=_noop_indexer)

    with Ledger.open(repo) as ledger:
        last = ledger.last_run()
        assert last is not None
        assert last.status == 'failed'


# -- regression: the failure status line reports real elapsed time and real
# progress, not a raw clock reading and hardcoded [0/0] ---------------------

_FAILURE_LINE_RE = re.compile(r'\[(\d+)/(\d+)\].*elapsed=([\d.]+)s.*error=')


def test_failure_status_line_reports_real_elapsed_and_progress(
    repo: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    factory = FlakyFactory(fail_after=2)
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)

    with pytest.raises(RuntimeError, match='boom'):
        run_scan(repo, options, settings, worker_factory=factory, indexer=_noop_indexer)

    with Ledger.open(repo) as ledger:
        last = ledger.last_run()
        assert last is not None
        assert last.status == 'failed'
        assert last.units_done == 2  # the two units that ran before the crash

    output = capsys.readouterr().out
    failure_lines = [line for line in output.splitlines() if 'error=' in line]
    assert len(failure_lines) == 1, f'expected exactly one failure status line, got: {failure_lines!r}'

    match = _FAILURE_LINE_RE.search(failure_lines[0])
    assert match is not None, f'failure status line did not match the expected shape: {failure_lines[0]!r}'
    done, queued, elapsed = int(match.group(1)), int(match.group(2)), float(match.group(3))

    # Real progress, not the hardcoded [0/0] the bug reported regardless of
    # how much work had actually happened.
    assert done == 2
    assert queued > done
    # Real time since the scan began, not a raw `time.monotonic()` reading
    # (which is process-uptime-since-boot and was seen at 70588.8s in review
    # for an instant crash) — this whole test runs in well under a minute.
    assert 0.0 <= elapsed < 60.0


# -- bullet: rerunning an unchanged repo scans nothing new -------------------


def test_rerun_on_unchanged_repo_scans_nothing_new(repo: Path, settings: Settings) -> None:
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)

    first = run_scan(repo, options, settings, worker_factory=SpyFactory(), indexer=_noop_indexer)
    assert first.status == 'stopped_complete'
    assert first.units_done > 0

    second_factory = SpyFactory()
    second = run_scan(repo, options, settings, worker_factory=second_factory, indexer=_noop_indexer)

    assert second.status == 'stopped_complete'
    assert second.units_done == 0
    assert len(second_factory.made) == 0


# -- bullet: editing one function rescans only the affected units -----------

# `units.ast_hash` (T-06) hashes a unit's whole `ast.dump`, so editing a
# method's body also changes the `ast.dump` of its enclosing class (the
# method's body is inside the class's own AST) and of the module (the whole
# file's AST) — see `seshat/units.py`'s module docstring. Editing
# `OrderRepository.add` therefore changes exactly three units, not one:
# the method itself, the `OrderRepository` class, and the `demo/repository.py`
# module. This is what "only the affected units, not the whole repo" means
# here, and it is what the second scan below is checked against.
_EXPECTED_CHANGED_QUALIFIED_NAMES = {'OrderRepository.add', 'OrderRepository', 'demo/repository.py'}


def test_edit_one_function_rescans_only_affected_units(
    repo: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)

    first_factory = SpyFactory()
    first = run_scan(repo, options, settings, worker_factory=first_factory, indexer=_noop_indexer)
    assert first.status == 'stopped_complete'
    total_units_first_scan = first.units_done

    # The first scan must have persisted verifier rows, or the rerun set is
    # trivially empty and this whole bullet is meaningless.
    with Ledger.open(repo) as ledger:
        assert len(ledger.all_verifiers()) > 0

    # The verifiers that *should* be rerun: whatever, right now (before the
    # edit and before the second scan creates any new ones of its own),
    # touches one of the three units the edit is about to change.
    with Ledger.open(repo) as ledger:
        changed_unit_ids_before_edit = [
            u.id for u in ledger.units() if u.qualified_name in _EXPECTED_CHANGED_QUALIFIED_NAMES
        ]
        expected_rerun_verifiers = ledger.verifiers_touching(changed_unit_ids_before_edit)
        all_verifiers_before_edit = ledger.all_verifiers()

    repo_py = repo / 'demo' / 'repository.py'
    original = repo_py.read_text()
    edited = original.replace(
        'def add(self, order_id: str, payload: dict) -> None:\n        self._orders[order_id] = payload',
        'def add(self, order_id: str, payload: dict) -> None:\n        self._orders[order_id] = dict(payload)',
    )
    assert edited != original, 'fixture source did not match the expected snippet to edit'
    repo_py.write_text(edited)

    verify_calls: list[str] = []
    original_verify_and_record = scan_mod.verify_and_record

    def spy_verify_and_record(ledger: Ledger, verifier: Verifier, graph: Graph, run_id: str) -> VerifierResult:
        verify_calls.append(verifier.claim_id)
        return original_verify_and_record(ledger, verifier, graph, run_id)

    monkeypatch.setattr(scan_mod, 'verify_and_record', spy_verify_and_record)

    second_factory = SpyFactory()
    second = run_scan(repo, options, settings, worker_factory=second_factory, indexer=_noop_indexer)

    assert second.status == 'stopped_complete'
    # Not the whole repo rescanned again — only the units whose ast_hash
    # actually moved.
    assert second.units_done < total_units_first_scan
    assert len(second_factory.made) == second.units_done

    scanned_names = {w._unit.qualified_name for w in second_factory.made}
    assert scanned_names == _EXPECTED_CHANGED_QUALIFIED_NAMES

    # Only the changed units' verifiers were rerun, not every verifier in the
    # ledger — the first scan touched many more units than these three.
    assert len(expected_rerun_verifiers) > 0
    assert len(expected_rerun_verifiers) < len(all_verifiers_before_edit)
    assert set(verify_calls) == {v.claim_id for v in expected_rerun_verifiers}


# -- bullet: after_scan is called once with the ledger and the run ----------


def test_after_scan_called_once_with_ledger_and_run(repo: Path, settings: Settings) -> None:
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)
    after_scan, calls = _make_after_scan_spy()

    run = run_scan(repo, options, settings, worker_factory=SpyFactory(), indexer=_noop_indexer, after_scan=after_scan)

    assert len(calls) == 1
    called_ledger, called_run = calls[0]
    assert isinstance(called_ledger, Ledger)
    assert called_run.id == run.id


# -- bullet: workers=2 completes with the same counters as workers=1 --------


def test_workers_two_matches_workers_one_counters_with_large_budget(
    repo: Path, fixture_target: Path, settings: Settings
) -> None:
    options_one = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000, workers=1)
    run_one = run_scan(repo, options_one, settings, worker_factory=SpyFactory(), indexer=_noop_indexer)

    # A fresh, never-scanned copy — reusing `repo` here would find every unit
    # already `scanned` with a matching ast_hash and scan nothing at all.
    repo2 = repo.parent / 'target2'
    shutil.copytree(fixture_target, repo2)
    options_two = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000, workers=2)
    run_two = run_scan(repo2, options_two, settings, worker_factory=SpyFactory(), indexer=_noop_indexer)

    assert run_one.status == run_two.status == 'stopped_complete'
    assert run_one.units_done == run_two.units_done
    assert run_one.claims_confirmed == run_two.claims_confirmed
    assert run_one.claims_refuted == run_two.claims_refuted
    assert run_one.tokens_used == run_two.tokens_used


# -- indexer injection / IndexFailed -----------------------------------------


def test_index_failed_raised_on_nonzero_indexer_exit(repo: Path, settings: Settings) -> None:
    def failing_indexer(repo: Path) -> None:
        raise IndexFailed('boom: codegraph exited non-zero\nsome stderr')

    with pytest.raises(IndexFailed):
        run_scan(repo, ScanOptions(), settings, worker_factory=SpyFactory(), indexer=failing_indexer)


# -- T-15: report the unreadable count where a human will see it ------------
#
# Same bad-byte constant tests/test_units.py's T-14 tests use for "genuinely
# unreadable" (the bad byte is in code, not a comment, so ast.parse raises
# SyntaxError on it). `demo/__init__.py` is corrupted here rather than
# `demo/repository.py` because it holds no class/function of its own -- one
# module unit, one unreadable unit, so "the count is 1" is unambiguous
# instead of module+class+method all going unreadable together.
_GENUINELY_UNREADABLE_BYTES = b'co\xfbt = 1\n'


def test_unreadable_file_is_named_and_counted(
    repo: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / 'demo' / '__init__.py').write_bytes(_GENUINELY_UNREADABLE_BYTES)
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)

    run = run_scan(repo, options, settings, worker_factory=SpyFactory(), indexer=_noop_indexer)

    assert run.status == 'stopped_complete'
    output = capsys.readouterr().out
    naming_lines = [line for line in output.splitlines() if 'demo/__init__.py' in line]
    assert len(naming_lines) == 1, f'expected exactly one line naming the unreadable file, got: {naming_lines!r}'

    status_lines = [line for line in output.splitlines() if 'unreadable=' in line]
    assert status_lines, 'expected at least one status line reporting the unreadable count'
    assert all('unreadable=1' in line for line in status_lines)


def test_clean_repo_prints_no_unreadable_naming_line(
    repo: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    # Scope item 2's ruling: the silence-at-zero rule applies only to the
    # file-naming line (item 3) -- the status line's own `unreadable=N`
    # counter is never silenced, including at 0, so this asserts on the
    # *naming* line's absence specifically, not on the word "unreadable"
    # being absent from the whole run's output.
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)

    run = run_scan(repo, options, settings, worker_factory=SpyFactory(), indexer=_noop_indexer)

    assert run.status == 'stopped_complete'
    output = capsys.readouterr().out
    naming_lines = [line for line in output.splitlines() if line.startswith('unreadable (')]
    assert naming_lines == [], f'a clean repo must print no unreadable-naming line at all, got: {naming_lines!r}'

    status_lines = [line for line in output.splitlines() if 'unreadable=' in line]
    assert status_lines, 'expected at least one status line reporting the (zero) unreadable count'
    assert all('unreadable=0' in line for line in status_lines)


def test_crash_before_sync_units_reports_zero_unreadable(
    repo: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError('boom: crash before sync_units')

    monkeypatch.setattr(scan_mod, 'seed_docs', boom)
    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)

    with pytest.raises(RuntimeError, match='boom: crash before sync_units'):
        run_scan(repo, options, settings, worker_factory=SpyFactory(), indexer=_noop_indexer)

    output = capsys.readouterr().out
    failure_lines = [line for line in output.splitlines() if 'error=' in line]
    assert len(failure_lines) == 1, f'expected exactly one failure status line, got: {failure_lines!r}'
    assert 'unreadable=0' in failure_lines[0]


# -- fix round 1: naming-line cap/remainder arithmetic, unresolved-id fallback

# Follow-up findings on T-15: the `and N more` arithmetic in
# `_unreadable_names_line` and the `ledger.unit(...) is None` fallback both
# had no test of their own -- the three tests above only ever hit 1 unreadable
# unit at a time, well under the cap, and never an id the ledger can't
# resolve.


def _module_only_indexed_repo(repo_dir: Path, file_names: list[str]) -> Path:
    """A throwaway repo, indexed for real, with one module-only .py file per name.

    Mirrors tests/test_units.py's `_indexed_repo`: module-only files (no
    class or function) so each corrupted file below contributes exactly one
    unreadable *unit*, keeping "N distinct unreadable files" and "N
    unreadable units" the same number -- the cap/remainder test needs that to
    hold, or "5 files -> and 2 more" would not follow from the file count.
    """
    for name in file_names:
        target = repo_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'{Path(name).stem}_marker = 1\n')
    env = {**os.environ, 'CODEGRAPH_TELEMETRY': '0'}
    result = subprocess.run(
        ['codegraph', 'init', str(repo_dir)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return repo_dir


def test_naming_line_caps_at_three_and_reports_and_n_more_through_run_scan(
    tmp_path: Path, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """5 distinct unreadable files: only the first 3 are named, `and 2 more`
    covers the rest, and the leading count is the true total (5), not the
    shown count (3) -- through `run_scan` itself, so the print path (not just
    the helper function) is covered.
    """
    file_names = [f'demo/mod_{i}.py' for i in range(5)]
    repo5 = _module_only_indexed_repo(tmp_path, file_names)
    for name in file_names:
        (repo5 / name).write_bytes(_GENUINELY_UNREADABLE_BYTES)

    options = ScanOptions(units=10_000, minutes=10_000, tokens=10_000_000)
    run = run_scan(repo5, options, settings, worker_factory=SpyFactory(), indexer=_noop_indexer)

    assert run.status == 'stopped_complete'
    output = capsys.readouterr().out
    naming_lines = [line for line in output.splitlines() if line.startswith('unreadable (')]
    assert len(naming_lines) == 1, f'expected exactly one naming line, got: {naming_lines!r}'
    line = naming_lines[0]

    assert line.endswith('and 2 more'), line
    prefix, _, rest = line.partition(': ')
    assert prefix == 'unreadable (5)', line
    names_part = rest.rsplit(' and ', 1)[0]
    shown_names = [n.strip() for n in names_part.split(',') if n.strip()]
    assert len(shown_names) == 3, f'expected exactly 3 named files, got: {shown_names!r}'
    for name in shown_names:
        assert name in file_names


def _unreadable_unit_row(unit_id: str, file_path: str, run_id: str) -> Unit:
    return Unit(
        id=unit_id,
        repo_id='',
        file_path=file_path,
        qualified_name=file_path,
        kind='module',
        start_line=1,
        end_line=1,
        ast_hash=None,
        inbound_calls=0,
        first_seen_run=run_id,
        last_seen_run=run_id,
        last_scanned_run=run_id,
        status='unreadable',
    )


def test_naming_line_boundary_at_exactly_the_cap_has_no_and_more_suffix(tmp_path: Path) -> None:
    """Exactly 3 unreadable files (the cap itself): every one is named, and
    there is no `and N more` suffix at all -- the boundary the off-by-one
    arithmetic has to get right in both directions.
    """
    boundary_repo = tmp_path / 'boundary'
    boundary_repo.mkdir()

    with Ledger.open(boundary_repo) as ledger:
        run_id = ledger.create_run().id
        unit_ids = []
        for i in range(3):
            unit = _unreadable_unit_row(f'unit-{i}', f'demo/file_{i}.py', run_id)
            ledger.upsert_unit(unit, run_id)
            unit_ids.append(unit.id)

        line = scan_mod._unreadable_names_line(ledger, unit_ids)

    assert line is not None
    assert line.startswith('unreadable (3):'), line
    assert 'more' not in line, line
    for i in range(3):
        assert f'demo/file_{i}.py' in line


def test_naming_line_unresolved_unit_id_falls_back_to_the_raw_id(tmp_path: Path) -> None:
    """`ledger.unit(unit_id)` returning `None` (T-15 scope item 3's fallback,
    scan.py:130-131) must still produce a usable line naming the raw id,
    not crash and not silently drop the unresolved unit.
    """
    empty_repo = tmp_path / 'empty'
    empty_repo.mkdir()

    with Ledger.open(empty_repo) as ledger:
        line = scan_mod._unreadable_names_line(ledger, ['no-such-unit-id'])

    assert line is not None
    assert 'no-such-unit-id' in line
