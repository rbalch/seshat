# Seshat phase two — test what phase one built, and fix what testing finds

Phase one (`docs/specs/seshat-phase-one.md`) shipped the whole loop in fifteen tasks and
the findings ledger (F-60) records the gap: task compliance never demonstrated product
acceptance. Phase two is dogfooding. Ryan runs `seshat` against real repos, and every
thing that bites becomes a task here. The plan is expected to grow as testing goes; new
tasks are appended with the next `PT-NN` id.

## Goal

A `seshat scan` that Ryan can point at a handful of files, wipe and re-run in seconds,
and trust to stop when its clock says so. Those three controls are what make the rest
of the testing possible; nothing else in phase one changes until testing says it must.

## Approach

All three tasks are thin slices through `src/seshat/cli.py` and `src/seshat/scan.py`,
tested through the existing `StubWorker` / `SpyFactory` harness in `tests/test_scan.py`
and `tests/test_cli.py`. No model, no network, no `codegraph` subprocess in any test.

```
seshat clear REPO          ─┐ one function: remove <repo>/.seshat/, print what went
seshat scan REPO --clear   ─┘ (.codegraph/ is codegraph's; never touched)

seshat scan REPO --file demo/orders.py --file demo/main.py
    sync_units as today → mark every unit in those files `changed`
    → queue = exactly those units, same sort as today → budgets as today

seshat scan REPO --unit-timeout 300
    run_unit runs under min(unit_timeout, minutes remaining)
    → a unit that overruns is abandoned, stays unscanned, run continues
    → --minutes becomes a hard wall instead of a between-units check
```

**Why the timer looked ignored.** `_budget_exhausted()` in `scan.py` runs only when a
worker picks up its next unit. Nothing bounds one unit, so a 27B model stuck on a single
unit runs past `--minutes` indefinitely. PT-03 is the fix.

## Out of scope

- Any change to the agents (`src/seshat/agents/`), the ledger schema, or the verifier
  runner. A timed-out unit gets no new `UnitStatus`; it simply stays unscanned.
- `--file` globs, directories, or exclusion. Explicit file paths only.
- Deleting `.codegraph/`. Use `codegraph` for that.
- Reflection changes. `--file` runs go through `after_scan` exactly as before.

## Decisions

- `--file` re-processes every unit in the named files, scanned or not, by marking them
  `changed` so the existing rescan path replaces prior claims. No new queue semantics.
- `--file` changes only what goes on the queue. `--units`, `--minutes`, `--tokens` apply
  exactly as today, defaults included.
- `--clear` lives twice: `seshat clear REPO` and `scan --clear`. One code path. No
  confirmation prompt; the command prints every path it removed.
- A timed-out unit is abandoned, not recorded. It keeps its pre-scan status so the next
  run picks it up. The status line says `timeout`.
- No ADR. No task chose between alternatives a future reader would re-litigate.

## Tasks

No merge dependencies. All three touch `cli.py`, `scan.py` and their tests, so run them
one at a time, in this order.

| id | title | try it after merge |
|---|---|---|
| PT-01 | `seshat clear` and `scan --clear` | `seshat clear <repo>` prints the removed files; `.seshat/` is gone, `.codegraph/` remains |
| PT-02 | `scan --file` restricts the queue to named files | `seshat scan <repo> --file demo/orders.py`; `seshat units` shows only that file's units touched this run |
| PT-03 | `scan --unit-timeout` and a hard `--minutes` wall | a stub worker that sleeps past `--unit-timeout 1` is abandoned; the run finishes and says `timeout` |

## Open questions

- Should a timed-out unit be counted on the run row (`units_timed_out`)? Deferred until
  testing shows the status-line count is not enough. Owner: Ryan.
- Which real repo is the first phase-two target, and what are its five questions?
  Owner: Ryan; phase one's `plan.md` §9 bar still stands.
- Tasks PT-04+ arrive as testing finds things. Each new task gets its own row here.
