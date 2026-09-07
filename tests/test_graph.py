"""Acceptance tests for T-04: the graph helper API.

These run against the committed fixture target's codegraph DB (`fixture_target`,
see `tests/conftest.py` and `tests/fixtures/REBUILD.md`) and assert the boundary
`seshat.graph.Graph` promises every later task: everything above this module
reads the code graph only through it, identity is `(file_path, qualified_name)`,
and no codegraph node id ever leaks into a return value.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from seshat.graph import Graph, GraphNotIndexed, Node


@pytest.fixture
def graph(fixture_target: Path) -> Iterator[Graph]:
    g = Graph.open(fixture_target)
    yield g
    g.close()


def _build_synthetic_repo(
    tmp_path: Path,
    *,
    nodes: list[tuple[str, str, str, str, str, int, int]],
    edges: list[tuple[str, str, str, int | None]],
    source_files: dict[str, str] | None = None,
) -> Path:
    """A throwaway repo with a minimal hand-built codegraph.db.

    Used for scenarios the committed fixture cannot represent (duplicate edges,
    a decorated class) without desynchronising `tests/fixtures/target/` from its
    committed, line-exact index — see `tests/fixtures/REBUILD.md`. Schema is the
    subset of `nodes`/`edges` columns `seshat.graph` actually reads (see
    `tests/fixtures/REBUILD.md` for the real codegraph schema this mirrors).

    `nodes` rows are `(id, kind, name, qualified_name, file_path, start_line,
    end_line)`; `edges` rows are `(source, target, kind, line)`.
    """
    codegraph_dir = tmp_path / '.codegraph'
    codegraph_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(codegraph_dir / 'codegraph.db'))
    try:
        conn.executescript(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                kind TEXT,
                name TEXT,
                qualified_name TEXT,
                file_path TEXT,
                start_line INTEGER,
                end_line INTEGER
            );
            CREATE TABLE edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                target TEXT,
                kind TEXT,
                line INTEGER
            );
            """
        )
        conn.executemany(
            'INSERT INTO nodes (id, kind, name, qualified_name, file_path, start_line, end_line) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            nodes,
        )
        conn.executemany(
            'INSERT INTO edges (source, target, kind, line) VALUES (?, ?, ?, ?)',
            edges,
        )
        conn.commit()
    finally:
        conn.close()

    for relative_path, content in (source_files or {}).items():
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    return tmp_path


def test_open_raises_when_not_indexed(tmp_path: Path) -> None:
    with pytest.raises(GraphNotIndexed) as excinfo:
        Graph.open(tmp_path)
    assert str(tmp_path) in str(excinfo.value)


def test_node_dataclass_has_exactly_five_fields() -> None:
    assert set(Node.__dataclass_fields__.keys()) == {
        'qualified_name',
        'file_path',
        'kind',
        'start_line',
        'end_line',
    }


def test_node_normalizes_double_colon_and_dot_to_same_node(graph: Graph) -> None:
    dotted = graph.node('OrderRepository.get')
    colon = graph.node('OrderRepository::get')

    assert dotted is not None
    assert colon is not None
    assert dotted == colon
    assert dotted.file_path == 'demo/repository.py'
    assert dotted.start_line < dotted.end_line


def test_node_returns_none_for_unknown_qualified_name(graph: Graph) -> None:
    assert graph.node('does.not.exist') is None


def test_callers_returns_nodes_in_two_different_files(graph: Graph) -> None:
    # render_receipt is called from print_receipt (demo/receipts.py) and main
    # (demo/main.py) — see tests/fixtures/REBUILD.md.
    callers = graph.callers('render_receipt')

    files = {node.file_path for node in callers}
    assert len(callers) == 2
    assert files == {'demo/receipts.py', 'demo/main.py'}


def test_callees_of_get_includes_get_or_raise(graph: Graph) -> None:
    callees = graph.callees('OrderRepository.get')

    names = {node.qualified_name for node in callees}
    assert 'OrderRepository._get_or_raise' in names


def test_subclasses_of_order_repository_includes_special_order(graph: Graph) -> None:
    subclasses = graph.subclasses('OrderRepository')

    names = {node.qualified_name for node in subclasses}
    assert 'SpecialOrder' in names


def test_decorators_of_lru_cache_function_falls_back_to_ast(graph: Graph) -> None:
    # format_currency is decorated with a bare `@lru_cache`; codegraph's own
    # `decorates` edges are empty for it (only `render_receipt -> logged` exists
    # in the fixture), so this exercises the ast fallback.
    decorators = graph.decorators('format_currency')

    assert 'lru_cache' in decorators


def test_external_refs_of_json_dumps_user_contains_dumps(graph: Graph) -> None:
    refs = graph.external_refs('render_receipt')

    assert any('dumps' in ref for ref in refs)


def test_imports_returns_cross_file_imports(graph: Graph) -> None:
    imported = graph.imports('demo/main.py')

    assert 'demo/repository.py' in imported
    assert 'demo/receipts.py' in imported
    assert 'demo/orders.py' in imported


def test_search_returns_nodes(graph: Graph) -> None:
    # A search() that ignored its query and returned every node would still
    # pass a bare "returns nodes" assertion, so this also pins the query to
    # actually filter: `logged` (demo/decorators.py) has no "order" anywhere in
    # its name, qualified name, docstring, or signature, and must not show up.
    results = graph.search('Order')

    assert results
    assert all(isinstance(node, Node) for node in results)
    names = {node.qualified_name for node in results}
    assert 'logged' not in names


def test_files_glob_returns_fixture_module_paths(graph: Graph) -> None:
    paths = graph.files('demo/*.py')

    assert 'demo/repository.py' in paths
    assert 'demo/receipts.py' in paths
    assert 'demo/orders.py' in paths
    assert 'demo/main.py' in paths
    assert all(path.startswith('demo/') and path.endswith('.py') for path in paths)


# -- regression: duplicate edges must not duplicate the Node identity --------
#
# codegraph records one `calls`/`extends` edge per call site or declaration, so
# a caller that invokes the target twice (or, in principle, an `extends` edge
# recorded more than once) produces two edges between the same pair of nodes.
# The fixture target has zero duplicate edges (see tests/fixtures/REBUILD.md),
# so these scenarios are built on a throwaway synthetic repo instead.


def test_callers_dedupes_multiple_call_sites_to_same_target(tmp_path: Path) -> None:
    repo = _build_synthetic_repo(
        tmp_path,
        nodes=[
            ('function:caller', 'function', 'caller', 'caller', 'a.py', 1, 5),
            ('function:callee', 'function', 'callee', 'callee', 'b.py', 1, 5),
        ],
        edges=[
            # Two call sites inside `caller`, same edge kind and pair, different
            # `line` — exactly what codegraph does for repeated calls.
            ('function:caller', 'function:callee', 'calls', 2),
            ('function:caller', 'function:callee', 'calls', 3),
        ],
    )
    with Graph.open(repo) as g:
        callers = g.callers('callee')

    assert len(callers) == 1
    assert callers[0].qualified_name == 'caller'


def test_callees_dedupes_multiple_call_sites_to_same_target(tmp_path: Path) -> None:
    repo = _build_synthetic_repo(
        tmp_path,
        nodes=[
            ('function:caller', 'function', 'caller', 'caller', 'a.py', 1, 5),
            ('function:callee', 'function', 'callee', 'callee', 'b.py', 1, 5),
        ],
        edges=[
            ('function:caller', 'function:callee', 'calls', 2),
            ('function:caller', 'function:callee', 'calls', 3),
        ],
    )
    with Graph.open(repo) as g:
        callees = g.callees('caller')

    assert len(callees) == 1
    assert callees[0].qualified_name == 'callee'


def test_subclasses_dedupes_multiple_extends_edges(tmp_path: Path) -> None:
    repo = _build_synthetic_repo(
        tmp_path,
        nodes=[
            ('class:base', 'class', 'Base', 'Base', 'a.py', 1, 5),
            ('class:child', 'class', 'Child', 'Child', 'b.py', 1, 5),
        ],
        edges=[
            ('class:child', 'class:base', 'extends', None),
            ('class:child', 'class:base', 'extends', None),
        ],
    )
    with Graph.open(repo) as g:
        subclasses = g.subclasses('Base')

    assert len(subclasses) == 1
    assert subclasses[0].qualified_name == 'Child'


def test_inbound_call_count_counts_distinct_callers_not_call_sites(tmp_path: Path) -> None:
    repo = _build_synthetic_repo(
        tmp_path,
        nodes=[
            ('function:caller', 'function', 'caller', 'caller', 'a.py', 1, 5),
            ('function:callee', 'function', 'callee', 'callee', 'b.py', 1, 5),
        ],
        edges=[
            ('function:caller', 'function:callee', 'calls', 2),
            ('function:caller', 'function:callee', 'calls', 3),
        ],
    )
    with Graph.open(repo) as g:
        count = g.inbound_call_count('callee')

    assert count == 1


# -- regression: the ast fallback must handle decorated classes, not just defs --


def test_decorators_of_decorated_class_uses_ast_fallback(tmp_path: Path) -> None:
    source = 'def decorator(cls):\n    return cls\n\n\n@decorator\nclass Widget:\n    pass\n'
    repo = _build_synthetic_repo(
        tmp_path,
        nodes=[
            ('class:widget', 'class', 'Widget', 'Widget', 'mod.py', 6, 7),
        ],
        edges=[],
        source_files={'mod.py': source},
    )
    with Graph.open(repo) as g:
        decorators = g.decorators('Widget')

    assert decorators == ['decorator']


# -- coverage for the decorates-edge branch and the T-06 enumeration methods --


def test_decorators_uses_decorates_edge_when_present(graph: Graph) -> None:
    # render_receipt is decorated with the in-repo `logged` decorator, which
    # codegraph does record a `decorates` edge for (unlike the bare stdlib
    # `@lru_cache` case, which never gets an edge and always uses the ast
    # fallback) — see tests/fixtures/REBUILD.md. This exercises the edge branch
    # of decorators() instead of the fallback.
    decorators = graph.decorators('render_receipt')

    assert decorators == ['logged']


def test_nodes_filters_by_kind(graph: Graph) -> None:
    classes = graph.nodes(kinds=['class'])

    assert classes
    assert all(node.kind == 'class' for node in classes)
    names = {node.qualified_name for node in classes}
    assert 'OrderRepository' in names
    assert 'SpecialOrder' in names


def test_nodes_maps_file_kind_to_module(graph: Graph) -> None:
    modules = graph.nodes(kinds=['module'])

    assert modules
    assert all(node.kind == 'module' for node in modules)


def test_inbound_call_count_pins_known_fixture_value(graph: Graph) -> None:
    # render_receipt has exactly two distinct callers in the fixture —
    # print_receipt (demo/receipts.py) and main (demo/main.py), see
    # tests/fixtures/REBUILD.md and test_callers_returns_nodes_in_two_different_files.
    # Pinned to that known value rather than to callers() itself: asserting
    # inbound_call_count() against len(callers()) is tautological, since
    # inbound_call_count() is implemented as len(self.callers(...)) — it would
    # pass even if both were wrong together.
    assert graph.inbound_call_count('render_receipt') == 2
    # Still worth checking the two stay consistent with each other.
    assert graph.inbound_call_count('render_receipt') == len(graph.callers('render_receipt'))


def test_nodes_breaks_ties_on_normalized_qualified_name(tmp_path: Path) -> None:
    # Two nodes sharing (file_path, start_line): without a tiebreak, ORDER BY
    # file_path, start_line leaves them in whatever order the table scan
    # produces, which for a plain rowid table is insertion order. Insert them
    # in the "wrong" order relative to their alphabetical qualified names —
    # `Zebra::foo` (normalizes to `Zebra.foo`) before `Apple` — so that if the
    # tiebreak is missing or compares the raw `::`-form column instead of the
    # normalized name, the physical (insertion) order survives and the
    # assertion below fails.
    repo = _build_synthetic_repo(
        tmp_path,
        nodes=[
            ('method:zebra_foo', 'method', 'foo', 'Zebra::foo', 'a.py', 10, 20),
            ('class:apple', 'class', 'Apple', 'Apple', 'a.py', 10, 20),
        ],
        edges=[],
    )
    with Graph.open(repo) as g:
        names = [node.qualified_name for node in g.nodes()]

    assert names == ['Apple', 'Zebra.foo']
