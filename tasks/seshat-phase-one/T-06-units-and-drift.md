---
id: T-06
plan: seshat-phase-one
title: Unit enumeration, ast_hash, drift diff
status: todo
depends_on: [T-03, T-04]
files:
  - src/seshat/units.py
  - tests/test_units.py
rules: []
---

## Goal

Steps 4 and 5 of the scanning loop (plan §5) as deterministic code: list every unit
in the target, hash its AST, upsert into the ledger, mark what changed or vanished,
mark their claims stale, and produce the ordered work queue. A rescan is
incremental because this task makes it so.

## Scope

1. `unit_id(file_path: str, qualified_name: str) -> str`: sha256 of
   `f'{file_path}\0{qualified_name}'`, first 32 hex chars.
2. `ast_hash(repo: Path, node: Node) -> str | None`: parse the file with `ast`,
   locate the def/class by qualified name (walk nested `ClassDef`/`FunctionDef`
   names joined with `.`; a `module` kind hashes the whole file), `ast.dump` it
   without attributes (no line numbers, no comments, no docstring changes counting
   only if you decide so and document it), sha256. `None` if the file or symbol is
   not there.
3. `enumerate_units(graph: Graph, repo: Path) -> list[Unit]`: one `Unit` per graph
   node of kind class/function/method, plus one `module` unit per Python file, with
   `inbound_calls` from `graph.inbound_call_count`.
4. `sync_units(ledger: Ledger, units: list[Unit], run_id) -> UnitDiff` where
   `UnitDiff(new, unchanged, changed, vanished: list[str])`:
   - new → insert `status='pending'`, `first_seen_run=last_seen_run=run_id`;
   - same hash → `last_seen_run=run_id`, status untouched;
   - hash differs → `status='changed'`;
   - in ledger, not in `units`, or `ast_hash` is `None` → `status='vanished'`;
   - for changed ∪ vanished: `ledger.mark_stale_for_units`.
5. `verifiers_to_rerun(ledger, diff, full: bool) -> list[Verifier]`:
   `ledger.verifiers_touching(changed ∪ vanished)`, or `all_verifiers()` if `full`.
   Rerunning them is T-09's job.
6. `build_queue(ledger, seed_names: set[str]) -> list[Unit]`: pending + changed,
   ordered by `inbound_calls` desc, with units whose `qualified_name` is in
   `seed_names` moved to the front, ties by `(file_path, start_line)`.

## Non-scope

- No verifier execution, no model, no `codegraph init`. No CLI.
- Do not reindex codegraph when the source changes; tests edit the source and rely
  on `ast_hash` alone.

## Acceptance

- `uv run pytest tests/test_units.py -q` → exit 0. Tests copy `fixture_target` to a
  tmp dir (including `.codegraph/`) so they can edit it. Covers:
  - `enumerate_units` yields ≥ 8 non-module units plus one module unit per `.py`
    file, and every non-module unit has a non-`None` `ast_hash`;
  - `unit_id` is stable across calls and differs for a different file;
  - first `sync_units` returns everything in `new`, ledger rows are `pending`;
  - second `sync_units` with no edits returns everything in `unchanged`;
  - after editing a function body (not its name) → that unit alone is in
    `changed`, its claims are `stale`, `verifiers_to_rerun` returns only verifiers
    whose `depends_on` includes it;
  - after adding only a comment inside a function → `unchanged`;
  - after deleting a function from the source → that unit is `vanished`;
  - `verifiers_to_rerun(full=True)` returns every verifier;
  - `build_queue` puts a seeded unit first, then highest `inbound_calls`, and never
    includes `scanned` or `vanished` units.
- `make check` → exit 0

## Context

- plan §5 steps 4–5, §6 identity note. Decisions Q6, Q29, Q32.
- The ledger API is `src/seshat/ledger/store.py` (T-03); `Graph` is
  `src/seshat/graph.py` (T-04). Do not add SQL here.

## Manual QA

None.
