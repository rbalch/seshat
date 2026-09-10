"""Acceptance tests for T-11 — the read-only CLI.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-11-readonly-cli.md. Committed alone, before any
implementation exists, per the project's red-then-green contract.

Hermetic: `cli.worker_factory` is patched to hand back a `SpyFactory` wrapping
the `StubWorker` shape from `tests/test_scan.py` (driven through the real
`seshat.agents.worker.run_unit`, no model), and `cli.reflect_after_scan` is
patched to a callable that drives the real `run_reflection` with a
`nooa.unifiedllm.FakeLLMClient` (the T-10 test pattern) — so concepts and
their evidence rows come from the real reflection path, not hand-seeded rows.
No model, no network, no live LLM_HOST required (a dummy one is set so
`Settings.load` inside `cmd_scan` does not raise `ConfigError`).

On `units --changed` after an edit: editing `OrderRepository.add` changes
three `Unit` rows (the method, its class, and its module —
`tests/test_scan.py`'s own regression test names exactly these three, since
`ast_hash` hashes a whole node's `ast.dump` and a method's body is nested
inside both), but a `changed` unit that a rescan's worker pool actually
reaches gets set back to `status='scanned'` once it is (re)surveyed
(`seshat.agents.worker.run_unit`). A rescan with a large enough budget to
drain the queue therefore leaves nothing `changed`. The acceptance bullet's
"lists exactly one unit" only holds for a rescan whose budget stops short of
reprocessing every changed unit — the test below rescans with `--units 2`
(2 of the 3 changed units get reprocessed back to `scanned`, 1 stays
`changed`) to exercise that shape truthfully rather than asserting a
budget-independent claim the ledger does not actually support.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import cast

import pytest
from nooa.unifiedllm import FakeLLMClient, LLMResponse

from seshat import cli
from seshat.agents.reflection import ReflectionAgent, run_reflection
from seshat.ledger.models import Citation, Claim
from seshat.ledger.store import Ledger
from seshat.render import format_citation
from seshat.scan import IndexFailed
from tests.test_scan import SpyFactory

# -- shared fixtures ----------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, fixture_target: Path) -> Path:
    dest = tmp_path / 'target'
    shutil.copytree(fixture_target, dest)
    return dest


@pytest.fixture
def llm_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('LLM_HOST', 'http://example.invalid')


def _response(payload: dict) -> LLMResponse:
    content = json.dumps(payload)
    return LLMResponse(
        raw_response=None,
        content=content,
        tool_calls=[],
        finish_reason='stop',
        assistant_message={'role': 'assistant', 'content': content},
        reasoning=None,
        usage=None,
    )


def _fake_reflect_after_scan(settings):
    """The T-10 `reflect_after_scan` shape, driven by a `FakeLLMClient`.

    One concept, citing every confirmed claim the scan just wrote, so the
    CLI's `concept` command has a real row (with real evidence links written
    by `run_reflection`/`Ledger.add_concept`) to render.
    """

    def after_scan(ledger, run) -> None:
        confirmed = ledger.confirmed_claims(limit=100_000)
        if confirmed:
            payload = {
                'concepts': [
                    {
                        'title': 'Stub concept',
                        'body': 'Auto concept covering: ' + ' '.join(f'[{c.id}]' for c in confirmed),
                        'evidence': [c.id for c in confirmed],
                    }
                ],
                'patterns': [],
            }
        else:
            payload = {'concepts': [], 'patterns': []}

        agent = ReflectionAgent(llm=FakeLLMClient())
        agent.set_llm(FakeLLMClient(scripted_responses=[_response(payload)]))
        asyncio.run(run_reflection(agent, ledger, run.id, batch_size=100_000))

    return after_scan


def _noop_indexer(repo: Path) -> None:
    return None


@pytest.fixture
def stubbed_scan(monkeypatch: pytest.MonkeyPatch, llm_host_env: None) -> None:
    monkeypatch.setattr(cli, 'worker_factory', lambda repo, settings: SpyFactory())
    monkeypatch.setattr(cli, 'reflect_after_scan', _fake_reflect_after_scan)
    # The fixture copy already carries a committed `.codegraph/` — no test may
    # ever shell out to the real `codegraph` binary (tests/test_scan.py's own
    # `_noop_indexer` is the same seam, injected the same way).
    monkeypatch.setattr(cli, 'indexer', _noop_indexer)


def _run_scan(repo: Path) -> int:
    return cli.main(['scan', str(repo), '--units', '1000', '--minutes', '1000', '--tokens', '100000000'])


@pytest.fixture
def scanned_repo(repo: Path, stubbed_scan: None) -> Path:
    exit_code = _run_scan(repo)
    assert exit_code == 0
    return repo


CITATION_RE = re.compile(r'^\S+ \S+:\d+-\d+ @(?:[0-9a-f]{8}|-) \[(?:pass|fail|error|-)\](?: \[STALE\])?$')


def _citation(**overrides: object) -> Citation:
    fields: dict[str, object] = {
        'claim_id': 'c1',
        'qualified_name': 'OrderRepository.get',
        'file_path': 'demo/repository.py',
        'start_line': 1,
        'end_line': 5,
        'verified_sha': 'deadbeef00',
        'last_status': 'pass',
        'claim_status': 'confirmed',
    }
    fields.update(overrides)
    return Citation(**fields)


# -- bullet: format_citation renders `-` for None fields, [STALE] per trigger


def test_format_citation_renders_dash_for_none_verified_sha() -> None:
    text = format_citation(_citation(verified_sha=None))
    assert '@- [' in text
    assert 'None' not in text


def test_format_citation_renders_dash_for_none_last_status() -> None:
    text = format_citation(_citation(last_status=None))
    assert '[-]' in text
    assert 'None' not in text


def test_format_citation_appends_stale_for_a_stale_claim_with_a_passing_verifier() -> None:
    # claim_status='stale' alone must trigger [STALE], independent of
    # last_status — a verifier that still passes does not un-rot a claim
    # `mark_stale_for_units` already invalidated.
    text = format_citation(_citation(claim_status='stale', last_status='pass'))
    assert text.endswith('[STALE]')


def test_format_citation_appends_stale_for_a_failed_verifier_on_a_non_stale_claim() -> None:
    # last_status='fail' alone must trigger [STALE], independent of
    # claim_status — a claim that is not itself stale but whose own
    # verifier just failed is not trustworthy either.
    text = format_citation(_citation(claim_status='confirmed', last_status='fail'))
    assert text.endswith('[STALE]')


def test_format_citation_no_stale_suffix_when_neither_trigger_fires() -> None:
    text = format_citation(_citation(claim_status='confirmed', last_status='pass'))
    assert not text.endswith('[STALE]')


# -- bullet: scan with the stub factory patched exits 0, prints a status line -


def test_scan_exits_zero_and_prints_status_line(
    repo: Path, stubbed_scan: None, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = _run_scan(repo)

    assert exit_code == 0
    out = capsys.readouterr().out
    status_lines = [line for line in out.splitlines() if re.match(r'^\[\d+/\d+\]', line)]
    assert len(status_lines) >= 1


# -- bullet: scan exit codes — ConfigError/IndexFailed -> 2, failed -> 1, --
# -- stopped_* -> 0, message on stderr in the error cases ------------------


def test_scan_config_error_exits_two_with_message_on_stderr(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The real seam: `Settings.load()` itself raises `ConfigError` when
    # `LLM_HOST` is unset — no need to reach into `cli`'s internals for this
    # one, `cmd_scan` calls it before building anything else.
    monkeypatch.delenv('LLM_HOST', raising=False)

    exit_code = cli.main(['scan', str(repo)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert 'LLM_HOST' in err


def test_scan_index_failed_exits_two_with_message_on_stderr(
    repo: Path, stubbed_scan: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Drive it through the real seam `_cmd_scan` passes to `run_scan` — the
    # same shape as tests/test_scan.py::test_index_failed_raised_on_nonzero_indexer_exit
    # — rather than patching `run_scan` itself, so this proves the CLI maps a
    # failing *indexer* to exit code 2, not just any exception `run_scan` raises.
    def failing_indexer(repo: Path) -> None:
        raise IndexFailed('codegraph init exited 1: boom stderr')

    monkeypatch.setattr(cli, 'indexer', failing_indexer)

    exit_code = cli.main(['scan', str(repo)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert 'codegraph init exited 1' in err


def test_scan_failed_run_exits_one_with_message_on_stderr(
    repo: Path, stubbed_scan: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # `run_scan` re-raises a unit's own exception rather than returning a
    # `Run(status='failed')` (see scan.py: the `except BaseException` block
    # closes the run as `failed` and re-raises) — so a `failed` run reaches
    # this CLI as a raised exception, not a status string to branch on.
    def raising_run_scan(*args: object, **kwargs: object) -> None:
        raise RuntimeError('boom: this worker always fails')

    monkeypatch.setattr(cli, 'run_scan', raising_run_scan)

    exit_code = cli.main(['scan', str(repo)])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert 'boom: this worker always fails' in err


def test_scan_stopped_complete_exits_zero(repo: Path, stubbed_scan: None) -> None:
    assert _run_scan(repo) == 0


def test_scan_stopped_budget_exits_zero(repo: Path, stubbed_scan: None, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(['scan', str(repo), '--units', '1', '--minutes', '1000', '--tokens', '100000000'])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert 'stopped_budget' in out


# -- bullet: status prints the run id and stopped_complete -------------------


def test_status_prints_run_id_and_stopped_complete(scanned_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with Ledger.open(scanned_repo) as ledger:
        last = ledger.last_run()
        assert last is not None

    exit_code = cli.main(['status', str(scanned_repo)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert last.id in out
    assert 'stopped_complete' in out


# -- bullet: units lists every unit; --changed empty/one-after-edit ---------


def test_units_lists_every_unit(scanned_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with Ledger.open(scanned_repo) as ledger:
        all_units = ledger.units()
    assert all_units

    exit_code = cli.main(['units', str(scanned_repo)])

    assert exit_code == 0
    out = capsys.readouterr().out
    for unit in all_units:
        assert unit.qualified_name in out


def test_units_changed_is_empty_on_unchanged_repo(scanned_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(['units', str(scanned_repo), '--changed'])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.strip() == ''


_EXPECTED_CHANGED_QUALIFIED_NAMES = {'OrderRepository.add', 'OrderRepository', 'demo/repository.py'}


def _edit_order_repository_add(repo: Path) -> None:
    repo_py = repo / 'demo' / 'repository.py'
    original = repo_py.read_text()
    edited = original.replace(
        'def add(self, order_id: str, payload: dict) -> None:\n        self._orders[order_id] = payload',
        'def add(self, order_id: str, payload: dict) -> None:\n        self._orders[order_id] = dict(payload)',
    )
    assert edited != original, 'fixture source did not match the expected snippet to edit'
    repo_py.write_text(edited)


def test_units_changed_names_the_unit_a_budget_limited_rescan_did_not_reach(
    scanned_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--changed` means "seen as changed and not yet reprocessed" (scope item 3,
    amended): `sync_units` sets `OrderRepository.add` and its two enclosing
    units to `changed`; `seshat.agents.worker.run_unit` sets a unit back to
    `scanned` the moment its own worker turn actually processes it. A budget
    of 2 lets exactly 2 of those 3 reprocess, leaving `OrderRepository.add` —
    the one the queue reaches last — still `changed`. This asserts the exact
    name the filter should track, not merely a count of one: a count passes
    by arithmetic even if the filter names the wrong unit.
    """
    _edit_order_repository_add(scanned_repo)

    capsys.readouterr()  # drain the first scan's output
    exit_code = cli.main(['scan', str(scanned_repo), '--units', '2', '--minutes', '1000', '--tokens', '100000000'])
    assert exit_code == 0
    capsys.readouterr()  # drain the second scan's status lines too

    exit_code = cli.main(['units', str(scanned_repo), '--changed'])

    assert exit_code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    names = [line.split('\t', 1)[0] for line in lines]
    assert names == ['OrderRepository.add']


def test_units_changed_is_empty_after_rescan_runs_to_completion(
    scanned_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of the same semantics: a rescan whose budget drains the
    whole queue reprocesses every `changed` unit back to `scanned`
    (`run_unit`), so `--changed` is empty again — `drift`, not this flag,
    is what still shows the rot. Pins the documented behaviour with a test,
    not only with the module docstring/scope-item-3 prose.
    """
    _edit_order_repository_add(scanned_repo)

    capsys.readouterr()
    exit_code = _run_scan(scanned_repo)  # large budget: drains the queue
    assert exit_code == 0
    capsys.readouterr()

    exit_code = cli.main(['units', str(scanned_repo), '--changed'])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.strip() == ''


# -- bullet: claims OrderRepository.get shows each claim, its id, a citation -


def test_claims_shows_each_claim_with_its_id_and_a_citation(
    scanned_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with Ledger.open(scanned_repo) as ledger:
        unit = next(u for u in ledger.units() if u.qualified_name == 'OrderRepository.get')
        expected_claims = ledger.claims_for_unit(unit.id)
    assert len(expected_claims) >= 2  # StubWorker writes one confirmed + one refuted claim

    exit_code = cli.main(['claims', str(scanned_repo), 'OrderRepository.get'])

    assert exit_code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == len(expected_claims)

    for claim, line in zip(expected_claims, lines, strict=True):
        assert line.startswith(f'[{claim.status}] {claim.id} '), line
        assert re.match(r'^\[(confirmed|refuted|stale|conjectured)\] \S+ .+  — .+$', line), line
        citation_text = line.split('  — ', 1)[1]
        assert CITATION_RE.match(citation_text), citation_text


# -- bullet: concept <id> prints the body and its evidence citations --------


def test_concept_prints_body_and_evidence_citations(scanned_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with Ledger.open(scanned_repo) as ledger:
        row = ledger.conn.execute('SELECT id, body FROM concepts LIMIT 1').fetchone()
        assert row is not None, 'the fake reflection hook should have written one concept'
        concept_id, body = row['id'], row['body']
        evidence_ids = ledger.concept_evidence(concept_id)
        assert evidence_ids

    exit_code = cli.main(['concept', str(scanned_repo), concept_id])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert body in out
    assert 'Evidence:' in out
    for claim_id in evidence_ids:
        with Ledger.open(scanned_repo) as ledger:
            citation = ledger.citation(claim_id)
        assert format_citation(citation) in out


# -- bullet: drift prints "No drift." before edit, names claims after -------


def test_drift_no_drift_then_names_only_edited_unit_claims(
    scanned_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(['drift', str(scanned_repo)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.strip() == 'No drift.'

    _edit_order_repository_add(scanned_repo)

    capsys.readouterr()
    exit_code = _run_scan(scanned_repo)
    assert exit_code == 0

    with Ledger.open(scanned_repo) as ledger:
        stale = ledger.stale_report()
        stale_claims = cast(list[Claim], stale['claims'])
        stale_unit_ids = {c.unit_id for c in stale_claims}
        stale_unit_names = {u.qualified_name for u in ledger.units() if u.id in stale_unit_ids}

    assert stale_unit_names, 'the edit should have staled at least one claim'
    assert stale_unit_names <= _EXPECTED_CHANGED_QUALIFIED_NAMES

    exit_code = cli.main(['drift', str(scanned_repo)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.strip() != 'No drift.'
    for name in stale_unit_names:
        assert name in out


# -- bullet: unknown repo path -> exit 2, hint on stderr ---------------------


def test_unknown_repo_path_exits_two_with_hint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / 'does-not-exist'

    exit_code = cli.main(['status', str(missing)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert 'run seshat scan' in err
