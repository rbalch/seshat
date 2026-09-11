"""Tests for the DEC-0 view-naming control.

`controls/fitness/view_naming.py` is a fitness gate: it scans `governance/views/`
by default. Every test here repoints its module-level path constant at a throwaway
`tmp_path`, mirroring `tests/controls/test_exec_confinement.py`'s pattern, so the
control can be exercised against a synthetic tree without touching the real one.

This file exists because DEC-3 requires every `controls/fitness/*.py` module to
carry a test module here — the gap it closes is exactly this one: this control had
gated every build since DEC-0 with nothing pinning its two branches (see
`docs/ledger-findings.md` F-45, about the sibling control `exec_confinement.py`,
which had the identical gap).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import view_naming as vn


@pytest.fixture
def views_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway `governance/views/` with the control's constants repointed at it."""
    monkeypatch.setattr(vn, 'REPO_ROOT', tmp_path)
    root = tmp_path / 'views'
    monkeypatch.setattr(vn, 'VIEWS_DIR', root)
    return root


def run(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = vn.main()
    return code, capsys.readouterr().err


def test_clean_tree_passes(views_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    views_dir.mkdir(parents=True)
    (views_dir / 'RULES.md').write_text('# rules\n', encoding='utf-8')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_missing_views_dir_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(vn, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(vn, 'VIEWS_DIR', tmp_path / 'views')  # never created

    code, err = run(capsys)

    assert code == 1
    assert 'does not exist' in err


def test_agents_md_under_views_is_caught(views_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    views_dir.mkdir(parents=True)
    (views_dir / 'RULES.md').write_text('# rules\n', encoding='utf-8')
    (views_dir / 'AGENTS.md').write_text('poison\n', encoding='utf-8')

    code, err = run(capsys)

    assert code == 1
    assert 'views/AGENTS.md' in err


def test_agents_md_check_is_load_bearing(
    views_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red-first proof: without the name check, a rogue AGENTS.md goes unnoticed."""
    views_dir.mkdir(parents=True)
    (views_dir / 'RULES.md').write_text('# rules\n', encoding='utf-8')
    (views_dir / 'AGENTS.md').write_text('poison\n', encoding='utf-8')

    # Simulate the branch being deleted: only the required-file check remains.
    monkeypatch.setattr(vn.Path, 'rglob', lambda self, pattern: iter(()))

    code, err = run(capsys)

    assert code == 0
    assert 'AGENTS.md' not in err


def test_nested_agents_md_under_views_is_caught(views_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    views_dir.mkdir(parents=True)
    (views_dir / 'RULES.md').write_text('# rules\n', encoding='utf-8')
    nested = views_dir / 'sub'
    nested.mkdir()
    (nested / 'AGENTS.md').write_text('poison\n', encoding='utf-8')

    code, err = run(capsys)

    assert code == 1
    assert 'views/sub/AGENTS.md' in err


def test_missing_rules_md_is_caught_even_with_no_agents_md(views_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    views_dir.mkdir(parents=True)
    (views_dir / 'other.md').write_text('not the rules file\n', encoding='utf-8')

    code, err = run(capsys)

    assert code == 1
    assert 'governance/views/RULES.md is missing' in err


def test_missing_rules_md_check_is_load_bearing(views_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Red-first proof: without the required-file check, an absent RULES.md passes."""
    views_dir.mkdir(parents=True)
    (views_dir / 'other.md').write_text('not the rules file\n', encoding='utf-8')

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(vn, 'REQUIRED_VIEW', 'other.md')
    try:
        code, err = run(capsys)
    finally:
        monkeypatch.undo()

    assert code == 0
    assert err == ''


def test_both_defects_together_are_both_reported(views_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    views_dir.mkdir(parents=True)
    (views_dir / 'AGENTS.md').write_text('poison\n', encoding='utf-8')

    code, err = run(capsys)

    assert code == 1
    assert 'views/AGENTS.md' in err
    assert 'governance/views/RULES.md is missing' in err
