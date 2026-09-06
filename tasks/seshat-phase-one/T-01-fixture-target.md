---
id: T-01
plan: seshat-phase-one
title: Fixture target repo with committed codegraph index
status: todo
depends_on: []
files:
  - tests/fixtures/target/**
  - tests/fixtures/target/.codegraph/codegraph.db
  - tests/fixtures/REBUILD.md
  - tests/conftest.py
  - tests/test_fixture_target.py
rules: []
---

## Goal

A small hand-written Python repo under `tests/fixtures/target/`, with its
`.codegraph/codegraph.db` committed beside it, so every later task can open a real
code graph read-only in tests with no Node runtime and no MCP daemon. This is the
target every acceptance test in the plan runs against.

## Scope

1. Create `tests/fixtures/target/` as a runnable-looking Python package `demo/` with
   a `README.md`. It must contain, across at least three files:
   - a class with two methods, one of which calls the other;
   - a subclass of that class (`extends` edge);
   - a custom exception class;
   - a module-level function decorated with a stdlib decorator
     (`functools.lru_cache`), and one decorated with a decorator defined in the repo;
   - a function that calls a stdlib function (`json.dumps`) so `unresolved_refs`
     is non-empty;
   - cross-file imports so at least two `imports` edges exist;
   - a function that is called from two different files (so `inbound_calls ≥ 2`).
   Keep it under 150 lines total. Names must be distinctive
   (`OrderRepository`, `OrderNotFound`, `SpecialOrder`, `render_receipt`, …) so
   later tests can assert on them.
2. Write one README statement that is true of the code (e.g. "`OrderRepository.get`
   raises `OrderNotFound` for an unknown id") and one that is false, marked with a
   comment `<!-- deliberately false -->`. Later tasks use these as doc seeds.
3. Run `CODEGRAPH_TELEMETRY=0 codegraph init tests/fixtures/target` and commit the
   resulting `.codegraph/codegraph.db`. Remove any other file codegraph writes
   (config, gitignore edits) that is not needed to open the DB.
4. Ensure the repo `.gitignore` does not exclude `tests/fixtures/target/.codegraph/`.
5. Write `tests/fixtures/REBUILD.md`: the exact command to rebuild the index and the
   rule that the source and the DB are committed together.
6. Add a `fixture_target` session fixture in `tests/conftest.py` returning the
   absolute `Path` of the fixture repo, and `fixture_graph_db` returning the DB path.

## Non-scope

- No `seshat` code. No graph helper API. Do not write a wrapper over the DB.
- Do not make the fixture large or realistic. It is a probe, not a demo app.
- Do not add codegraph to CI.

## Acceptance

- `uv run pytest tests/test_fixture_target.py -q` → exit 0, covers:
  - the DB opens with `sqlite3.connect('file:…?mode=ro', uri=True)`;
  - tables `nodes`, `edges`, `files`, `unresolved_refs` exist;
  - at least 8 nodes with kind in {class, function, method};
  - at least one edge of each kind in {calls, imports, extends};
  - at least one `unresolved_refs` row;
  - every `files` row's path exists on disk under the fixture root.
- `git ls-files tests/fixtures/target/.codegraph/codegraph.db` → prints the path
  (it is tracked).
- `make check` → exit 0

## Context

- Codegraph schema facts (`decisions.md`, "Facts gathered"): tables `nodes`, `edges`,
  `files`, `unresolved_refs`, `nodes_fts`. Edge kinds: contains, calls, instantiates,
  references, imports, extends, decorates. Python decorators are known to come back
  empty; do not try to fix that here, just include decorated functions so T-04 can
  test its fallback.
- Codegraph is installed in this container at `~/.local/bin/codegraph`. Set
  `CODEGRAPH_TELEMETRY=0` whenever you run it.
- Inspect the DB with `sqlite3` after init and put the actual column names you find
  into `REBUILD.md` as a short table. T-04's builder will read it.

## Manual QA

Open `tests/fixtures/target/README.md` and confirm the false statement is marked.
