"""The typed ledger store. The only code that writes `.seshat/ledger.db`.

Every later task persists through `Ledger`'s methods and never issues SQL of its
own — see AGENTS.md and tasks/seshat-phase-one/T-03-ledger-store.md.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from seshat.ledger.models import Citation, Claim, Concept, Run, RunMode, RunStatus, Unit, Verifier
from seshat.ledger.schema import apply_schema

_GITIGNORE_ENTRY = '.seshat/'


class EvidenceNotConfirmed(Exception):
    """Raised when a concept cites a claim that does not exist or is not `confirmed`."""


class SearchQueryError(Exception):
    """Raised when a search query cannot be evaluated against the FTS5 index.

    Distinct from an empty result list: an empty list means the query was
    evaluated and matched nothing, this means the query itself was rejected.
    """


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fts_phrase(query: str) -> str:
    """Turn arbitrary user input into a literal FTS5 phrase query.

    FTS5's own query language treats `' " ( ) * - :` and bareword operators like
    `AND`/`NOT` specially, so passing a model- or user-authored string straight
    to `MATCH` raises `sqlite3.OperationalError` on ordinary input (an
    apostrophe, a bare `*`, an unbalanced paren). Wrapping the whole query in
    double quotes makes FTS5 treat it as one literal phrase: every character
    loses its special meaning except the closing quote, which we escape by
    doubling. A phrase that matches nothing is a real, evaluated "no results" —
    not a silently swallowed rejection.
    """
    return '"' + query.replace('"', '""') + '"'


def _ensure_gitignore(repo_root: Path) -> None:
    path = repo_root / '.gitignore'
    if path.exists():
        content = path.read_text()
        lines = [line.strip() for line in content.splitlines()]
        if _GITIGNORE_ENTRY in lines:
            return
        if content and not content.endswith('\n'):
            content += '\n'
        content += _GITIGNORE_ENTRY + '\n'
        path.write_text(content)
    else:
        path.write_text(_GITIGNORE_ENTRY + '\n')


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        id=row['id'],
        repo_id=row['repo_id'],
        commit_sha=row['commit_sha'],
        started_at=row['started_at'],
        finished_at=row['finished_at'],
        model=row['model'],
        thinking=row['thinking'],
        workers=row['workers'],
        budget_units=row['budget_units'],
        budget_minutes=row['budget_minutes'],
        budget_tokens=row['budget_tokens'],
        units_done=row['units_done'],
        claims_confirmed=row['claims_confirmed'],
        claims_refuted=row['claims_refuted'],
        tokens_used=row['tokens_used'],
        mode=row['mode'],
        status=row['status'],
    )


def _row_to_unit(row: sqlite3.Row) -> Unit:
    return Unit(
        id=row['id'],
        repo_id=row['repo_id'],
        file_path=row['file_path'],
        qualified_name=row['qualified_name'],
        kind=row['kind'],
        start_line=row['start_line'],
        end_line=row['end_line'],
        ast_hash=row['ast_hash'],
        inbound_calls=row['inbound_calls'],
        first_seen_run=row['first_seen_run'],
        last_seen_run=row['last_seen_run'],
        last_scanned_run=row['last_scanned_run'],
        status=row['status'],
    )


def _row_to_claim(row: sqlite3.Row) -> Claim:
    return Claim(
        id=row['id'],
        repo_id=row['repo_id'],
        unit_id=row['unit_id'],
        text=row['text'],
        kind=row['kind'],
        source=row['source'],
        mode=row['mode'],
        status=row['status'],
        confidence=row['confidence'],
        candidate_rule=row['candidate_rule'],
        rule_sightings=row['rule_sightings'],
        created_run=row['created_run'],
        verified_run=row['verified_run'],
        verified_sha=row['verified_sha'],
        retries=row['retries'],
    )


def _row_to_verifier(row: sqlite3.Row) -> Verifier:
    return Verifier(
        id=row['id'],
        repo_id=row['repo_id'],
        claim_id=row['claim_id'],
        source=row['source'],
        expected=row['expected'],
        depends_on=json.loads(row['depends_on']),
        last_run=row['last_run'],
        last_status=row['last_status'],
        last_error=row['last_error'],
    )


def _row_to_concept(row: sqlite3.Row) -> Concept:
    return Concept(
        id=row['id'],
        repo_id=row['repo_id'],
        title=row['title'],
        body=row['body'],
        created_run=row['created_run'],
        status=row['status'],
    )


@dataclass
class Ledger:
    conn: sqlite3.Connection
    repo_id: str
    repo_root: Path

    # -- lifecycle -----------------------------------------------------

    @classmethod
    def open(cls, repo_path: Path) -> Ledger:
        resolved = Path(repo_path).resolve()
        repo_id = hashlib.sha256(str(resolved).encode()).hexdigest()[:16]

        seshat_dir = resolved / '.seshat'
        seshat_dir.mkdir(parents=True, exist_ok=True)
        db_path = seshat_dir / 'ledger.db'

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA journal_mode = WAL')
        apply_schema(conn)

        _ensure_gitignore(resolved)

        return cls(conn=conn, repo_id=repo_id, repo_root=resolved)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- runs ------------------------------------------------------------

    def create_run(
        self,
        id: str | None = None,
        commit_sha: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        model: str | None = None,
        thinking: int = 0,
        workers: int = 1,
        budget_units: int | None = None,
        budget_minutes: int | None = None,
        budget_tokens: int | None = None,
        units_done: int = 0,
        claims_confirmed: int = 0,
        claims_refuted: int = 0,
        tokens_used: int = 0,
        mode: RunMode = 'claims',
        status: RunStatus = 'running',
    ) -> Run:
        run = Run(
            id=id or _new_id(),
            repo_id=self.repo_id,
            commit_sha=commit_sha,
            started_at=started_at or _now(),
            finished_at=finished_at,
            model=model,
            thinking=thinking,
            workers=workers,
            budget_units=budget_units,
            budget_minutes=budget_minutes,
            budget_tokens=budget_tokens,
            units_done=units_done,
            claims_confirmed=claims_confirmed,
            claims_refuted=claims_refuted,
            tokens_used=tokens_used,
            mode=mode,
            status=status,
        )
        self.conn.execute(
            """
            INSERT INTO runs (
                id, repo_id, commit_sha, started_at, finished_at, model, thinking,
                workers, budget_units, budget_minutes, budget_tokens, units_done,
                claims_confirmed, claims_refuted, tokens_used, mode, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.id,
                run.repo_id,
                run.commit_sha,
                run.started_at,
                run.finished_at,
                run.model,
                run.thinking,
                run.workers,
                run.budget_units,
                run.budget_minutes,
                run.budget_tokens,
                run.units_done,
                run.claims_confirmed,
                run.claims_refuted,
                run.tokens_used,
                run.mode,
                run.status,
            ),
        )
        self.conn.commit()
        return run

    def update_run(self, run_id: str, **counters: object) -> Run:
        allowed = {
            'commit_sha',
            'finished_at',
            'model',
            'thinking',
            'workers',
            'budget_units',
            'budget_minutes',
            'budget_tokens',
            'units_done',
            'claims_confirmed',
            'claims_refuted',
            'tokens_used',
            'mode',
            'status',
        }
        unknown = set(counters) - allowed
        if unknown:
            raise ValueError(f'unknown run fields: {sorted(unknown)}')
        if counters:
            set_clause = ', '.join(f'{key} = ?' for key in counters)
            self.conn.execute(
                f'UPDATE runs SET {set_clause} WHERE id = ? AND repo_id = ?',
                (*counters.values(), run_id, self.repo_id),
            )
            self.conn.commit()
        row = self.conn.execute('SELECT * FROM runs WHERE id = ?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(f'no such run: {run_id}')
        return _row_to_run(row)

    def close_run(self, run_id: str, status: str) -> Run:
        return self.update_run(run_id, status=status, finished_at=_now())

    def last_run(self) -> Run | None:
        row = self.conn.execute(
            'SELECT * FROM runs WHERE repo_id = ? ORDER BY started_at DESC, rowid DESC LIMIT 1',
            (self.repo_id,),
        ).fetchone()
        return _row_to_run(row) if row is not None else None

    # -- units -------------------------------------------------------------

    def upsert_unit(self, unit: Unit, run_id: str) -> Unit:
        stamped = replace(unit, repo_id=self.repo_id, last_seen_run=run_id)
        self.conn.execute(
            """
            INSERT INTO units (
                id, repo_id, file_path, qualified_name, kind, start_line, end_line,
                ast_hash, inbound_calls, first_seen_run, last_seen_run,
                last_scanned_run, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                file_path = excluded.file_path,
                qualified_name = excluded.qualified_name,
                kind = excluded.kind,
                start_line = excluded.start_line,
                end_line = excluded.end_line,
                ast_hash = excluded.ast_hash,
                inbound_calls = excluded.inbound_calls,
                last_seen_run = excluded.last_seen_run,
                last_scanned_run = excluded.last_scanned_run,
                status = excluded.status
            """,
            (
                stamped.id,
                stamped.repo_id,
                stamped.file_path,
                stamped.qualified_name,
                stamped.kind,
                stamped.start_line,
                stamped.end_line,
                stamped.ast_hash,
                stamped.inbound_calls,
                stamped.first_seen_run,
                stamped.last_seen_run,
                stamped.last_scanned_run,
                stamped.status,
            ),
        )
        self.conn.commit()
        result = self.unit(stamped.id)
        if result is None:
            raise KeyError(f'no such unit after upsert: {stamped.id}')
        return result

    def set_unit_status(self, unit_id: str, status: str, run_id: str) -> Unit:
        self.conn.execute(
            'UPDATE units SET status = ?, last_scanned_run = ? WHERE id = ?',
            (status, run_id, unit_id),
        )
        self.conn.commit()
        result = self.unit(unit_id)
        if result is None:
            raise KeyError(f'no such unit: {unit_id}')
        return result

    def units(self, status: str | None = None) -> list[Unit]:
        if status is None:
            rows = self.conn.execute('SELECT * FROM units WHERE repo_id = ?', (self.repo_id,)).fetchall()
        else:
            rows = self.conn.execute(
                'SELECT * FROM units WHERE repo_id = ? AND status = ?',
                (self.repo_id, status),
            ).fetchall()
        return [_row_to_unit(row) for row in rows]

    def unit(self, unit_id: str) -> Unit | None:
        row = self.conn.execute('SELECT * FROM units WHERE id = ?', (unit_id,)).fetchone()
        return _row_to_unit(row) if row is not None else None

    # -- claims --------------------------------------------------------------

    def add_claim(self, claim: Claim) -> Claim:
        if claim.status != 'conjectured':
            raise ValueError(
                f"add_claim requires status='conjectured', got {claim.status!r}; "
                'a claim only becomes confirmed/refuted/stale via set_claim_status'
            )
        stamped = replace(claim, id=claim.id or _new_id(), repo_id=self.repo_id)
        self.conn.execute(
            """
            INSERT INTO claims (
                id, repo_id, unit_id, text, kind, source, mode, status, confidence,
                candidate_rule, rule_sightings, created_run, verified_run,
                verified_sha, retries
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stamped.id,
                stamped.repo_id,
                stamped.unit_id,
                stamped.text,
                stamped.kind,
                stamped.source,
                stamped.mode,
                stamped.status,
                stamped.confidence,
                stamped.candidate_rule,
                stamped.rule_sightings,
                stamped.created_run,
                stamped.verified_run,
                stamped.verified_sha,
                stamped.retries,
            ),
        )
        self.conn.commit()
        return stamped

    def set_claim_status(
        self,
        claim_id: str,
        status: str,
        run_id: str,
        verified_sha: str | None = None,
        retries: int | None = None,
    ) -> Claim:
        """Update a claim's status (and `verified_run`/`verified_sha`); optionally its `retries`.

        `retries=None` (the default) leaves the `retries` column untouched —
        every caller before T-08 relies on this method writing status,
        `verified_run` and `verified_sha` only, and none of them pass
        `retries`, so this is the exact same UPDATE they always got. Only
        when a caller passes a real `int` does the column move: T-08's
        `Worker.verify_claim` needs to record how many retries a claim took
        (0 on a first-try pass, 1 after one retry, whether the second
        attempt passed or the claim ended up `refuted`), and there was no
        typed path to write it at all before this — `add_claim` is
        insert-only and rejects any status but `conjectured`. Same shape as
        the `F-20` defect in `docs/ledger-findings.md`: a status write that
        cannot write a field the status carries.
        """
        if retries is None:
            self.conn.execute(
                'UPDATE claims SET status = ?, verified_run = ?, verified_sha = ? WHERE id = ?',
                (status, run_id, verified_sha, claim_id),
            )
        else:
            self.conn.execute(
                'UPDATE claims SET status = ?, verified_run = ?, verified_sha = ?, retries = ? WHERE id = ?',
                (status, run_id, verified_sha, retries, claim_id),
            )
        self.conn.commit()
        row = self.conn.execute('SELECT * FROM claims WHERE id = ?', (claim_id,)).fetchone()
        if row is None:
            raise KeyError(f'no such claim: {claim_id}')
        return _row_to_claim(row)

    def claims_for_unit(self, unit_id: str) -> list[Claim]:
        rows = self.conn.execute('SELECT * FROM claims WHERE unit_id = ?', (unit_id,)).fetchall()
        return [_row_to_claim(row) for row in rows]

    def confirmed_claims(self, limit: int = 20, offset: int = 0) -> list[Claim]:
        rows = self.conn.execute(
            "SELECT * FROM claims WHERE repo_id = ? AND status = 'confirmed' ORDER BY rowid LIMIT ? OFFSET ?",
            (self.repo_id, limit, offset),
        ).fetchall()
        return [_row_to_claim(row) for row in rows]

    def claims_by_ids(self, claim_ids: list[str]) -> list[Claim]:
        """Claims matching `claim_ids`, silently omitting any id that does not exist.

        For T-10's `flag_candidates`: a model-authored `PatternDraft` cites
        claim ids freely and may hallucinate one, so this looks them up
        rather than raising — the caller decides what to do with whichever
        ids come back real, exactly like `run_reflection` already does for
        a concept's evidence ids.
        """
        if not claim_ids:
            return []
        placeholders = ','.join('?' for _ in claim_ids)
        rows = self.conn.execute(
            f'SELECT * FROM claims WHERE id IN ({placeholders})',
            claim_ids,
        ).fetchall()
        return [_row_to_claim(row) for row in rows]

    def set_candidate(self, claim_id: str, sightings: int) -> Claim:
        """Set `candidate_rule=1` and `rule_sightings=sightings` on one claim.

        T-03 shipped the two columns but no writer for them — this is that
        writer, added for T-10's `flag_candidates`. Seshat only ever flags a
        candidate here; nothing in this codebase unsets `candidate_rule`
        (AGENTS.md "Never: emit a governance rule" — a human decides what,
        if anything, happens next).
        """
        self.conn.execute(
            'UPDATE claims SET candidate_rule = 1, rule_sightings = ? WHERE id = ?',
            (sightings, claim_id),
        )
        self.conn.commit()
        rows = self.claims_by_ids([claim_id])
        if not rows:
            raise KeyError(f'no such claim: {claim_id}')
        return rows[0]

    def mark_stale_for_units(self, unit_ids: list[str], run_id: str) -> int:
        if not unit_ids:
            return 0
        placeholders = ','.join('?' for _ in unit_ids)

        affected = self.conn.execute(
            f"SELECT id FROM claims WHERE unit_id IN ({placeholders}) AND status != 'stale'",
            unit_ids,
        ).fetchall()
        claim_ids = [row['id'] for row in affected]

        if claim_ids:
            # Two writes that must land together: a claim flipped to stale with its
            # citing concept left `current` (or vice versa) is a half-applied
            # invalidation. `with self.conn:` commits on a clean exit and rolls
            # back the whole block on any exception, so a failure here leaves the
            # prior committed state untouched rather than parking an uncommitted
            # write that a later, unrelated commit would flush to disk.
            with self.conn:
                self.conn.execute(
                    f"UPDATE claims SET status = 'stale' WHERE unit_id IN ({placeholders})",
                    unit_ids,
                )
                claim_placeholders = ','.join('?' for _ in claim_ids)
                self.conn.execute(
                    f"""
                    UPDATE concepts SET status = 'stale' WHERE id IN (
                        SELECT concept_id FROM concept_evidence WHERE claim_id IN ({claim_placeholders})
                    )
                    """,
                    claim_ids,
                )
        return len(claim_ids)

    # -- verifiers -------------------------------------------------------

    def add_verifier(self, v: Verifier) -> Verifier:
        # Stamped with repo_id so a verifier row is self-identifying even if
        # the claims -> units join it normally rides on is ever broken by a
        # prune or delete.
        stamped = replace(v, id=v.id or _new_id(), repo_id=self.repo_id)
        self.conn.execute(
            """
            INSERT INTO verifiers (
                id, repo_id, claim_id, source, expected, depends_on, last_run,
                last_status, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stamped.id,
                stamped.repo_id,
                stamped.claim_id,
                stamped.source,
                stamped.expected,
                json.dumps(list(stamped.depends_on)),
                stamped.last_run,
                stamped.last_status,
                stamped.last_error,
            ),
        )
        self.conn.commit()
        return stamped

    def record_verifier_run(self, verifier_id: str, status: str, error: str | None, run_id: str) -> Verifier:
        self.conn.execute(
            'UPDATE verifiers SET last_run = ?, last_status = ?, last_error = ? WHERE id = ?',
            (run_id, status, error, verifier_id),
        )
        self.conn.commit()
        row = self.conn.execute('SELECT * FROM verifiers WHERE id = ?', (verifier_id,)).fetchone()
        if row is None:
            raise KeyError(f'no such verifier: {verifier_id}')
        return _row_to_verifier(row)

    def verifiers_touching(self, unit_ids: list[str]) -> list[Verifier]:
        if not unit_ids:
            return []
        placeholders = ','.join('?' for _ in unit_ids)
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT v.*
            FROM verifiers v, json_each(v.depends_on) je
            WHERE je.value IN ({placeholders})
            """,
            unit_ids,
        ).fetchall()
        return [_row_to_verifier(row) for row in rows]

    def all_verifiers(self) -> list[Verifier]:
        rows = self.conn.execute('SELECT * FROM verifiers').fetchall()
        return [_row_to_verifier(row) for row in rows]

    # -- concepts --------------------------------------------------------

    def add_concept(self, concept: Concept, evidence_claim_ids: list[str]) -> Concept:
        # Distinct from EvidenceNotConfirmed: "cited nothing" is a caller mistake
        # about the shape of the call, not a claim about unproven evidence.
        if not evidence_claim_ids:
            raise ValueError('a concept requires at least one evidence claim id')

        placeholders = ','.join('?' for _ in evidence_claim_ids)
        rows = self.conn.execute(
            f'SELECT id, status FROM claims WHERE id IN ({placeholders})',
            evidence_claim_ids,
        ).fetchall()
        statuses = {row['id']: row['status'] for row in rows}

        missing = set(evidence_claim_ids) - set(statuses)
        if missing:
            raise EvidenceNotConfirmed(f'unknown claim ids: {sorted(missing)}')

        not_confirmed = [cid for cid, status in statuses.items() if status != 'confirmed']
        if not_confirmed:
            raise EvidenceNotConfirmed(f'claims not confirmed: {sorted(not_confirmed)}')

        stamped = replace(concept, id=concept.id or _new_id(), repo_id=self.repo_id)
        # Two writes that must land together: on any exception inside this block
        # (e.g. a duplicate evidence claim id colliding on the concept_evidence
        # primary key) `with self.conn:` rolls back the whole transaction, so the
        # concepts INSERT above never survives to be flushed by some later,
        # unrelated commit. Without this, a caller sees the raise and believes
        # nothing was written while the ledger silently keeps a concept with a
        # truncated evidence set — the false-success case AGENTS.md forbids.
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO concepts (id, repo_id, title, body, created_run, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (stamped.id, stamped.repo_id, stamped.title, stamped.body, stamped.created_run, stamped.status),
            )
            self.conn.executemany(
                'INSERT INTO concept_evidence (concept_id, claim_id) VALUES (?, ?)',
                [(stamped.id, claim_id) for claim_id in evidence_claim_ids],
            )
        return stamped

    def concept(self, concept_id: str) -> Concept | None:
        """One concept by id, or `None` — the exact-id half of the CLI's `concept` lookup."""
        row = self.conn.execute('SELECT * FROM concepts WHERE id = ?', (concept_id,)).fetchone()
        return _row_to_concept(row) if row is not None else None

    def concept_evidence(self, concept_id: str) -> list[str]:
        """The claim ids a concept cites as evidence, insertion order. `[]` for an unknown concept."""
        rows = self.conn.execute(
            'SELECT claim_id FROM concept_evidence WHERE concept_id = ? ORDER BY rowid', (concept_id,)
        ).fetchall()
        return [row['claim_id'] for row in rows]

    # -- citation ---------------------------------------------------------

    def citation(self, claim_id: str) -> Citation:
        row = self.conn.execute(
            """
            SELECT
                c.id AS claim_id,
                u.qualified_name AS qualified_name,
                u.file_path AS file_path,
                u.start_line AS start_line,
                u.end_line AS end_line,
                c.verified_sha AS verified_sha,
                v.last_status AS last_status,
                c.status AS claim_status
            FROM claims c
            JOIN units u ON u.id = c.unit_id
            LEFT JOIN verifiers v ON v.claim_id = c.id
            WHERE c.id = ?
            ORDER BY v.rowid DESC
            LIMIT 1
            """,
            (claim_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f'no such claim: {claim_id}')
        return Citation(
            claim_id=row['claim_id'],
            qualified_name=row['qualified_name'],
            file_path=row['file_path'],
            start_line=row['start_line'],
            end_line=row['end_line'],
            verified_sha=row['verified_sha'],
            last_status=row['last_status'],
            claim_status=row['claim_status'],
        )

    # -- search -------------------------------------------------------------

    def search_claims(self, fts_query: str, limit: int = 20) -> list[Claim]:
        try:
            rows = self.conn.execute(
                """
                SELECT c.* FROM claims c
                JOIN claims_fts f ON f.rowid = c.rowid
                WHERE claims_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (_fts_phrase(fts_query), limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SearchQueryError(f'could not evaluate claim search query {fts_query!r}: {exc}') from exc
        return [_row_to_claim(row) for row in rows]

    def search_concepts(self, fts_query: str, limit: int = 20) -> list[Concept]:
        try:
            rows = self.conn.execute(
                """
                SELECT c.* FROM concepts c
                JOIN concepts_fts f ON f.rowid = c.rowid
                WHERE concepts_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (_fts_phrase(fts_query), limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SearchQueryError(f'could not evaluate concept search query {fts_query!r}: {exc}') from exc
        return [_row_to_concept(row) for row in rows]

    # -- reporting ------------------------------------------------------

    def stale_report(self) -> dict[str, list[Claim] | list[Concept]]:
        stale_claims = self.conn.execute(
            "SELECT * FROM claims WHERE repo_id = ? AND status = 'stale'", (self.repo_id,)
        ).fetchall()
        stale_concepts = self.conn.execute(
            "SELECT * FROM concepts WHERE repo_id = ? AND status = 'stale'", (self.repo_id,)
        ).fetchall()
        return {
            'claims': [_row_to_claim(row) for row in stale_claims],
            'concepts': [_row_to_concept(row) for row in stale_concepts],
        }
