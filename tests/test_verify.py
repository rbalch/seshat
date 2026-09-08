"""Acceptance tests for T-05: verifier runner with tautology gate.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-05-verifier-runner.md. Committed alone, before any
implementation exists, per the project's red-then-green contract.

Run against the committed fixture target (`fixture_target`, see
tests/conftest.py) whose graph contains `OrderRepository` (repository.py:6),
`SpecialOrder(OrderRepository)` (orders.py:6) and `OrderRepository.get`
(repository.py:15).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from seshat.graph import Graph
from seshat.ledger.models import Claim, Unit, Verifier
from seshat.ledger.store import Ledger
from seshat.verify import VerifierResult, is_tautological, run_verifier, verify_and_record

SUBCLASSES_SOURCE = """
def check(graph):
    return [n.qualified_name for n in graph.subclasses('OrderRepository')]
"""

NO_CHECK_SOURCE = """
def not_check(graph):
    return 1
"""


def _import_os_source(marker_path: Path) -> str:
    """`import os` source that writes to `marker_path` if the import gate fails to stop it.

    `marker_path` must be interpolated per-test (from `tmp_path`) rather than a
    fixed shared path: a fixed path in `/tmp` collides across concurrent runs
    and a stale marker left by a crashed run makes a later run fail
    confusingly for a reason unrelated to the import gate.
    """
    return f"""
import os

def check(graph):
    os.system('echo pwned > {marker_path}')
    return True
"""


RAISES_SOURCE = """
def check(graph):
    graph.callers('OrderRepository.get')
    raise ValueError('boom')
"""

TAUTOLOGICAL_SOURCE = """
def check(graph):
    n = graph.node('OrderRepository.get')
    return n.qualified_name if n else None
"""


@pytest.fixture
def graph(fixture_target: Path) -> Iterator[Graph]:
    g = Graph.open(fixture_target)
    yield g
    g.close()


# --- bullet 1/2: graph.subclasses with matching expected -> pass ---


def test_subclasses_matching_expected_passes(graph: Graph):
    expected = json.dumps(['SpecialOrder'])
    result = run_verifier(SUBCLASSES_SOURCE, expected, graph, unit_qualified_name='OrderRepository')
    assert result.status == 'pass'


# --- bullet 2: wrong expected -> fail with actual filled ---


def test_subclasses_wrong_expected_fails_with_actual(graph: Graph):
    expected = json.dumps(['NotARealSubclass'])
    result = run_verifier(SUBCLASSES_SOURCE, expected, graph, unit_qualified_name='OrderRepository')
    assert result.status == 'fail'
    assert result.actual == ['SpecialOrder']


# --- bullet 3: source without check -> error ---


def test_source_without_check_errors(graph: Graph):
    result = run_verifier(NO_CHECK_SOURCE, json.dumps(None), graph, unit_qualified_name='OrderRepository')
    assert result.status == 'error'


# --- bullet 4: import os -> error, and os never runs ---


def test_import_os_errors_before_execution(graph: Graph, tmp_path: Path):
    marker = tmp_path / 'pwned-marker'
    source = _import_os_source(marker)
    result = run_verifier(source, json.dumps(True), graph, unit_qualified_name='OrderRepository')
    assert result.status == 'error'
    assert result.error is not None
    assert 'import' in result.error.lower()
    assert not marker.exists(), 'os.system ran: the import gate did not stop execution'


# --- fix round 2, item 1: builtins allow-list, not the real `__builtins__` module ---


def test_dunder_import_builtin_does_not_pass_and_marker_never_written(graph: Graph, tmp_path: Path):
    """No literal `import` statement here — `__import__` is a name, not a statement,
    so the ast-based import gate cannot see it. This is the exact bypass a reviewer
    demonstrated against the pre-fix code: `_build_namespace` handed the real
    `__builtins__` module into the exec namespace, so `__import__('os').system(...)`
    ran and `run_verifier` reported a clean `pass`. The fix is an explicit allow-list
    of builtins that does not include `__import__`, so this now fails before
    `os.system` ever runs.
    """
    marker = tmp_path / 'pwned-marker-dunder-import'
    source = f"""
def check(graph):
    graph.subclasses('OrderRepository')
    __import__('os').system('echo pwned > {marker}')
    return True
"""
    result = run_verifier(source, json.dumps(True), graph, unit_qualified_name='OrderRepository')
    assert result.status != 'pass', 'arbitrary code execution must never be reported as a passing verification'
    assert not marker.exists(), 'os.system ran: __import__ reached the real builtins module'


def test_dunder_traversal_escape_is_a_known_accepted_gap_not_correct_behaviour(graph: Graph):
    """This test documents a limitation, it does not assert correct behaviour.

    The builtins allow-list and the import gate close direct routes
    (`__import__`, `open`, `eval`, `exec`, `compile`) but cannot close
    attribute-traversal escapes that reach a live module without going
    through any builtin at all — here, `json`'s own loader object's class's
    `__init__`'s `__globals__` dict, which contains the running interpreter's
    `sys` module. Closing this requires process isolation, deferred to
    phase 1.5 (see the `verify.py` module docstring and DEC-1). If this test
    starts failing, the gap has closed and those two places should be
    updated to say so — this test is not the thing to fix to make it pass.
    """
    source = """
def check(graph):
    graph.subclasses('OrderRepository')
    sys_module = json.__loader__.__class__.__init__.__globals__['sys']
    return sys_module.__name__
"""
    result = run_verifier(source, json.dumps('sys'), graph, unit_qualified_name='OrderRepository')
    assert result.status == 'pass', 'documents a known gap: dunder-traversal reaches sys without any builtin'


# --- fix round 2, item 2: sets are order-independent, lists/tuples are not ---


def test_set_actual_passes_regardless_of_iteration_order(graph: Graph):
    """A verifier returning a `set` is making no claim about order at all — the task
    contract is "lists sorted where they were sets". `expected` is authored in this
    module's own canonical sorted order (`_canonical_sort_key`, a `json.dumps(...,
    sort_keys=True)` string) so the comparison is stable regardless of the set's
    actual (unspecified, not-guaranteed-stable-across-runs) iteration order.
    """
    source = """
def check(graph):
    graph.subclasses('OrderRepository')
    return {'zzz', 'aaa', 'mmm'}
"""
    expected = json.dumps(sorted(['zzz', 'aaa', 'mmm']))
    result = run_verifier(source, expected, graph, unit_qualified_name='OrderRepository')
    assert result.status == 'pass'


def test_list_actual_is_order_sensitive_and_fails_on_reordering(graph: Graph):
    """A verifier returning a `list`/`tuple` may be making a claim that genuinely
    depends on order (e.g. "the first caller is X"). Round 1 sorted every list
    unconditionally, which made this silently `pass` regardless of the claimed
    order — this is the regression test for that: same elements, different order,
    must `fail`, not `pass`.
    """
    source = """
def check(graph):
    graph.subclasses('OrderRepository')
    return ['first', 'second', 'third']
"""
    expected = json.dumps(['third', 'second', 'first'])
    result = run_verifier(source, expected, graph, unit_qualified_name='OrderRepository')
    assert result.status == 'fail'
    assert result.actual == ['first', 'second', 'third']


# --- bullet 5: source raising -> error with exception text ---


def test_raising_source_errors_with_exception_text(graph: Graph):
    result = run_verifier(RAISES_SOURCE, json.dumps(None), graph, unit_qualified_name='OrderRepository')
    assert result.status == 'error'
    assert result.error is not None
    assert 'boom' in result.error


# --- bullet 6: tautological verifier -> error mentioning tautology ---


def test_tautological_verifier_errors(graph: Graph):
    result = run_verifier(
        TAUTOLOGICAL_SOURCE,
        json.dumps('OrderRepository.get'),
        graph,
        unit_qualified_name='OrderRepository.get',
    )
    assert result.status == 'error'
    assert result.error is not None
    assert 'tautology' in result.error.lower()


def test_is_tautological_detects_graph_node_only_call():
    reason = is_tautological(TAUTOLOGICAL_SOURCE, 'OrderRepository.get')
    assert reason is not None
    assert 'tautology' in reason.lower()


def test_is_tautological_detects_non_literal_node_argument_fails_closed():
    """`graph.node(f'...')` (or any other non-literal argument) evades the literal-string
    match this gate used to rely on exclusively — an f-string built from the exact
    unit name looks, to a naive literal check, like "not calling graph.node on the
    unit", when it is exactly that call in disguise. Unknown fails closed: a
    non-literal argument must not be assumed safe.
    """
    source = """
def check(graph):
    n = graph.node(f'{"OrderRepository.get"}')
    return n.qualified_name if n else None
"""
    reason = is_tautological(source, 'OrderRepository.get')
    assert reason is not None


def test_run_verifier_non_literal_node_argument_errors(graph: Graph):
    source = """
def check(graph):
    n = graph.node(f'{"OrderRepository.get"}')
    return n.qualified_name if n else None
"""
    result = run_verifier(
        source,
        json.dumps('OrderRepository.get'),
        graph,
        unit_qualified_name='OrderRepository.get',
    )
    assert result.status == 'error'
    assert result.status != 'pass'


def test_is_tautological_detects_no_graph_call_at_all():
    source = """
def check(graph):
    return 1
"""
    reason = is_tautological(source, 'OrderRepository.get')
    assert reason is not None


# --- fix round 3, item 1: only graph.node(...) is unprovable; other methods are not ---


TWO_STEP_LOOKUP_SOURCE = """
def check(graph):
    subs = graph.subclasses('OrderRepository')
    return [graph.node(s.qualified_name).kind for s in subs]
"""


def test_two_step_lookup_is_not_tautological():
    """`graph.subclasses('OrderRepository')` is a literal-argument call to a method
    other than `node`, which proves real work by construction regardless of what
    the *following* `graph.node(s.qualified_name)` call's (non-literal) argument is.
    Round 2's fix over-corrected: it made *any* non-literal graph-call argument
    fail closed, which rejected this perfectly ordinary two-step lookup outright.
    """
    reason = is_tautological(TWO_STEP_LOOKUP_SOURCE, 'OrderRepository')
    assert reason is None


def test_run_verifier_two_step_lookup_passes(graph: Graph):
    result = run_verifier(TWO_STEP_LOOKUP_SOURCE, json.dumps(['class']), graph, unit_qualified_name='OrderRepository')
    assert result.status != 'error', 'a genuine two-step lookup must not be rejected as tautological'
    assert result.status == 'pass'


def test_lone_non_literal_node_call_still_fails_closed():
    """The other direction of the same fix: a verifier whose *only* graph call is
    `graph.node(...)` with a non-literal argument still proves nothing and must
    still be rejected — round 3 only stops a non-literal `node` call from
    poisoning an *otherwise* real-angle verifier, it does not make an unprovable
    lookup into proof of real work on its own.
    """
    source = """
def check(graph):
    n = graph.node(f'{"OrderRepository"}')
    return n.qualified_name if n else None
"""
    reason = is_tautological(source, 'OrderRepository')
    assert reason is not None


# --- bullet 7: same source for a different unit name -> not tautological ---


def test_tautological_source_for_different_unit_is_not_tautological():
    reason = is_tautological(TAUTOLOGICAL_SOURCE, 'SomeOtherUnit')
    assert reason is None


def test_run_verifier_not_tautological_for_different_unit(graph: Graph):
    result = run_verifier(
        TAUTOLOGICAL_SOURCE,
        json.dumps('OrderRepository.get'),
        graph,
        unit_qualified_name='SpecialOrder',
    )
    assert result.status == 'pass'


# --- bullet 8: verify_and_record writes last_status/last_run on the row ---


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'target-repo'
    repo.mkdir()
    return repo


def test_verify_and_record_writes_last_status_and_last_run(graph: Graph, tmp_repo: Path):
    ledger = Ledger.open(tmp_repo)
    try:
        run = ledger.create_run()
        unit = ledger.upsert_unit(
            Unit(
                id='unit-1',
                repo_id='',
                file_path='demo/repository.py',
                qualified_name='OrderRepository',
                kind='class',
                start_line=6,
                end_line=21,
                ast_hash='deadbeef',
                inbound_calls=0,
                first_seen_run=run.id,
                last_seen_run=run.id,
                last_scanned_run=run.id,
                status='scanned',
            ),
            run.id,
        )
        claim = ledger.add_claim(
            Claim(
                id='',
                repo_id='',
                unit_id=unit.id,
                text='OrderRepository has one subclass.',
                kind='structural',
                source='code',
                mode='claims',
                status='conjectured',
                confidence=0.9,
                candidate_rule=0,
                rule_sightings=0,
                created_run=run.id,
                verified_run=None,
                verified_sha=None,
                retries=0,
            )
        )
        verifier = Verifier(
            id='',
            repo_id='',
            claim_id=claim.id,
            source=SUBCLASSES_SOURCE,
            expected=json.dumps(['SpecialOrder']),
            depends_on=[],
            last_run=None,
            last_status=None,
            last_error=None,
        )
        stored = ledger.add_verifier(verifier)

        result = verify_and_record(ledger, stored, graph, run.id)

        assert isinstance(result, VerifierResult)
        assert result.status == 'pass'

        row = ledger.conn.execute('SELECT last_status, last_run FROM verifiers WHERE id = ?', (stored.id,)).fetchone()
        assert row['last_status'] == 'pass'
        assert row['last_run'] == run.id
    finally:
        ledger.close()
