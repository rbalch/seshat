"""Acceptance tests for T-01: the fixture target repo and its committed code graph.

These assert the boundary the task promises later tasks: a real, read-only-openable
codegraph DB, committed beside the source it describes, with enough shape (node
kinds, edge kinds, an unresolved ref, files that exist on disk) that T-04's graph
helper API has something real to read in tests.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)


def test_db_opens_read_only(fixture_graph_db: Path) -> None:
    conn = _connect_ro(fixture_graph_db)
    try:
        conn.execute('select 1').fetchone()
    finally:
        conn.close()


def test_expected_tables_exist(fixture_graph_db: Path) -> None:
    conn = _connect_ro(fixture_graph_db)
    try:
        rows = conn.execute("select name from sqlite_master where type = 'table'").fetchall()
        table_names = {row[0] for row in rows}
    finally:
        conn.close()

    for expected in ('nodes', 'edges', 'files', 'unresolved_refs'):
        assert expected in table_names, f'missing table {expected!r}: found {table_names}'


def test_at_least_eight_class_function_method_nodes(fixture_graph_db: Path) -> None:
    conn = _connect_ro(fixture_graph_db)
    try:
        count = conn.execute("select count(*) from nodes where kind in ('class', 'function', 'method')").fetchone()[0]
    finally:
        conn.close()

    assert count >= 8, f'expected at least 8 class/function/method nodes, found {count}'


@pytest.mark.parametrize('edge_kind', ['calls', 'imports', 'extends'])
def test_at_least_one_edge_of_each_kind(fixture_graph_db: Path, edge_kind: str) -> None:
    conn = _connect_ro(fixture_graph_db)
    try:
        count = conn.execute('select count(*) from edges where kind = ?', (edge_kind,)).fetchone()[0]
    finally:
        conn.close()

    assert count >= 1, f'expected at least one {edge_kind!r} edge, found {count}'


def test_at_least_one_unresolved_ref(fixture_graph_db: Path) -> None:
    conn = _connect_ro(fixture_graph_db)
    try:
        count = conn.execute('select count(*) from unresolved_refs').fetchone()[0]
    finally:
        conn.close()

    assert count >= 1, 'expected at least one unresolved_refs row'


def test_every_files_row_exists_on_disk(fixture_target: Path, fixture_graph_db: Path) -> None:
    conn = _connect_ro(fixture_graph_db)
    try:
        rows = conn.execute('select path from files').fetchall()
    finally:
        conn.close()

    assert rows, 'expected at least one row in files'
    for (path,) in rows:
        candidate = Path(path)
        resolved = candidate if candidate.is_absolute() else fixture_target / candidate
        assert resolved.exists(), f'files row path does not exist on disk: {path!r}'


def test_db_is_tracked_in_git(fixture_graph_db: Path) -> None:
    import subprocess

    repo_root = Path(__file__).parent.parent
    result = subprocess.run(
        ['git', 'ls-files', str(fixture_graph_db.relative_to(repo_root))],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip(), 'codegraph.db is not tracked by git'
