"""Acceptance tests for T-03 — ledger schema and typed store.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-03-ledger-store.md. Committed alone, before any
implementation exists, per the project's red-then-green contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seshat.ledger.models import Claim, Concept, Unit, Verifier
from seshat.ledger.store import EvidenceNotConfirmed, Ledger


def make_unit(unit_id: str, repo_id: str, run_id: str, **overrides) -> Unit:
    fields = {
        'id': unit_id,
        'repo_id': repo_id,
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


def make_verifier(claim_id: str, depends_on: list[str], **overrides) -> Verifier:
    fields = {
        'id': '',
        'repo_id': '',
        'claim_id': claim_id,
        'source': 'def check(graph): return True',
        'expected': 'true',
        'depends_on': depends_on,
        'last_run': None,
        'last_status': None,
        'last_error': None,
    }
    fields.update(overrides)
    return Verifier(**fields)


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


# --- bullet 1: Ledger.open creates .seshat/ledger.db and .gitignore entry ---


def test_open_creates_seshat_dir_and_db(tmp_repo: Path):
    ledger = Ledger.open(tmp_repo)
    try:
        assert (tmp_repo / '.seshat').is_dir()
        assert (tmp_repo / '.seshat' / 'ledger.db').is_file()
    finally:
        ledger.close()


def test_open_adds_gitignore_entry(tmp_repo: Path):
    ledger = Ledger.open(tmp_repo)
    ledger.close()
    gitignore = (tmp_repo / '.gitignore').read_text()
    lines = [line.strip() for line in gitignore.splitlines()]
    assert lines.count('.seshat/') == 1


def test_open_twice_does_not_duplicate_gitignore_line(tmp_repo: Path):
    ledger1 = Ledger.open(tmp_repo)
    ledger1.close()
    ledger2 = Ledger.open(tmp_repo)
    ledger2.close()
    gitignore = (tmp_repo / '.gitignore').read_text()
    lines = [line.strip() for line in gitignore.splitlines()]
    assert lines.count('.seshat/') == 1


def test_open_appends_to_gitignore_without_trailing_newline(tmp_repo: Path):
    (tmp_repo / '.gitignore').write_text('*.pyc')  # no trailing newline, no .seshat/
    ledger = Ledger.open(tmp_repo)
    ledger.close()
    gitignore = (tmp_repo / '.gitignore').read_text()
    lines = [line.strip() for line in gitignore.splitlines()]
    assert '*.pyc' in lines
    assert lines.count('.seshat/') == 1


def test_open_gitignore_already_present_among_other_entries_not_duplicated(tmp_repo: Path):
    (tmp_repo / '.gitignore').write_text('*.pyc\n.seshat/\n__pycache__/\n')
    ledger = Ledger.open(tmp_repo)
    ledger.close()
    gitignore = (tmp_repo / '.gitignore').read_text()
    lines = [line.strip() for line in gitignore.splitlines()]
    assert lines.count('.seshat/') == 1


def test_open_uses_wal_and_foreign_keys(tmp_repo: Path):
    ledger = Ledger.open(tmp_repo)
    try:
        cur = ledger.conn.execute('PRAGMA journal_mode')
        assert cur.fetchone()[0].lower() == 'wal'
        cur = ledger.conn.execute('PRAGMA foreign_keys')
        assert cur.fetchone()[0] == 1
    finally:
        ledger.close()


def test_ledger_is_a_context_manager(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        assert ledger.conn is not None
        run = ledger.create_run(commit_sha='abc123', mode='claims', status='running')
        assert run.id


# --- bullet 2: every row written carries the same repo_id and the run_id passed ---


def test_rows_carry_stamped_repo_id_and_run_id(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc123', mode='claims', status='running')
        unit = make_unit('u1', repo_id='ignored', run_id=run.id)
        ledger.upsert_unit(unit, run.id)

        claim = make_claim('u1', run.id)
        stored_claim = ledger.add_claim(claim)

        verifier = make_verifier(stored_claim.id, depends_on=['u1'])
        stored_verifier = ledger.add_verifier(verifier)

        expected_repo_id = ledger.repo_id
        assert expected_repo_id

        row = ledger.conn.execute('SELECT repo_id FROM units WHERE id = ?', ('u1',)).fetchone()
        assert row[0] == expected_repo_id

        row = ledger.conn.execute('SELECT repo_id, created_run FROM claims WHERE id = ?', (stored_claim.id,)).fetchone()
        assert row[0] == expected_repo_id
        assert row[1] == run.id

        row = ledger.conn.execute('SELECT repo_id FROM runs WHERE id = ?', (run.id,)).fetchone()
        assert row[0] == expected_repo_id

        # A verifier row is self-identifying even if the claims -> units join
        # it normally rides on is ever broken by a prune or delete: it carries
        # its own repo_id, stamped independently of claim/unit ownership.
        assert stored_verifier.repo_id == expected_repo_id
        row = ledger.conn.execute('SELECT repo_id FROM verifiers WHERE id = ?', (stored_verifier.id,)).fetchone()
        assert row[0] == expected_repo_id


def test_repo_id_is_sha256_of_resolved_repo_path_first_16_hex(tmp_repo: Path):
    import hashlib

    with Ledger.open(tmp_repo) as ledger:
        expected = hashlib.sha256(str(tmp_repo.resolve()).encode()).hexdigest()[:16]
        assert ledger.repo_id == expected


# --- bullet 3: add_claim with status other than conjectured raises ValueError ---


def test_add_claim_rejects_non_conjectured_status(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        unit = make_unit('u1', repo_id='ignored', run_id=run.id)
        ledger.upsert_unit(unit, run.id)

        for bad_status in ('confirmed', 'refuted', 'stale'):
            claim = make_claim('u1', run.id, status=bad_status)
            with pytest.raises(ValueError):
                ledger.add_claim(claim)


def test_add_claim_accepts_conjectured_status(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        unit = make_unit('u1', repo_id='ignored', run_id=run.id)
        ledger.upsert_unit(unit, run.id)
        claim = make_claim('u1', run.id, status='conjectured')
        stored = ledger.add_claim(claim)
        assert stored.status == 'conjectured'
        assert stored.id


# --- bullet 4: add_concept citing non-confirmed claims raises EvidenceNotConfirmed ---


def _setup_claim_with_status(ledger: Ledger, run_id: str, status: str) -> Claim:
    unit = make_unit(f'u-{status}', repo_id='ignored', run_id=run_id)
    ledger.upsert_unit(unit, run_id)
    claim = ledger.add_claim(make_claim(unit.id, run_id))
    if status != 'conjectured':
        claim = ledger.set_claim_status(claim.id, status, run_id)
    return claim


def test_add_concept_rejects_conjectured_evidence(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        claim = _setup_claim_with_status(ledger, run.id, 'conjectured')
        concept = make_concept(created_run=run.id)
        with pytest.raises(EvidenceNotConfirmed):
            ledger.add_concept(concept, [claim.id])


def test_add_concept_rejects_refuted_evidence(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        claim = _setup_claim_with_status(ledger, run.id, 'refuted')
        concept = make_concept(created_run=run.id)
        with pytest.raises(EvidenceNotConfirmed):
            ledger.add_concept(concept, [claim.id])


def test_add_concept_accepts_confirmed_evidence(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        claim = _setup_claim_with_status(ledger, run.id, 'confirmed')
        concept = make_concept(created_run=run.id)
        stored = ledger.add_concept(concept, [claim.id])
        assert stored.id
        assert stored.status == 'current'


# --- bullet 5: mark_stale_for_units flips claims + citing concepts to stale ---


def test_mark_stale_for_units_flips_claims_and_concepts(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        unit = make_unit('u1', repo_id='ignored', run_id=run.id)
        ledger.upsert_unit(unit, run.id)

        claim = ledger.add_claim(make_claim('u1', run.id))
        confirmed = ledger.set_claim_status(claim.id, 'confirmed', run.id, verified_sha='sha1')

        concept = ledger.add_concept(make_concept(created_run=run.id), [confirmed.id])

        count = ledger.mark_stale_for_units(['u1'], run.id)
        assert count == 1

        row = ledger.conn.execute('SELECT status FROM claims WHERE id = ?', (confirmed.id,)).fetchone()
        assert row[0] == 'stale'

        row = ledger.conn.execute('SELECT status FROM concepts WHERE id = ?', (concept.id,)).fetchone()
        assert row[0] == 'stale'


def test_mark_stale_for_units_does_not_touch_unrelated_claims(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        ledger.upsert_unit(make_unit('u1', repo_id='ignored', run_id=run.id), run.id)
        ledger.upsert_unit(make_unit('u2', repo_id='ignored', run_id=run.id), run.id)

        claim1 = ledger.add_claim(make_claim('u1', run.id))
        claim2 = ledger.add_claim(make_claim('u2', run.id))
        ledger.set_claim_status(claim1.id, 'confirmed', run.id, verified_sha='sha1')
        ledger.set_claim_status(claim2.id, 'confirmed', run.id, verified_sha='sha2')

        count = ledger.mark_stale_for_units(['u1'], run.id)
        assert count == 1

        row = ledger.conn.execute('SELECT status FROM claims WHERE id = ?', (claim2.id,)).fetchone()
        assert row[0] == 'confirmed'


# --- bullet 6: verifiers_touching matches depends_on JSON list ---


def test_verifiers_touching_matches_depends_on(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        ledger.upsert_unit(make_unit('u1', repo_id='ignored', run_id=run.id), run.id)
        ledger.upsert_unit(make_unit('u2', repo_id='ignored', run_id=run.id), run.id)
        ledger.upsert_unit(make_unit('u3', repo_id='ignored', run_id=run.id), run.id)

        claim1 = ledger.add_claim(make_claim('u1', run.id))
        claim2 = ledger.add_claim(make_claim('u2', run.id))
        claim3 = ledger.add_claim(make_claim('u3', run.id))

        v_touches_u2 = ledger.add_verifier(make_verifier(claim1.id, depends_on=['u1', 'u2']))
        v_also_touches_u2 = ledger.add_verifier(make_verifier(claim2.id, depends_on=['u2']))
        v_no_u2 = ledger.add_verifier(make_verifier(claim3.id, depends_on=['u1', 'u3']))

        result = ledger.verifiers_touching(['u2'])
        result_ids = {v.id for v in result}

        assert result_ids == {v_touches_u2.id, v_also_touches_u2.id}
        assert v_no_u2.id not in result_ids


# --- bullet 7: search_claims full text search ---


def test_search_claims_finds_matching_text_only(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        ledger.upsert_unit(make_unit('u1', repo_id='ignored', run_id=run.id), run.id)
        ledger.upsert_unit(make_unit('u2', repo_id='ignored', run_id=run.id), run.id)

        matching = ledger.add_claim(
            make_claim('u1', run.id, text='get_order raises OrderNotFound when the id is missing.')
        )
        non_matching = ledger.add_claim(
            make_claim('u2', run.id, text='save_order writes the record to the repository.')
        )

        results = ledger.search_claims('OrderNotFound')
        result_ids = {c.id for c in results}

        assert matching.id in result_ids
        assert non_matching.id not in result_ids


def test_search_concepts_finds_matching_title_or_body(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        ledger.upsert_unit(make_unit('u1', repo_id='ignored', run_id=run.id), run.id)
        claim = ledger.add_claim(make_claim('u1', run.id))
        confirmed = ledger.set_claim_status(claim.id, 'confirmed', run.id, verified_sha='sha1')

        matching = ledger.add_concept(
            make_concept(created_run=run.id, title='Widgetorama lifecycle', body='irrelevant body text'),
            [confirmed.id],
        )
        non_matching = ledger.add_concept(
            make_concept(created_run=run.id, title='Something else', body='totally unrelated'),
            [confirmed.id],
        )

        results = ledger.search_concepts('Widgetorama')
        result_ids = {c.id for c in results}

        assert matching.id in result_ids
        assert non_matching.id not in result_ids


# --- bullet 8: citation returns all eight fields, last_status None if never run ---


def test_citation_returns_all_eight_fields_with_null_last_status(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        unit = make_unit('u1', repo_id='ignored', run_id=run.id)
        ledger.upsert_unit(unit, run.id)
        claim = ledger.add_claim(make_claim('u1', run.id))
        ledger.add_verifier(make_verifier(claim.id, depends_on=['u1'], last_status=None))

        citation = ledger.citation(claim.id)

        assert citation.claim_id == claim.id
        assert citation.qualified_name == unit.qualified_name
        assert citation.file_path == unit.file_path
        assert citation.start_line == unit.start_line
        assert citation.end_line == unit.end_line
        assert citation.verified_sha is None
        assert citation.last_status is None
        assert citation.claim_status == 'conjectured'


def test_citation_reflects_verifier_last_status_when_run(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        unit = make_unit('u1', repo_id='ignored', run_id=run.id)
        ledger.upsert_unit(unit, run.id)
        claim = ledger.add_claim(make_claim('u1', run.id))
        confirmed = ledger.set_claim_status(claim.id, 'confirmed', run.id, verified_sha='deadsha')
        ledger.add_verifier(make_verifier(confirmed.id, depends_on=['u1'], last_run=run.id, last_status='pass'))

        citation = ledger.citation(confirmed.id)
        assert citation.verified_sha == 'deadsha'
        assert citation.last_status == 'pass'
        assert citation.claim_status == 'confirmed'


def test_citation_claim_status_reflects_staleness_after_mark_stale(tmp_repo: Path):
    """The whole point of the eighth field: a stale citation must say so
    inline, distinctly from the verifier's last_status axis. Without
    claim_status, a confirmed claim and a stale claim return byte-identical
    Citation objects and a rotted citation renders as fresh."""
    with Ledger.open(tmp_repo) as ledger:
        run = ledger.create_run(commit_sha='abc', mode='claims', status='running')
        unit = make_unit('u1', repo_id='ignored', run_id=run.id)
        ledger.upsert_unit(unit, run.id)
        claim = ledger.add_claim(make_claim('u1', run.id))
        confirmed = ledger.set_claim_status(claim.id, 'confirmed', run.id, verified_sha='deadsha')
        ledger.add_verifier(make_verifier(confirmed.id, depends_on=['u1'], last_run=run.id, last_status='pass'))

        fresh_citation = ledger.citation(confirmed.id)
        assert fresh_citation.claim_status == 'confirmed'

        count = ledger.mark_stale_for_units(['u1'], run.id)
        assert count == 1

        stale_citation = ledger.citation(confirmed.id)
        assert stale_citation.claim_status == 'stale'
        assert stale_citation.claim_status != fresh_citation.claim_status


# --- schema_version table ---


def test_schema_version_is_1(tmp_repo: Path):
    with Ledger.open(tmp_repo) as ledger:
        row = ledger.conn.execute('SELECT version FROM schema_version').fetchone()
        assert row[0] == 1
