---
id: T-09
plan: seshat-phase-one
title: Scan orchestrator
depends_on: [T-06, T-08]
files:
  - src/seshat/scan.py
  - tests/test_scan.py
rules: []
---

## Goal

`seshat.scan.run_scan(...)` performs plan §5 steps 1–7 and 10 end to end in plain
Python: index, run row, seeds, unit sync, queue, worker pool, budget, close.
Reflection (step 8–9) is T-10 and is called from here behind a hook. This is the
deterministic 85 % of the system; no model is imported by this module.

## Scope

1. `ScanOptions(units: int = 5, minutes: float = 10, tokens: int = 200_000,
   workers: int = 1, thinking: bool = True, full: bool = False, model: str | None)`.
2. `run_scan(repo: Path, options, settings, *, worker_factory, after_scan=None)
   -> Run`:
   1. `codegraph init` (or `sync` if `.codegraph/` exists) via `subprocess` with
      `CODEGRAPH_TELEMETRY=0`; a non-zero exit raises `IndexFailed` with stderr.
      Injectable as `indexer=` for tests.
   2. `Ledger.open`, `Graph.open`, `create_run` with `commit_sha` from
      `git rev-parse HEAD` (or `'nogit'`), model, thinking, workers, budgets,
      `status='running'`, `mode='claims'`.
   3. `seed_docs` into working memory (T-08) → seed names.
   4. `enumerate_units` + `sync_units` + `verifiers_to_rerun` → rerun each with
      T-05 `verify_and_record`; a rerun that fails flips its claim to `stale`.
   5. `build_queue`.
   6. Worker pool: `asyncio.gather` over `workers` slots, one `worker_factory()`
      instance per unit (CyberGym pattern). After each unit: update
      `units_done`, `claims_confirmed`, `claims_refuted`, `tokens_used`, print
      one status line `[{done}/{queued}] {qualified_name} +{confirmed} -{refuted}
      tokens={used} elapsed={s}s`.
   7. Budget check after each unit: units, minutes, tokens, whichever first →
      `status='stopped_budget'`; queue drained → `stopped_complete`; unhandled
      exception → `failed` with the error in the status line, then re-raise.
   8. `after_scan(ledger, run)` hook if given (T-10 plugs reflection in).
   9. `close_run`.
3. Name the NOOA trace session by `run_id` where NOOA exposes that.

## Non-scope

- No CLI parsing (T-11). No reflection or candidate rules (T-10). No model calls
  in this module; workers come in through `worker_factory`.
- Do not parallelise beyond `asyncio.gather`; no threads or processes.

## Acceptance

- `uv run pytest tests/test_scan.py -q` → exit 0, hermetic, with `indexer` stubbed
  to a no-op (fixture already has `.codegraph/`) and `worker_factory` returning a
  stub whose `run_unit` writes one confirmed and one refuted claim and reports a
  fixed token count, against a tmp copy of `fixture_target`, covers:
  - a run with `units=2` scans exactly two units, ends `stopped_budget`, and the
    run row's counters equal what the stubs wrote;
  - `tokens=1` ends after one unit with `stopped_budget`;
  - a large budget drains the queue and ends `stopped_complete`;
  - a stub that raises → run `failed` and the exception propagates;
  - rerunning the same scan on an unchanged repo scans nothing new and ends
    `stopped_complete` with `units_done == 0`;
  - after editing one function and rerunning, only that unit is scanned again and
    only its verifiers were rerun (spy on `verify_and_record`);
  - `after_scan` is called once with the ledger and the run;
  - `workers=2` completes with the same counters as `workers=1`.
- `make check` → exit 0

## Context

- plan §2 (orchestrator row), §5, §8. Decisions Q9, Q18, Q33, Q34. `AGENTS.md`:
  "if a model creeps into the orchestration, the run stops being measurable."
- Building blocks: `units.py` (T-06), `verify.py` (T-05), `agents/worker.py`
  and `memory.py` (T-08), `ledger/store.py` (T-03).

## Manual QA

Run `uv run seshat scan <repo> --units 2` after T-11 and watch the status lines.
