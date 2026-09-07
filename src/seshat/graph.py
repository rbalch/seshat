"""The graph helper API. The one way any Seshat code reads a target's code graph.

Verifiers, workers, and everything above them read `.codegraph/codegraph.db` only
through `Graph` — never through codegraph's own tables — because codegraph's node
ids hash line numbers and churn on any edit above a symbol. Identity here is
`(file_path, qualified_name)` instead, and codegraph's `Class::method` separator is
normalized to `Class.method` on the way out and accepted in either form on the way
in, so the backend can change without rewriting anything above this module. See
AGENTS.md and tasks/seshat-phase-one/T-04-graph-helper-api.md.
"""

from __future__ import annotations

import ast
import fnmatch
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Self


class GraphNotIndexed(Exception):
    """Raised when `Graph.open` is given a repo with no `.codegraph/codegraph.db`."""


# codegraph's own node `kind` values that are not one of Node's four kinds. `file`
# maps to `module`; `import` nodes are never surfaced as a `Node` at all.
_DB_KIND_TO_NODE_KIND = {'file': 'module'}
_NODE_KIND_TO_DB_KIND = {'module': 'file'}


def _normalize_qname(qualified_name: str) -> str:
    """The one place `Class::method` becomes `Class.method`.

    Used both to normalize a `Node.qualified_name` read out of the DB and to
    normalize a caller-supplied qualified name before it is compared (via SQL
    `REPLACE`) against codegraph's own `::`-separated column, so both forms are
    accepted on the way in and only the dotted form is ever returned.
    """
    return qualified_name.replace('::', '.')


@dataclass(frozen=True)
class Node:
    qualified_name: str
    file_path: str
    kind: str
    start_line: int
    end_line: int


def _row_to_node(row: sqlite3.Row) -> Node:
    kind = _DB_KIND_TO_NODE_KIND.get(row['kind'], row['kind'])
    return Node(
        qualified_name=_normalize_qname(row['qualified_name']),
        file_path=row['file_path'],
        kind=kind,
        start_line=row['start_line'],
        end_line=row['end_line'],
    )


def _decorator_name(decorator: ast.expr) -> str:
    """Reconstruct a decorator's name as written, stripping call arguments.

    `@lru_cache` and `@lru_cache(maxsize=8)` both yield `lru_cache`;
    `@functools.lru_cache` yields `functools.lru_cache`.
    """
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return ast.unparse(target)


def _find_def(body: list[ast.stmt], parts: list[str]) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None:
    """Walk `body` following dotted `parts` (e.g. `['OrderRepository', 'get']`).

    `parts` may terminate on a class itself (`['Widget']`) as well as on a
    function or a method inside a class — a decorated class must not be
    silently reported as having no decorators just because `Node.kind` for a
    class and a def share this one lookup path.
    """
    name, rest = parts[0], parts[1:]
    for stmt in body:
        if isinstance(stmt, ast.ClassDef) and stmt.name == name:
            if not rest:
                return stmt
            return _find_def(stmt.body, rest)
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == name:
            if not rest:
                return stmt
            return _find_def(stmt.body, rest)
    return None


@dataclass
class Graph:
    _conn: sqlite3.Connection
    repo_root: Path

    # -- lifecycle -----------------------------------------------------

    @classmethod
    def open(cls, repo_path: Path) -> Self:
        resolved = Path(repo_path).resolve()
        db_path = resolved / '.codegraph' / 'codegraph.db'
        if not db_path.exists():
            raise GraphNotIndexed(f'no codegraph index at {db_path}: run `codegraph init` first')

        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        return cls(_conn=conn, repo_root=resolved)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- lookups ---------------------------------------------------------

    def node(self, qualified_name: str, file_path: str | None = None) -> Node | None:
        qn = _normalize_qname(qualified_name)
        query = "SELECT * FROM nodes WHERE REPLACE(qualified_name, '::', '.') = ? AND kind != 'import'"
        params: list[object] = [qn]
        if file_path is not None:
            query += ' AND file_path = ?'
            params.append(file_path)
        query += " ORDER BY file_path, start_line, REPLACE(qualified_name, '::', '.') LIMIT 1"
        row = self._conn.execute(query, params).fetchone()
        return _row_to_node(row) if row is not None else None

    def nodes(self, kinds: Iterable[str] | None = None) -> list[Node]:
        query = "SELECT * FROM nodes WHERE kind != 'import'"
        params: list[object] = []
        if kinds is not None:
            db_kinds = [_NODE_KIND_TO_DB_KIND.get(kind, kind) for kind in kinds]
            placeholders = ','.join('?' for _ in db_kinds)
            query += f' AND kind IN ({placeholders})'
            params.extend(db_kinds)
        query += " ORDER BY file_path, start_line, REPLACE(qualified_name, '::', '.')"
        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_node(row) for row in rows]

    # -- calls -------------------------------------------------------------

    def callers(self, qualified_name: str) -> list[Node]:
        # DISTINCT: codegraph records one `calls` edge per call site, so a
        # caller that invokes the target more than once produces more than one
        # edge between the same pair of nodes. Without it the same Node comes
        # back once per call site, inflating anything that counts callers.
        qn = _normalize_qname(qualified_name)
        rows = self._conn.execute(
            """
            SELECT DISTINCT src.* FROM edges e
            JOIN nodes src ON src.id = e.source
            JOIN nodes tgt ON tgt.id = e.target
            WHERE e.kind = 'calls' AND REPLACE(tgt.qualified_name, '::', '.') = ?
            ORDER BY src.file_path, src.start_line, REPLACE(src.qualified_name, '::', '.')
            """,
            (qn,),
        ).fetchall()
        return [_row_to_node(row) for row in rows]

    def callees(self, qualified_name: str) -> list[Node]:
        # See `callers` — the same one-edge-per-call-site fact applies in the
        # other direction.
        qn = _normalize_qname(qualified_name)
        rows = self._conn.execute(
            """
            SELECT DISTINCT tgt.* FROM edges e
            JOIN nodes src ON src.id = e.source
            JOIN nodes tgt ON tgt.id = e.target
            WHERE e.kind = 'calls' AND REPLACE(src.qualified_name, '::', '.') = ?
            ORDER BY tgt.file_path, tgt.start_line, REPLACE(tgt.qualified_name, '::', '.')
            """,
            (qn,),
        ).fetchall()
        return [_row_to_node(row) for row in rows]

    def inbound_call_count(self, qualified_name: str) -> int:
        """Count of distinct callers, not call sites — matches `callers()`."""
        return len(self.callers(qualified_name))

    # -- structure ---------------------------------------------------------

    def subclasses(self, qualified_name: str) -> list[Node]:
        # DISTINCT for the same reason as `callers`: nothing rules out more
        # than one `extends` edge being recorded between the same pair.
        qn = _normalize_qname(qualified_name)
        rows = self._conn.execute(
            """
            SELECT DISTINCT src.* FROM edges e
            JOIN nodes src ON src.id = e.source
            JOIN nodes tgt ON tgt.id = e.target
            WHERE e.kind = 'extends' AND REPLACE(tgt.qualified_name, '::', '.') = ?
            ORDER BY src.file_path, src.start_line, REPLACE(src.qualified_name, '::', '.')
            """,
            (qn,),
        ).fetchall()
        return [_row_to_node(row) for row in rows]

    def imports(self, file_path: str) -> list[str]:
        """Resolved file->file `imports` edges out of `file_path`."""
        rows = self._conn.execute(
            """
            SELECT DISTINCT tgt.file_path AS path FROM edges e
            JOIN nodes src ON src.id = e.source
            JOIN nodes tgt ON tgt.id = e.target
            WHERE e.kind = 'imports' AND src.kind = 'file' AND tgt.kind = 'file' AND src.file_path = ?
            ORDER BY path
            """,
            (file_path,),
        ).fetchall()
        return [row['path'] for row in rows]

    def external_refs(self, qualified_name: str) -> list[str]:
        """`unresolved_refs` (stdlib/third-party calls) inside the node's file/span."""
        n = self.node(qualified_name)
        if n is None:
            return []
        rows = self._conn.execute(
            """
            SELECT DISTINCT reference_name FROM unresolved_refs
            WHERE file_path = ? AND line BETWEEN ? AND ?
            ORDER BY reference_name
            """,
            (n.file_path, n.start_line, n.end_line),
        ).fetchall()
        return [row['reference_name'] for row in rows]

    def decorators(self, qualified_name: str) -> list[str]:
        """Codegraph's `decorates` edges first; fall back to parsing the source with `ast`."""
        qn = _normalize_qname(qualified_name)
        rows = self._conn.execute(
            """
            SELECT DISTINCT tgt.qualified_name AS qualified_name FROM edges e
            JOIN nodes src ON src.id = e.source
            JOIN nodes tgt ON tgt.id = e.target
            WHERE e.kind = 'decorates' AND REPLACE(src.qualified_name, '::', '.') = ?
            """,
            (qn,),
        ).fetchall()
        if rows:
            return sorted(_normalize_qname(row['qualified_name']) for row in rows)

        n = self.node(qualified_name)
        if n is None:
            return []
        source_path = self.repo_root / n.file_path
        tree = ast.parse(source_path.read_text())
        defn = _find_def(tree.body, qn.split('.'))
        if defn is None:
            return []
        return [_decorator_name(dec) for dec in defn.decorator_list]

    # -- search --------------------------------------------------------------

    def search(self, fts_query: str) -> list[Node]:
        # FTS5 phrase-quoting duplicated from seshat.ledger.store._fts_phrase:
        # graph.py sits below the helper API seam in AGENTS.md's architecture
        # diagram and must not import from seshat.ledger, so this stays copied
        # rather than shared.
        phrase = '"' + fts_query.replace('"', '""') + '"'
        rows = self._conn.execute(
            """
            SELECT n.* FROM nodes n
            JOIN nodes_fts f ON f.rowid = n.rowid
            WHERE nodes_fts MATCH ? AND n.kind != 'import'
            ORDER BY n.file_path, n.start_line, REPLACE(n.qualified_name, '::', '.')
            """,
            (phrase,),
        ).fetchall()
        return [_row_to_node(row) for row in rows]

    def files(self, glob: str) -> list[str]:
        rows = self._conn.execute('SELECT path FROM files').fetchall()
        return sorted(row['path'] for row in rows if fnmatch.fnmatch(row['path'], glob))
