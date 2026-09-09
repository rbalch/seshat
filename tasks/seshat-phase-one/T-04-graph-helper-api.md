---
id: T-04
plan: seshat-phase-one
title: Graph helper API with ast decorator fallback
depends_on: [T-01, T-02]
files:
  - src/seshat/graph.py
  - tests/test_graph.py
rules: []
---

## Goal

`seshat.graph.Graph` is the one way any Seshat code reads a target's code graph
(plan §6). Verifiers import only this module. Codegraph's table layout is hidden
behind it, so the backend can change without touching ledger rows.

## Scope

1. `Node` frozen dataclass: `qualified_name`, `file_path` (relative to repo root,
   posix), `kind` (`class | function | method | module`), `start_line`, `end_line`.
2. `Graph.open(repo_path: Path) -> Graph` opens `<repo>/.codegraph/codegraph.db`
   read-only (`mode=ro` URI). Raises `GraphNotIndexed` naming the path if absent.
3. Implement exactly the methods in plan §6 with those signatures: `node`,
   `callers`, `callees`, `imports`, `external_refs`, `subclasses`, `decorators`,
   `search`, `files`. Add `nodes(kinds: Iterable[str] | None = None) -> list[Node]`
   for T-06's enumeration, and `inbound_call_count(qualified_name) -> int`.
4. Name normalisation: codegraph's `Class::method` becomes `Class.method` on the
   way out, and either form is accepted on the way in. Identity is
   `(file_path, qualified_name)`; never expose codegraph node ids.
5. `decorators()` reads the graph's `decorates` edges first; when empty it falls
   back to parsing the file with the stdlib `ast` module, locating the def by
   qualified name, and returning the decorator names as written (`lru_cache`,
   `functools.lru_cache`, `traced`).
6. `external_refs()` reads `unresolved_refs` for the node's file/span.
7. Every method returns plain lists of `Node` or `str`, sorted by
   `(file_path, start_line)` so verifier `expected` JSON is stable.

## Non-scope

- No writes, no `codegraph init`, no MCP. No ledger. Verifier execution is T-05.
- Do not add language handling beyond Python.

## Acceptance

- `uv run pytest tests/test_graph.py -q` → exit 0, against `fixture_target`, covers:
  - `Graph.open` on a dir with no `.codegraph/` raises `GraphNotIndexed`;
  - `node('OrderRepository.get')` and `node('OrderRepository::get')` return the same
    `Node` with the fixture's file path and a line span where
    `start_line < end_line`;
  - `node('does.not.exist')` returns `None`;
  - `callers(<the function called from two files>)` returns two nodes in two
    different files;
  - `callees('OrderRepository.get')` includes the method it calls;
  - `subclasses('OrderRepository')` includes `SpecialOrder`;
  - `decorators(<lru_cache function>)` returns a list containing `lru_cache`
    (via the ast fallback, since codegraph returns none);
  - `external_refs(<function using json.dumps>)` contains a string with `dumps`;
  - `imports(<file>)` returns the fixture's cross-file imports;
  - `search('Order')` returns nodes and `files('demo/*.py')` returns the fixture's
    module paths;
  - the module does not import `sqlite3` row shapes into its public API: a test
    asserts `Node.__dataclass_fields__` keys equal the five in scope item 1.
- `make check` → exit 0

## Context

- plan §6 and §11 "Codegraph gaps". Decisions Q14, Q29. `AGENTS.md` architectural
  shape: everything above this module reads the graph through it.
- Read `tests/fixtures/REBUILD.md` for the actual column names in the fixture DB,
  then inspect with `sqlite3 tests/fixtures/target/.codegraph/codegraph.db '.schema'`.
- Node ids in codegraph hash line numbers; that is why nothing here exposes them.

## Manual QA

None.
