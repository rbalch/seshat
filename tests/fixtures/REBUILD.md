# Rebuilding the fixture target's codegraph index

`tests/fixtures/target/.codegraph/codegraph.db` is committed. **The source under
`tests/fixtures/target/` and this DB are committed together, in the same commit, as one
unit.** Line spans in `nodes` and `edges` are byte-exact against the committed source;
editing a fixture `.py` file without rebuilding the index silently desynchronises the
two in a way that looks like a codegraph bug to every later task that reads this DB.

Do not run `ruff format` (or any formatter) over `tests/fixtures/` — it would rewrite
line numbers after the index was built. `pyproject.toml` excludes `tests/fixtures/`
from both `ruff` and `ty` for this reason.

## Rebuild command

```bash
rm -rf tests/fixtures/target/.codegraph
CODEGRAPH_TELEMETRY=0 codegraph init tests/fixtures/target
rm -f tests/fixtures/target/.codegraph/.gitignore   # codegraph writes one; delete it, see below
```

Then re-run `tests/test_fixture_target.py` and commit the updated `codegraph.db`
alongside whatever source change triggered the rebuild.

## Why the inner `.gitignore` is deleted

`codegraph init` writes `tests/fixtures/target/.codegraph/.gitignore` containing `*` /
`!.gitignore`, which would exclude `codegraph.db` from git regardless of the repo
root's own `.gitignore`. It is not needed to open the DB, so it is removed after every
init. The repo root `.gitignore` carries the negation instead:

```
.codegraph/
!tests/fixtures/target/.codegraph/
```

## Schema (as found, `codegraph` 1.6.0)

Table names: `nodes`, `edges`, `files`, `unresolved_refs`, `nodes_fts` (+ FTS5 shadow
tables `nodes_fts_config`, `nodes_fts_data`, `nodes_fts_docsize`, `nodes_fts_idx`),
`name_segment_vocab`, `project_metadata`, `schema_versions`.

### `nodes`

| column | type | notes |
|---|---|---|
| `id` | TEXT PK | e.g. `function:a9af5ad147ec7d70c4dd0ec3182ee1a8` — hashes line numbers, not stable across edits |
| `kind` | TEXT | `class`, `function`, `method`, `file`, `import`, … |
| `name` | TEXT | bare name |
| `qualified_name` | TEXT | dotted path |
| `file_path` | TEXT | relative to the indexed root, e.g. `demo/receipts.py` |
| `language` | TEXT | |
| `start_line`, `end_line` | INTEGER | 1-indexed |
| `start_column`, `end_column` | INTEGER | |
| `docstring` | TEXT | nullable |
| `signature` | TEXT | nullable |
| `visibility` | TEXT | nullable |
| `is_exported`, `is_async`, `is_static`, `is_abstract` | INTEGER | 0/1 |
| `decorators` | TEXT | JSON array; **empty for Python nodes** (known codegraph gap — see T-04) |
| `type_parameters` | TEXT | JSON array |
| `return_type` | TEXT | nullable |
| `updated_at` | INTEGER | |

### `edges`

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | autoincrement |
| `source` | TEXT | FK → `nodes.id` |
| `target` | TEXT | FK → `nodes.id` |
| `kind` | TEXT | `contains`, `calls`, `instantiates`, `references`, `imports`, `extends`, `decorates` |
| `metadata` | TEXT | JSON object, nullable |
| `line`, `col` | INTEGER | nullable |
| `provenance` | TEXT | nullable |

### `files`

| column | type | notes |
|---|---|---|
| `path` | TEXT PK | relative to the indexed root, e.g. `demo/repository.py` |
| `content_hash` | TEXT | |
| `language` | TEXT | |
| `size` | INTEGER | |
| `modified_at`, `indexed_at` | INTEGER | |
| `node_count` | INTEGER | default 0 |
| `errors` | TEXT | JSON array, nullable |
| `generated` | INTEGER | default 0 |

### `unresolved_refs`

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | autoincrement |
| `from_node_id` | TEXT | FK → `nodes.id` |
| `reference_name` | TEXT | e.g. `json.dumps` |
| `reference_kind` | TEXT | |
| `line`, `col` | INTEGER | |
| `candidates` | TEXT | JSON array, nullable |
| `file_path` | TEXT | default `''` |
| `language` | TEXT | default `'unknown'` |
| `status` | TEXT | default `'pending'` |
| `name_tail` | TEXT | default `''` |

## What the fixture graph actually contains (for sanity, after `codegraph init`)

- 7 files indexed, 31 nodes, 53 edges.
- Node kinds: `class` (3), `function` (6), `method` (5), `file` (7), `import` (10).
- Edge kinds present: `calls` (7), `contains` (24), `decorates` (1), `extends` (1),
  `imports` (16), `instantiates` (3), `references` (1).
- `unresolved_refs`: 11 rows (`json.dumps` among them — stdlib calls are not resolved
  against the indexed repo).
- The single `extends` edge is `SpecialOrder` → `OrderRepository`.
- `render_receipt` (in `demo/receipts.py`) has inbound calls from both
  `demo/receipts.py` (`print_receipt`) and `demo/main.py` (`main`).
