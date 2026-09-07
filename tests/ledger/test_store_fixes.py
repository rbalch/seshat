"""Regression tests for T-03 fix round one.

Covers, in order: (1) add_concept and mark_stale_for_units must not leave a
half-applied write behind on failure — verified by reopening the database, not
just inspecting the live connection; (2) FTS5 search must not raise on
ordinary malformed-looking input; (3) FTS5 delete triggers, currently unused
by any Ledger method but committed code; (4) add_concept must distinguish
"cited nothing" from "cited something unproven".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

import pytest

from seshat.ledger.models import Claim, Concept, Unit
from seshat.ledger.store import EvidenceNotConfirmed, Ledger, SearchQueryError


def make_unit(unit_id: str, run_id: str, **overrides) -> Unit:
    fields = {
        'id': unit_id,
        'repo_id': 'ignored',
        'file_path': 'demo/orders.py',
        'qualified_name': 'demo.orders.Order',
        'kind': 'class',
        'start_line': 1,
        'end_line': 10,
        'ast_hash': 'deadbeef',
        'inbound_calls': 0,
        'first_seen_run': run_id,
        'last_seen_run': run_id,
        'last_scanned_run': run_id,
        'status': 'pending',
    }
    fields.update(overrides)
    return Unit(**fields)


def make_claim(unit_id: str, run_id: str, text: str = 'Order raises OrderNotFound.', **overrides) -> Claim:
    fields = {
        'id': '',
        'repo_id': '',
        'unit_id': unit_id,
        'text': text,
        'kind': 'structural',
        'source': 'code',
        'mode': 'claims',
        'status': 'conjectured',
        'confidence': 0.9,
        'candidate_rule': 0,
        'rule_sightings': 0,
        'created_run': run_id,
        'verified_run': None,
        'verified_sha': None,
        'retries': 0,
    }
    fields.update(overrides)
    return Claim(**fields)


def make_concept(**overrides) -> Concept:
    fields = {
        'id': '',
        'repo_id': '',
        'title': 'Order lifecycle',
        'body': 'Orders raise OrderNotFound when missing.',
        'created_run': '',
        'status': 'current',
    }
    fields.update(overrides)
    return Concept(**fields)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'target-repo'
    repo.mkdir()
    return repo


def _confirmed_claim(ledger: Ledger, run_id: str, unit_id: str = 'u1') -> Claim:
    ledger.upsert_unit(make_unit(unit_id, run_id), run_id)
    claim = ledger.add_claim(make_claim(unit_id, run_id))
    return ledger.set_claim_status(claim.id, 'confirmed', run_id, verified_sha='sha1')


# --- item 1: add_concept must not half-write on failure -----------------


def test_add_concept_duplicate_evidence_raises_and_leaves_no_trace_after_reopen(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        confirmed = _confirmed_claim(ledger, run.id)

        with pytest.raises(sqlite3.IntegrityError):
            ledger.add_concept(make_concept(created_run=run.id), [confirmed.id, confirmed.id])

    # Reopening matters, but on its own it is not sufficient to catch this bug:
    # sqlite3.Connection.close() discards an uncommitted transaction, so a bare
    # close()+reopen would report 0 concepts even with the fix absent. The
    # test below reproduces the reviewer's exact finding: it commits an
    # unrelated write *before* closing, which is what flushes the half-write
    # to disk when the fix is missing.
    with Ledger.open(tmp_repo) as reopened:
        count = reopened.conn.execute('SELECT count(*) FROM concepts').fetchone()[0]
        assert count == 0
        evidence_count = reopened.conn.execute('SELECT count(*) FROM concept_evidence').fetchone()[0]
        assert evidence_count == 0


def test_add_concept_failure_does_not_leak_into_a_later_unrelated_commit(tmp_repo: Path):
    """The exact shape of the bug: an uncommitted half-write parked in the
    transaction, flushed to disk by the next unrelated commit rather than by
    the failing call itself. This is the test that actually fails against the
    pre-fix code — verified by hand against a temporarily unguarded
    add_concept, see the fix-round commit message for the reproduction."""
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        confirmed = _confirmed_claim(ledger, run.id)

        with pytest.raises(sqlite3.IntegrityError):
            ledger.add_concept(make_concept(created_run=run.id), [confirmed.id, confirmed.id])

        # An unrelated write and commit, on the same still-open connection —
        # the trigger for the false success described in the finding.
        ledger.upsert_unit(make_unit('u2', run.id), run.id)

    with Ledger.open(tmp_repo) as reopened:
        count = reopened.conn.execute('SELECT count(*) FROM concepts').fetchone()[0]
        assert count == 0


def test_mark_stale_for_units_is_atomic_across_reopen(tmp_repo: Path):
    """mark_stale_for_units issues two writes (claims, then concepts). Confirm
    both land together by reopening, matching the reviewer's finding on this
    method as well as add_concept."""
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        confirmed = _confirmed_claim(ledger, run.id)
        concept = ledger.add_concept(make_concept(created_run=run.id), [confirmed.id])

        count = ledger.mark_stale_for_units(['u1'], run.id)
        assert count == 1
        concept_id = concept.id

    with Ledger.open(tmp_repo) as reopened:
        claim_status = reopened.conn.execute('SELECT status FROM claims WHERE id = ?', (confirmed.id,)).fetchone()[0]
        concept_status = reopened.conn.execute('SELECT status FROM concepts WHERE id = ?', (concept_id,)).fetchone()[0]
        assert claim_status == 'stale'
        assert concept_status == 'stale'


class _FailAfterNCalls:
    """Wraps a real sqlite3.Connection, raising on the Nth `execute()` call.

    sqlite3.Connection is a C-level immutable type: individual methods on an
    instance cannot be monkeypatched, and its class cannot be patched either
    (`TypeError: cannot set 'execute' attribute of immutable type`). This
    stands in for the connection to force a genuine mid-transaction failure in
    a method whose two writes cannot otherwise fail independently with valid
    inputs, so the `with self.conn:` rollback path is actually exercised.
    """

    def __init__(self, real: sqlite3.Connection, fail_on_call: int):
        self._real = real
        self._calls = 0
        self._fail_on_call = fail_on_call

    def execute(self, *args, **kwargs):
        self._calls += 1
        if self._calls == self._fail_on_call:
            raise sqlite3.OperationalError('simulated mid-transaction failure')
        return self._real.execute(*args, **kwargs)

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._real.__exit__(*exc_info)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_mark_stale_for_units_rolls_back_on_mid_transaction_failure(tmp_repo: Path):
    """Fault-injection companion to the reopen test above: force the second of
    the two writes inside mark_stale_for_units to fail, and confirm the first
    write (claims -> stale) does not survive either."""
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        confirmed = _confirmed_claim(ledger, run.id)
        ledger.add_concept(make_concept(created_run=run.id), [confirmed.id])

        real_conn = ledger.conn
        # The wrapper's call count starts fresh here. mark_stale_for_units
        # itself issues exactly three: SELECT affected claims (1st), UPDATE
        # claims -> stale (2nd), UPDATE citing concepts -> stale (3rd). Failing
        # on the 3rd forces the claims UPDATE to have already run when the
        # concepts UPDATE blows up.
        ledger.conn = cast(sqlite3.Connection, _FailAfterNCalls(real_conn, fail_on_call=3))
        try:
            with pytest.raises(sqlite3.OperationalError):
                ledger.mark_stale_for_units(['u1'], run.id)
        finally:
            ledger.conn = real_conn

        row = ledger.conn.execute('SELECT status FROM claims WHERE id = ?', (confirmed.id,)).fetchone()
        assert row[0] == 'confirmed', 'the claims UPDATE must not survive if the concepts UPDATE failed'


# --- item 2: FTS5 search must not raise on ordinary input ---------------


@pytest.mark.parametrize('bad_query', ["don't", '*', '((', '"unterminated'])
def test_search_claims_does_not_raise_on_malformed_looking_input(tmp_repo: Path, bad_query: str):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        ledger.upsert_unit(make_unit('u1', run.id), run.id)
        ledger.add_claim(make_claim('u1', run.id))

        # Must not raise sqlite3.OperationalError (or anything else).
        results = ledger.search_claims(bad_query)
        assert isinstance(results, list)


@pytest.mark.parametrize('bad_query', ["don't", '*', '((', '"unterminated'])
def test_search_concepts_does_not_raise_on_malformed_looking_input(tmp_repo: Path, bad_query: str):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        confirmed = _confirmed_claim(ledger, run.id)
        ledger.add_concept(make_concept(created_run=run.id), [confirmed.id])

        results = ledger.search_concepts(bad_query)
        assert isinstance(results, list)


def test_search_claims_apostrophe_finds_literal_match(tmp_repo: Path):
    """The sanitised query is not just non-raising, it stays useful: a query
    containing an ordinary English contraction finds a claim containing it."""
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        ledger.upsert_unit(make_unit('u1', run.id), run.id)
        matching = ledger.add_claim(make_claim('u1', run.id, text="don't retry after the third failure"))

        results = ledger.search_claims("don't")
        assert matching.id in {c.id for c in results}


def test_search_claims_raises_typed_error_not_silent_empty_list_on_genuine_failure(tmp_repo: Path):
    """Ambiguity must fail closed: if the query genuinely cannot be evaluated —
    a NUL byte defeats even the quoting, since it terminates the FTS5 string
    literal early — the caller gets a typed exception, never an empty list
    that reads as 'no matches'."""
    with Ledger.open(tmp_repo) as ledger, pytest.raises(SearchQueryError):
        ledger.search_claims('bad\x00query')


# --- item 3: FTS5 delete triggers ----------------------------------------


def test_claims_fts_delete_trigger_removes_row_from_index(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        ledger.upsert_unit(make_unit('u1', run.id), run.id)
        claim = ledger.add_claim(make_claim('u1', run.id, text='UniqueDeleteMarkerClaim appears here'))

        assert claim.id in {c.id for c in ledger.search_claims('UniqueDeleteMarkerClaim')}

        ledger.conn.execute('DELETE FROM claims WHERE id = ?', (claim.id,))
        ledger.conn.commit()

        assert claim.id not in {c.id for c in ledger.search_claims('UniqueDeleteMarkerClaim')}
        fts_count = ledger.conn.execute(
            "SELECT count(*) FROM claims_fts WHERE claims_fts MATCH 'UniqueDeleteMarkerClaim'"
        ).fetchone()[0]
        assert fts_count == 0


def test_concepts_fts_delete_trigger_removes_row_from_index(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        confirmed = _confirmed_claim(ledger, run.id)
        concept = ledger.add_concept(
            make_concept(created_run=run.id, title='UniqueDeleteMarkerConcept', body='irrelevant'),
            [confirmed.id],
        )

        assert concept.id in {c.id for c in ledger.search_concepts('UniqueDeleteMarkerConcept')}

        # concept_evidence references concepts, and foreign_keys=ON is set on
        # every Ledger connection, so the child row must go first.
        ledger.conn.execute('DELETE FROM concept_evidence WHERE concept_id = ?', (concept.id,))
        ledger.conn.execute('DELETE FROM concepts WHERE id = ?', (concept.id,))
        ledger.conn.commit()

        assert concept.id not in {c.id for c in ledger.search_concepts('UniqueDeleteMarkerConcept')}
        fts_count = ledger.conn.execute(
            "SELECT count(*) FROM concepts_fts WHERE concepts_fts MATCH 'UniqueDeleteMarkerConcept'"
        ).fetchone()[0]
        assert fts_count == 0


# --- item 4: add_concept must distinguish "cited nothing" from "cited unproven" ---


def test_add_concept_empty_evidence_raises_value_error_not_evidence_not_confirmed(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        with pytest.raises(ValueError) as excinfo:
            ledger.add_concept(make_concept(created_run=run.id), [])
        assert not isinstance(excinfo.value, EvidenceNotConfirmed)


def test_add_concept_unproven_evidence_still_raises_evidence_not_confirmed(tmp_repo: Path):
    """The acceptance criterion this must keep passing: citing a claim that
    is not confirmed raises EvidenceNotConfirmed."""
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        ledger.upsert_unit(make_unit('u1', run.id), run.id)
        claim = ledger.add_claim(make_claim('u1', run.id))  # status='conjectured'

        with pytest.raises(EvidenceNotConfirmed):
            ledger.add_concept(make_concept(created_run=run.id), [claim.id])
