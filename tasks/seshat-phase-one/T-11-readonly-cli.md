---
id: T-11
plan: seshat-phase-one
title: Read-only CLI
status: todo
depends_on: [T-09, T-10]
files:
  - src/seshat/cli.py
  - src/seshat/render.py
  - tests/test_cli.py
rules: []
---

## Goal

The `seshat` command from plan §7 minus `ask`: `scan` runs T-09 with T-10's
reflection hook, and `status`, `units`, `claims`, `concept`, `drift` read the ledger
and print it. Every claim shown carries its citation, and a stale one says so on
the same line.

## Scope

1. `seshat scan <repo> [--units N] [--minutes M] [--tokens T] [--workers W]
   [--no-thinking] [--full] [--model MODEL]` → `run_scan` with the real
   `worker_factory` and `reflect_after_scan`. Exit 0 on `stopped_*`, 1 on `failed`,
   2 on `ConfigError` or `IndexFailed`, with the message on stderr.
2. `seshat status <repo>`: last run's fields and counters, one per line.
3. `seshat units <repo> [--changed]`: table of `qualified_name`, `file_path`,
   `status`, confirmed/refuted/stale claim counts; `--changed` filters to
   `changed | vanished`.
4. `seshat claims <repo> <qualified_name>`: each claim as
   `[{status}] {text}  — {citation}`.
5. `seshat concept <repo> <id|query>`: exact id or first FTS hit; body, then an
   `Evidence:` list of citations.
6. `seshat drift <repo>`: stale claims and stale concepts from
   `ledger.stale_report()`, grouped by unit; exit 0 with `No drift.` when empty.
7. `src/seshat/render.py`: `format_citation(c: Citation) -> str` →
   `{qualified_name} {file_path}:{start}-{end} @{sha[:8]} [{last_status}]`, with
   `[STALE]` appended when the claim status is `stale` or `last_status == 'fail'`.
   Plain text; no color library.
8. A repo with no `.seshat/ledger.db` → message `No ledger at …; run seshat scan`
   on stderr, exit 2.

## Non-scope

- No `ask` (T-12). No new ledger queries beyond what T-03 provides; if one is
  missing, add it to the store with a test rather than writing SQL in the CLI.
- No rich/click/typer; `argparse` only.

## Acceptance

- `uv run pytest tests/test_cli.py -q` → exit 0. Tests drive `cli.main(argv)` on a
  tmp copy of `fixture_target` whose ledger was filled by a stub-worker
  `run_scan` (no model), covers:
  - `scan` with the stub factory injected exits 0 and prints at least one status
    line;
  - `status` prints the run id and `stopped_complete`;
  - `units` lists every unit; `--changed` is empty on an unchanged repo and lists
    exactly one unit after editing a function and rescanning;
  - `claims OrderRepository.get` shows each claim with a citation string matching
    the `format_citation` shape;
  - `concept <id>` prints the body and its evidence citations;
  - `drift` prints `No drift.` before the edit and names only the edited unit's
    claims after;
  - unknown repo path → exit 2 and the `run seshat scan` hint on stderr.
- `uv run seshat --help` lists all six subcommands.
- `make check` → exit 0

## Context

- plan §4 citation definition, §7, §9 (the drift check is the acceptance for the
  whole phase). Decisions Q22, Q24, Q33. `AGENTS.md` Always: cite claim id,
  qualified name, file path, span, sha, claim status, verifier status; stale says
  so inline.
- `cli.py` already has `main` from T-02; extend it.

## Manual QA

Run `seshat scan ~/code/labs-OO-Agents --units 3`, then `seshat status`,
`seshat units`, and `seshat claims` on one unit. Confirm citations point at real
lines.
