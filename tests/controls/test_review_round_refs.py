"""Tests for the DEC-4 review-round-citation control.

`controls/fitness/review_round_refs.py` is a fitness gate: it scans `src/` and
`tests/` by default. Every test here repoints its module-level constants at a
throwaway `tmp_path`, mirroring `tests/controls/test_exec_confinement.py`'s and
`tests/controls/test_view_naming.py`'s pattern, so the control can be exercised
against a synthetic tree without touching the real one.

This file exists because DEC-3 requires every `controls/fitness/*.py` module to
carry a test module here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import review_round_refs as rrr


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo root with the control's constants repointed at it."""
    monkeypatch.setattr(rrr, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(rrr, 'EXCLUDED_DIRS', {tmp_path / 'tests' / 'fixtures'})
    return tmp_path


def run(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = rrr.main()
    return code, capsys.readouterr().err


def _write(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_clean_tree_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, 'src/mod.py', 'def foo():\n    # closes a gap a reviewer found in T-15\n    return 1\n')
    _write(repo, 'tests/test_mod.py', '"""Regression tests for T-15."""\n')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_fix_round_in_comment_is_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, 'src/mod.py', 'def foo():\n    # See fix round 2, item 3 for why this exists.\n    return 1\n')

    code, err = run(capsys)

    assert code == 1
    assert 'src/mod.py:2' in err


def test_finding_number_in_comment_is_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, 'src/mod.py', '# See finding 4 for context.\ndef foo():\n    return 1\n')

    code, err = run(capsys)

    assert code == 1
    assert 'src/mod.py:1' in err


def test_finding_without_a_number_is_not_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The plain English word must not trip the control -- only a number after it does."""
    _write(repo, 'src/mod.py', 'def foo():\n    # Finding, not a fix: this helper is a no-op today.\n    return 1\n')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_fix_round_in_docstring_is_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, 'tests/test_mod.py', '"""Regression tests for T-03 fix round one."""\n')

    code, err = run(capsys)

    assert code == 1
    assert 'tests/test_mod.py:1' in err


def test_fix_round_in_function_docstring_is_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(
        repo,
        'tests/test_mod.py',
        'def test_thing():\n    """This fix round did not touch the sibling branch."""\n    assert True\n',
    )

    code, err = run(capsys)

    assert code == 1
    assert 'tests/test_mod.py:2' in err


def test_case_insensitive_fix_round_is_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, 'tests/test_mod.py', '# --- Fix round 4 ---\n')

    code, err = run(capsys)

    assert code == 1
    assert 'tests/test_mod.py:1' in err


def test_string_literal_fixture_data_is_not_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A test fixture holding source-as-a-string is data, not this repo's own commentary.

    Red-first proof that scanning is lexical (`tokenize`/`ast`), not a raw substring
    search: without that distinction, this string literal -- content under test, not
    a citation -- would trip the control.
    """
    _write(
        repo,
        'tests/test_mod.py',
        'CHECK_LOOKALIKE_SOURCE = """\n'
        '# See fix round 1, item 2 inside the sandboxed text\n'
        'def not_check(graph):\n'
        '    return 1\n'
        '"""\n',
    )

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_fixtures_directory_is_excluded(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, 'tests/fixtures/target/bad.py', '# fix round 1: probe repo data\n')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_docs_directory_is_out_of_scope(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, 'docs/ledger-findings.md', '# fix round 1 is discussed here on purpose\n')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_task_id_is_not_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, 'src/mod.py', '"""Implements T-15 / PT-01."""\n')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_unreadable_file_is_reported_and_does_not_hide_a_real_violation(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(repo, 'src/a_bad.py', '# fix round 1\n')
    (repo / 'src' / 'z_binary.py').write_bytes(b'\xff\xfe not valid utf-8 \x00\x01')

    code, err = run(capsys)

    assert code == 1
    assert 'src/a_bad.py:1' in err
    assert 'src/z_binary.py' in err
    assert 'could not decode' in err


def test_pattern_check_is_load_bearing(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red-first proof: without the pattern, an obvious violation passes."""
    _write(repo, 'src/mod.py', '# See fix round 2, item 3 for why this exists.\n')
    monkeypatch.setattr(rrr, 'PATTERN', rrr.re.compile(r'this pattern matches nothing real'))

    code, err = run(capsys)

    assert code == 0
    assert err == ''
