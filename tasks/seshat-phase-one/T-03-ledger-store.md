---
id: T-03
plan: seshat-phase-one
title: Ledger schema and typed store
status: todo
depends_on: [T-02]
files:
  - src/seshat/ledger/__init__.py
  - src/seshat/ledger/schema.py
  - src/seshat/ledger/store.py
  - src/seshat/ledger/models.py
  - tests/ledger/test_store.py
rules: []
---

## Goal

The SQLite ledger from plan §4 exists as a typed Python store. It is the only code
that writes `.seshat/ledger.db`. Every later task persists through its methods and
never issues SQL of its own.

## Scope

1. `schema.py`: the DDL from plan §4 verbatim in intent: `runs`, `units`, `claims`,
   `verifiers`, `concepts`, `concept_evidence`, plus FTS5 virtual tables over
   `claims.text` and `concepts.title || body`, kept in sync by triggers. A
   `schema_version` table with value `1`.
2. `models.py`: frozen dataclasses mirroring each table (`Run`, `Unit`, `Claim`,
   `Verifier`, `Concept`, `Citation`). Status values are `Literal` types matching
   the comments in plan §4. `Citation` carries claim id, qualified name, file path,
   `start_line`, `end_line`, `verified_sha`, verifier `last_status`.
3. `store.py`, class `Ledger`:
   - `Ledger.open(repo_path: Path) -> Ledger` creates `.seshat/` and `ledger.db`
     inside the target if absent, applies the schema once, and appends `.seshat/`
     to the target's `.gitignore` if not already present.
   - `repo_id` is derived once: sha256 of the resolved absolute repo path, first 16
     hex chars. Every insert stamps it.
   - Runs: `create_run(**fields) -> Run`, `update_run(run_id, **counters)`,
     `close_run(run_id, status)`, `last_run() -> Run | None`.
   - Units: `upsert_unit(unit: Unit, run_id)`, `set_unit_status(unit_id, status,
     run_id)`, `units(status: str | None = None) -> list[Unit]`, `unit(unit_id)`.
   - Claims: `add_claim(claim: Claim) -> Claim` (status must be `conjectured`),
     `set_claim_status(claim_id, status, run_id, verified_sha=None)`,
     `claims_for_unit(unit_id) -> list[Claim]`, `confirmed_claims(limit, offset)`,
     `mark_stale_for_units(unit_ids, run_id) -> int` (claims → stale, and every
     concept citing them → stale).
   - Verifiers: `add_verifier(v: Verifier)`, `record_verifier_run(verifier_id,
     status, error, run_id)`, `verifiers_touching(unit_ids) -> list[Verifier]`
     (matches on `depends_on` JSON list), `all_verifiers()`.
   - Concepts: `add_concept(concept, evidence_claim_ids) -> Concept`; raises
     `EvidenceNotConfirmed` if any cited claim is not `confirmed`.
   - `citation(claim_id) -> Citation` joins claim → unit → verifier.
   - `search_claims(fts_query, limit=20) -> list[Claim]`,
     `search_concepts(fts_query, limit=20) -> list[Concept]`.
   - `stale_report() -> dict` with lists of stale claims and stale concepts.
   - Context manager; `close()`.
4. All ids are `TEXT`; the store generates `run_id`, `claim_id`, `verifier_id`,
   `concept_id` as `uuid4().hex` unless given. `unit_id` is supplied by the caller
   (T-06 computes it).

## Non-scope

- No enumeration of units, no verifier execution, no model. No CLI.
- Do not use NOOA memory or NOOA storage for anything here (decisions Q21).
- No migrations framework. Version 1 only.

## Acceptance

- `uv run pytest tests/ledger/test_store.py -q` → exit 0, covers:
  - `Ledger.open(tmp_repo)` creates `.seshat/ledger.db` and adds `.seshat/` to
    `.gitignore`; opening twice does not duplicate the gitignore line;
  - every row written carries the same `repo_id` and the `run_id` passed;
  - `add_claim` with status other than `conjectured` raises `ValueError`;
  - `add_concept` citing a `conjectured` or `refuted` claim raises
    `EvidenceNotConfirmed`; citing a `confirmed` one succeeds;
  - `mark_stale_for_units` flips the claims and any concept citing them to
    `stale` and returns the claim count;
  - `verifiers_touching(['u2'])` returns exactly the verifiers whose `depends_on`
    contains `u2`;
  - `search_claims('OrderNotFound')` finds a claim containing that word and not one
    without it;
  - `citation(claim_id)` returns all seven fields and `last_status` is `None` when
    the verifier has never run.
- `make check` → exit 0

## Context

- plan §3 (why not NOOA memory), §4 (schema, citation). Decisions Q7, Q16, Q21,
  Q22, Q35.
- `sqlite3` stdlib only. Enable `PRAGMA foreign_keys=ON` and WAL.
- `AGENTS.md` "Always": rows stamped with `repo_id` and `run_id`; a stale citation
  says so inline. The `Citation` dataclass is what T-12 renders.

## Manual QA

None.
