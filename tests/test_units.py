"""Acceptance tests for T-06 — unit enumeration, ast_hash, drift diff.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-06-units-and-drift.md. Committed alone, before any
implementation exists, per the project's red-then-green contract.

Tests copy `fixture_target` (including `.codegraph/`) into a tmp dir so they can
edit the source in place. Per the task's Non-scope, the copy's codegraph index is
never rebuilt when the source changes — drift detection here rests on `ast_hash`
alone re-reading the edited file, exactly like the real `sync_units` will have to
in the field between `codegraph init` runs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from seshat.graph import Graph, Node
from seshat.ledger.store import Ledger
from seshat.units import UNREADABLE, ast_hash, build_queue, enumerate_units, sync_units, unit_id, verifiers_to_rerun


@pytest.fixture
def repo(tmp_path: Path, fixture_target: Path) -> Path:
    dest = tmp_path / 'target'
    shutil.copytree(fixture_target, dest)
    return dest


@pytest.fixture
def graph(repo: Path) -> Iterator[Graph]:
    g = Graph.open(repo)
    yield g
    g.close()


@pytest.fixture
def ledger(repo: Path) -> Iterator[Ledger]:
    led = Ledger.open(repo)
    yield led
    led.close()


def _new_run_id(ledger: Ledger) -> str:
    return ledger.create_run().id


# -- T-14: a repo with one undecodable file, indexed for real ---------------

# Three byte strings from tasks/seshat-phase-one/T-14-unreadable-source-files.md's
# Context section, each for a different test — not interchangeable.

# Reproduces today's crash: the bad byte is inside a comment, so `ast.parse`
# on the raw bytes parses this fine (PEP 263 default utf-8, replaced with the
# actual encoding the comment happens to decode under) once `ast_hash` reads
# bytes -- it's `read_text()` that raises today.
_CRASHING_COMMENT_BYTES = b'def cafe_price():\n    # co\xfbt en francs\n    return 42\n'

# Genuinely unreadable: the bad byte is in code, not a comment -- `ast.parse`
# raises `SyntaxError` on these bytes.
_GENUINELY_UNREADABLE_BYTES = b'co\xfbt = 1\n'


def _indexed_repo(tmp_path: Path, extra_files: dict[str, bytes]) -> Path:
    """A throwaway repo, for real, with `codegraph init` run over it.

    Minimal rather than a copy of `fixture_target`: the enumerate_units/sync_units
    tests below need a real codegraph index (not the hand-built sqlite `test_graph.py`
    uses) so a genuinely undecodable file gets indexed the way codegraph really
    indexes one -- see the manual repro in the task's planning conversation.
    """
    (tmp_path / 'demo').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'demo' / 'hello.py').write_text('def hello():\n    return 1\n')
    for relative_path, content in extra_files.items():
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    env = {**os.environ, 'CODEGRAPH_TELEMETRY': '0'}
    result = subprocess.run(
        ['codegraph', 'init', str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return tmp_path


# -- ast_hash: a declared encoding is not drift -------------------------------


def test_ast_hash_on_latin1_declared_file_equals_hash_of_same_code_as_utf8(tmp_path: Path) -> None:
    latin1_repo = tmp_path / 'latin1'
    latin1_repo.mkdir()
    latin1_source = '# -*- coding: latin-1 -*-\ndef cout():\n    return 1\n'.encode('latin-1')
    (latin1_repo / 'mod.py').write_bytes(latin1_source)
    latin1_node = Node(qualified_name='cout', file_path='mod.py', kind='module', start_line=1, end_line=3)

    utf8_repo = tmp_path / 'utf8'
    utf8_repo.mkdir()
    utf8_source = b'# -*- coding: latin-1 -*-\ndef cout():\n    return 1\n'
    (utf8_repo / 'mod.py').write_bytes(utf8_source)
    utf8_node = Node(qualified_name='cout', file_path='mod.py', kind='module', start_line=1, end_line=3)

    latin1_hash = ast_hash(latin1_repo, latin1_node)
    utf8_hash = ast_hash(utf8_repo, utf8_node)

    assert latin1_hash is not None
    assert latin1_hash != UNREADABLE
    assert latin1_hash == utf8_hash


# -- ast_hash: unreadable is distinguishable from missing ---------------------


def test_ast_hash_reports_unreadable_distinct_from_missing_symbol(tmp_path: Path) -> None:
    unreadable_repo = tmp_path / 'unreadable'
    unreadable_repo.mkdir()
    (unreadable_repo / 'mod.py').write_bytes(_GENUINELY_UNREADABLE_BYTES)
    unreadable_node = Node(qualified_name='mod', file_path='mod.py', kind='module', start_line=1, end_line=1)

    missing_repo = tmp_path / 'missing'
    missing_repo.mkdir()
    (missing_repo / 'mod.py').write_text('def other():\n    return 1\n')
    missing_node = Node(qualified_name='not_there', file_path='mod.py', kind='function', start_line=1, end_line=2)

    unreadable_result = ast_hash(unreadable_repo, unreadable_node)
    missing_result = ast_hash(missing_repo, missing_node)

    assert unreadable_result == UNREADABLE
    assert missing_result is None
    assert unreadable_result != missing_result


# -- enumerate_units: the crash this task exists to fix ----------------------


def test_enumerate_units_completes_over_repo_with_undecodable_file(tmp_path: Path) -> None:
    repo = _indexed_repo(tmp_path, {'demo/comment_bad.py': _CRASHING_COMMENT_BYTES})

    with Graph.open(repo) as graph:
        units = enumerate_units(graph, repo)

    file_paths = {u.file_path for u in units}
    assert 'demo/hello.py' in file_paths
    assert 'demo/comment_bad.py' in file_paths


# -- sync_units: unreadable status, not vanished ------------------------------


def test_sync_units_puts_unreadable_file_in_diff_unreadable_with_null_hash(tmp_path: Path) -> None:
    repo = _indexed_repo(tmp_path, {'demo/broken.py': _GENUINELY_UNREADABLE_BYTES})

    with Graph.open(repo) as graph, Ledger.open(repo) as ledger:
        run_id = _new_run_id(ledger)
        units = enumerate_units(graph, repo)
        diff = sync_units(ledger, units, run_id)

        broken_unit = next(u for u in units if u.file_path == 'demo/broken.py' and u.kind == 'module')

        assert broken_unit.id in diff.unreadable
        assert broken_unit.id not in diff.vanished
        row = ledger.unit(broken_unit.id)
        assert row is not None
        assert row.status == 'unreadable'
        assert row.ast_hash is None


def test_unreadable_on_first_sync_recovers_to_changed_and_reaches_build_queue(tmp_path: Path) -> None:
    repo = _indexed_repo(tmp_path, {'demo/broken.py': _GENUINELY_UNREADABLE_BYTES})

    with Graph.open(repo) as graph, Ledger.open(repo) as ledger:
        run_id_1 = _new_run_id(ledger)
        units_1 = enumerate_units(graph, repo)
        diff_1 = sync_units(ledger, units_1, run_id_1)

        broken_unit = next(u for u in units_1 if u.file_path == 'demo/broken.py' and u.kind == 'module')
        assert broken_unit.id in diff_1.unreadable
        row_1 = ledger.unit(broken_unit.id)
        assert row_1 is not None
        assert row_1.status == 'unreadable'

        # The file becomes valid utf-8 -- no reindex needed, the graph node
        # for this file path already exists.
        (repo / 'demo' / 'broken.py').write_text('cout = 1\n')

        run_id_2 = _new_run_id(ledger)
        units_2 = enumerate_units(graph, repo)
        diff_2 = sync_units(ledger, units_2, run_id_2)

        assert broken_unit.id in diff_2.changed
        assert broken_unit.id not in diff_2.unreadable
        row_2 = ledger.unit(broken_unit.id)
        assert row_2 is not None
        assert row_2.status == 'changed'
        assert row_2.ast_hash is not None

        queue = build_queue(ledger, seed_names=set())
        assert broken_unit.id in {u.id for u in queue}


def test_claims_on_newly_unreadable_unit_are_marked_stale(tmp_path: Path) -> None:
    from seshat.ledger.models import Claim

    repo = _indexed_repo(tmp_path, {'demo/breaks_later.py': b'def ok():\n    return 1\n'})

    with Graph.open(repo) as graph, Ledger.open(repo) as ledger:
        run_id_1 = _new_run_id(ledger)
        units_1 = enumerate_units(graph, repo)
        sync_units(ledger, units_1, run_id_1)

        target = next(u for u in units_1 if u.file_path == 'demo/breaks_later.py' and u.kind == 'module')
        claim = ledger.add_claim(
            Claim(
                id='',
                repo_id='',
                unit_id=target.id,
                text='breaks_later defines ok, which returns 1.',
                kind='structural',
                source='code',
                mode='claims',
                status='conjectured',
                confidence=0.9,
                candidate_rule=0,
                rule_sightings=0,
                created_run=run_id_1,
                verified_run=None,
                verified_sha=None,
                retries=0,
            )
        )

        (repo / 'demo' / 'breaks_later.py').write_bytes(_GENUINELY_UNREADABLE_BYTES)

        run_id_2 = _new_run_id(ledger)
        units_2 = enumerate_units(graph, repo)
        diff_2 = sync_units(ledger, units_2, run_id_2)

        assert target.id in diff_2.unreadable

        claims_for_target = ledger.claims_for_unit(target.id)
        refetched = next(c for c in claims_for_target if c.id == claim.id)
        assert refetched.status == 'stale'


# -- bullet: enumerate_units yields >= 8 non-module units plus one module unit
# per .py file, and every non-module unit has a non-None ast_hash ------------


def test_enumerate_units_covers_non_module_and_module_units(graph: Graph, repo: Path) -> None:
    units = enumerate_units(graph, repo)

    non_module = [u for u in units if u.kind != 'module']
    modules = [u for u in units if u.kind == 'module']

    assert len(non_module) >= 8
    assert all(u.ast_hash is not None for u in non_module)

    py_files = {p.relative_to(repo).as_posix() for p in repo.rglob('*.py')}
    module_paths = {u.file_path for u in modules}
    assert module_paths == py_files


# -- bullet: unit_id is stable across calls and differs for a different file -


def test_unit_id_stable_and_differs_by_file() -> None:
    a1 = unit_id('demo/repository.py', 'OrderRepository.get')
    a2 = unit_id('demo/repository.py', 'OrderRepository.get')
    b = unit_id('demo/orders.py', 'OrderRepository.get')

    assert a1 == a2
    assert a1 != b


# -- bullet: first sync_units returns everything in `new`, ledger rows pending --


def test_first_sync_returns_everything_new_and_pending(graph: Graph, ledger: Ledger, repo: Path) -> None:
    run_id = _new_run_id(ledger)
    units = enumerate_units(graph, repo)

    diff = sync_units(ledger, units, run_id)

    assert set(diff.new) == {u.id for u in units}
    assert diff.unchanged == []
    assert diff.changed == []
    assert diff.vanished == []
    for u in units:
        row = ledger.unit(u.id)
        assert row is not None
        assert row.status == 'pending'


# -- bullet: second sync_units with no edits returns everything unchanged ----


def test_second_sync_with_no_edits_is_all_unchanged(graph: Graph, ledger: Ledger, repo: Path) -> None:
    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    # A unit carries whatever status the previous run left it in — here,
    # 'changed' from a prior drift the worker has not gotten to yet. The
    # unchanged path in sync_units (this run's hash matches, nothing moved)
    # must leave that status exactly alone: not reset to 'pending', and not
    # hard-coded to any other fixed value either, since a status corruption
    # here silently drops the unit out of (or into) the wrong side of the
    # queue without it having drifted this run at all.
    tracked_unit = next(u for u in units if u.qualified_name == 'OrderRepository')
    ledger.set_unit_status(tracked_unit.id, 'changed', run_id_1)

    run_id_2 = _new_run_id(ledger)
    units_again = enumerate_units(graph, repo)
    diff = sync_units(ledger, units_again, run_id_2)

    assert set(diff.unchanged) == {u.id for u in units_again}
    assert diff.new == []
    assert diff.changed == []
    assert diff.vanished == []

    row = ledger.unit(tracked_unit.id)
    assert row is not None
    assert row.status == 'changed'


# -- bullet: editing a function body (not its name) marks only that unit
# changed, its claims stale, and verifiers_to_rerun scoped to it -------------


def test_editing_function_body_marks_changed_stale_and_scopes_verifiers(
    graph: Graph, ledger: Ledger, repo: Path
) -> None:
    from seshat.ledger.models import Claim, Verifier

    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    target = next(u for u in units if u.qualified_name == 'OrderRepository.get')
    other = next(u for u in units if u.qualified_name == 'OrderRepository.add')

    claim_target = ledger.add_claim(
        Claim(
            id='',
            repo_id='',
            unit_id=target.id,
            text='get raises OrderNotFound when missing.',
            kind='structural',
            source='code',
            mode='claims',
            status='conjectured',
            confidence=0.9,
            candidate_rule=0,
            rule_sightings=0,
            created_run=run_id_1,
            verified_run=None,
            verified_sha=None,
            retries=0,
        )
    )
    verifier_target = ledger.add_verifier(
        Verifier(
            id='',
            repo_id='',
            claim_id=claim_target.id,
            source='def check(graph): return True',
            expected='true',
            depends_on=[target.id],
        )
    )
    claim_other = ledger.add_claim(
        Claim(
            id='',
            repo_id='',
            unit_id=other.id,
            text='add stores the order.',
            kind='structural',
            source='code',
            mode='claims',
            status='conjectured',
            confidence=0.9,
            candidate_rule=0,
            rule_sightings=0,
            created_run=run_id_1,
            verified_run=None,
            verified_sha=None,
            retries=0,
        )
    )
    ledger.add_verifier(
        Verifier(
            id='',
            repo_id='',
            claim_id=claim_other.id,
            source='def check(graph): return True',
            expected='true',
            depends_on=[other.id],
        )
    )

    source_path = repo / 'demo' / 'repository.py'
    edited = source_path.read_text().replace(
        'return self._get_or_raise(order_id)',
        'result = self._get_or_raise(order_id)\n        return result',
    )
    assert edited != source_path.read_text()
    source_path.write_text(edited)

    class_unit = next(u for u in units if u.qualified_name == 'OrderRepository' and u.kind == 'class')
    module_unit = next(u for u in units if u.kind == 'module' and u.file_path == 'demo/repository.py')

    run_id_2 = _new_run_id(ledger)
    units_after = enumerate_units(graph, repo)
    diff = sync_units(ledger, units_after, run_id_2)

    # Corrected acceptance criterion (develop@1ca3e91): editing a method's body
    # necessarily also changes the ast.dump of every unit whose subtree
    # contains it — the enclosing class and the module, since a class or
    # module hash always contains the bodies of everything nested inside it.
    # Both are legitimately `changed`, not a bug. An untouched sibling method
    # in the same class must stay `unchanged`.
    assert target.id in diff.changed
    assert class_unit.id in diff.changed
    assert module_unit.id in diff.changed
    assert target.id not in diff.unchanged
    assert other.id not in diff.changed
    assert other.id in diff.unchanged

    claims_for_target = ledger.claims_for_unit(target.id)
    assert all(c.status == 'stale' for c in claims_for_target)
    claims_for_other = ledger.claims_for_unit(other.id)
    assert all(c.status != 'stale' for c in claims_for_other)

    reruns = verifiers_to_rerun(ledger, diff, full=False)
    assert {v.id for v in reruns} == {verifier_target.id}


# -- bullet: adding only a comment inside a function leaves it unchanged -----


def test_comment_only_edit_is_unchanged(graph: Graph, ledger: Ledger, repo: Path) -> None:
    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    source_path = repo / 'demo' / 'repository.py'
    edited = source_path.read_text().replace(
        'def get(self, order_id: str) -> dict:',
        'def get(self, order_id: str) -> dict:\n        # a comment, not a code change',
    )
    source_path.write_text(edited)

    run_id_2 = _new_run_id(ledger)
    units_after = enumerate_units(graph, repo)
    diff = sync_units(ledger, units_after, run_id_2)

    target = next(u for u in units if u.qualified_name == 'OrderRepository.get')
    assert target.id in diff.unchanged
    assert target.id not in diff.changed


# -- pin: a docstring-only edit counts as a change (documented decision) -----


def test_docstring_only_edit_counts_as_changed(graph: Graph, ledger: Ledger, repo: Path) -> None:
    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    source_path = repo / 'demo' / 'repository.py'
    edited = source_path.read_text().replace(
        '"""Return the order for `order_id`, raising `OrderNotFound` if absent."""',
        '"""A different docstring, no code touched."""',
    )
    assert edited != source_path.read_text()
    source_path.write_text(edited)

    run_id_2 = _new_run_id(ledger)
    units_after = enumerate_units(graph, repo)
    diff = sync_units(ledger, units_after, run_id_2)

    target = next(u for u in units if u.qualified_name == 'OrderRepository.get')
    assert target.id in diff.changed


# -- bullet: deleting a function from the source marks it vanished -----------


def test_deleting_function_marks_vanished(graph: Graph, ledger: Ledger, repo: Path) -> None:
    from seshat.ledger.models import Claim

    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    target = next(u for u in units if u.qualified_name == 'format_currency')
    claim = ledger.add_claim(
        Claim(
            id='',
            repo_id='',
            unit_id=target.id,
            text='format_currency formats cents as a dollar string.',
            kind='structural',
            source='code',
            mode='claims',
            status='conjectured',
            confidence=0.9,
            candidate_rule=0,
            rule_sightings=0,
            created_run=run_id_1,
            verified_run=None,
            verified_sha=None,
            retries=0,
        )
    )

    source_path = repo / 'demo' / 'receipts.py'
    text = source_path.read_text()
    deleted = text.replace(
        "@lru_cache\ndef format_currency(cents: int) -> str:\n    return f'${cents / 100:.2f}'\n\n\n",
        '',
    )
    assert deleted != text
    source_path.write_text(deleted)

    run_id_2 = _new_run_id(ledger)
    units_after = enumerate_units(graph, repo)
    diff = sync_units(ledger, units_after, run_id_2)

    assert target.id in diff.vanished
    row = ledger.unit(target.id)
    assert row is not None
    assert row.status == 'vanished'

    claims_for_target = ledger.claims_for_unit(target.id)
    assert claims_for_target
    assert all(c.status == 'stale' for c in claims_for_target)
    refetched = next(c for c in claims_for_target if c.id == claim.id)
    assert refetched.status == 'stale'


# -- decision: a unit that is vanished on first sight (never in the ledger,
# ast_hash already None the first time it's enumerated) still gets a
# resolvable ledger row, not a bare id in diff.vanished that ledger.unit()
# can't answer for. See the docstring on sync_units for the reasoning. -------


def test_vanished_on_first_sight_still_gets_a_resolvable_ledger_row(graph: Graph, ledger: Ledger, repo: Path) -> None:
    # Delete the function from source *before* the very first sync, so this
    # unit is unknown to the ledger and already unresolvable in the same pass
    # -- prior is None and ast_hash is None at once.
    source_path = repo / 'demo' / 'receipts.py'
    text = source_path.read_text()
    deleted = text.replace(
        "@lru_cache\ndef format_currency(cents: int) -> str:\n    return f'${cents / 100:.2f}'\n\n\n",
        '',
    )
    assert deleted != text
    source_path.write_text(deleted)

    run_id = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    target = next(u for u in units if u.qualified_name == 'format_currency')
    assert target.ast_hash is None

    diff = sync_units(ledger, units, run_id)

    assert target.id in diff.vanished
    row = ledger.unit(target.id)
    assert row is not None
    assert row.status == 'vanished'
    assert row.ast_hash is None


# -- property: a transiently-unreadable file (e.g. a SyntaxError mid-edit)
# does not leave its unit permanently vanished. The next sync that can parse
# the file again must route it into `changed`, not leave it stuck comparing
# against a stale cached hash. -----------------------------------------------


def test_transient_syntax_error_self_heals_into_changed(graph: Graph, ledger: Ledger, repo: Path) -> None:
    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    target = next(u for u in units if u.qualified_name == 'format_currency')
    assert target.ast_hash is not None

    source_path = repo / 'demo' / 'receipts.py'
    original = source_path.read_text()
    # Drop the colon: a SyntaxError, not a symbol that's gone -- ast.parse
    # raises on bytes that were read, so this is the `unreadable` branch
    # (T-14), not `vanished` -- the file itself was read fine, it just
    # doesn't parse.
    corrupted = original.replace(
        'def format_currency(cents: int) -> str:',
        'def format_currency(cents: int) -> str',
    )
    assert corrupted != original
    source_path.write_text(corrupted)

    run_id_2 = _new_run_id(ledger)
    units_2 = enumerate_units(graph, repo)
    diff_2 = sync_units(ledger, units_2, run_id_2)

    assert target.id in diff_2.unreadable
    row_2 = ledger.unit(target.id)
    assert row_2 is not None
    assert row_2.status == 'unreadable'

    # Restore the exact original content -- the same source ast_hash saw
    # before the corruption.
    source_path.write_text(original)

    run_id_3 = _new_run_id(ledger)
    units_3 = enumerate_units(graph, repo)
    diff_3 = sync_units(ledger, units_3, run_id_3)

    assert target.id in diff_3.changed
    assert target.id not in diff_3.unchanged
    assert target.id not in diff_3.vanished
    row_3 = ledger.unit(target.id)
    assert row_3 is not None
    assert row_3.status == 'changed'
    assert row_3.ast_hash is not None
    assert row_3.ast_hash == target.ast_hash


# -- property: the same self-heal guarantee, from the other vanished branch --
# a unit whose node disappears from the graph entirely (not just an unreadable
# file) must not get stuck vanished forever if the node reappears with
# byte-identical content on a later sync.


def test_node_removed_from_graph_then_reappears_self_heals_into_changed(
    graph: Graph, ledger: Ledger, repo: Path
) -> None:
    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    target = next(u for u in units if u.qualified_name == 'format_currency')
    assert target.ast_hash is not None

    # Simulate the node disappearing from the graph entirely (e.g. codegraph
    # reindexed without it) -- omit it from the list passed to sync_units,
    # without touching the source at all.
    run_id_2 = _new_run_id(ledger)
    units_without_target = [u for u in units if u.id != target.id]
    diff_2 = sync_units(ledger, units_without_target, run_id_2)

    assert target.id in diff_2.vanished
    row_2 = ledger.unit(target.id)
    assert row_2 is not None
    assert row_2.status == 'vanished'

    # The node reappears (e.g. a later codegraph reindex picks it back up)
    # with byte-identical source content -- the same ast_hash as before.
    run_id_3 = _new_run_id(ledger)
    units_again = enumerate_units(graph, repo)
    target_again = next(u for u in units_again if u.qualified_name == 'format_currency')
    assert target_again.ast_hash == target.ast_hash

    diff_3 = sync_units(ledger, units_again, run_id_3)

    assert target.id in diff_3.changed
    assert target.id not in diff_3.unchanged
    assert target.id not in diff_3.vanished
    row_3 = ledger.unit(target.id)
    assert row_3 is not None
    assert row_3.status == 'changed'
    assert row_3.ast_hash is not None


# -- bullet: verifiers_to_rerun(full=True) returns every verifier ------------


def test_verifiers_to_rerun_full_returns_every_verifier(graph: Graph, ledger: Ledger, repo: Path) -> None:
    from seshat.ledger.models import Claim, Verifier

    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    unit_a, unit_b = units[0], units[1]
    ids = []
    for u in (unit_a, unit_b):
        claim = ledger.add_claim(
            Claim(
                id='',
                repo_id='',
                unit_id=u.id,
                text=f'claim about {u.qualified_name}',
                kind='structural',
                source='code',
                mode='claims',
                status='conjectured',
                confidence=0.9,
                candidate_rule=0,
                rule_sightings=0,
                created_run=run_id_1,
                verified_run=None,
                verified_sha=None,
                retries=0,
            )
        )
        verifier = ledger.add_verifier(
            Verifier(
                id='',
                repo_id='',
                claim_id=claim.id,
                source='def check(graph): return True',
                expected='true',
                depends_on=[u.id],
            )
        )
        ids.append(verifier.id)

    diff = sync_units(ledger, units, _new_run_id(ledger))
    reruns = verifiers_to_rerun(ledger, diff, full=True)

    assert {v.id for v in reruns} == set(ids)


# -- bullet: build_queue puts a seeded unit first, then by inbound_calls,
# and never includes scanned or vanished units --------------------------


def test_build_queue_orders_by_seed_then_inbound_calls_and_excludes_scanned_vanished(
    graph: Graph, ledger: Ledger, repo: Path
) -> None:
    run_id_1 = _new_run_id(ledger)
    units = enumerate_units(graph, repo)
    sync_units(ledger, units, run_id_1)

    render_receipt = next(u for u in units if u.qualified_name == 'render_receipt')
    print_receipt = next(u for u in units if u.qualified_name == 'print_receipt')
    main_unit = next(u for u in units if u.qualified_name == 'main')

    # main has 0 inbound calls; mark it scanned so it must never appear.
    ledger.set_unit_status(main_unit.id, 'scanned', run_id_1)

    # Pick a unit to fake as vanished so it must never appear either, even
    # though it would otherwise sort high.
    vanished_candidate = next(u for u in units if u.qualified_name == 'OrderRepository.get')
    ledger.set_unit_status(vanished_candidate.id, 'vanished', run_id_1)

    queue = build_queue(ledger, seed_names={'print_receipt'})

    queue_ids = [u.id for u in queue]
    assert main_unit.id not in queue_ids
    assert vanished_candidate.id not in queue_ids

    # print_receipt is seeded, so it must come first regardless of inbound_calls.
    assert queue[0].id == print_receipt.id

    # render_receipt has inbound_calls == 2 (see tests/fixtures/REBUILD.md) and
    # is not seeded, so it must outrank other non-seeded pending units.
    rest = queue[1:]
    assert rest, 'expected other pending units besides the seeded one'
    assert rest[0].id == render_receipt.id
    for later in rest[1:]:
        assert later.inbound_calls <= render_receipt.inbound_calls
