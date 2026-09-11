"""Tests for the DEC-3 control-test-coverage control.

`controls/fitness/control_test_coverage.py` scans `controls/fitness/` and
`tests/controls/` by default. Every test here repoints its module-level path
constants at a throwaway `tmp_path`, mirroring `tests/controls/test_exec_confinement.py`.
"""

from __future__ import annotations

from pathlib import Path

import control_test_coverage as ctc
import pytest


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ctc, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(ctc, 'CONTROLS_DIR', tmp_path / 'controls' / 'fitness')
    monkeypatch.setattr(ctc, 'TESTS_DIR', tmp_path / 'tests' / 'controls')
    return tmp_path


def write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def run(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = ctc.main()
    return code, capsys.readouterr().err


def test_control_with_matching_test_module_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'controls/fitness/widget.py', 'def main() -> int:\n    return 0\n')
    write(repo, 'tests/controls/test_widget.py', 'def test_something() -> None:\n    assert True\n')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_control_with_no_test_module_is_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'controls/fitness/widget.py', 'def main() -> int:\n    return 0\n')

    code, err = run(capsys)

    assert code == 1
    assert 'controls/fitness/widget.py' in err
    assert 'tests/controls/test_widget.py' in err


def test_control_with_empty_test_module_is_caught(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Red-first proof for the second branch: a present-but-vacuous test file must not pass."""
    write(repo, 'controls/fitness/widget.py', 'def main() -> int:\n    return 0\n')
    write(repo, 'tests/controls/test_widget.py', '# no test functions here\nimport os\n')

    code, err = run(capsys)

    assert code == 1
    assert 'defines no test_* function' in err


def test_missing_test_module_check_is_load_bearing(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete the presence check and the missing-module violation above goes unseen."""
    write(repo, 'controls/fitness/widget.py', 'def main() -> int:\n    return 0\n')

    monkeypatch.setattr(ctc, '_control_modules', list)

    code, err = run(capsys)

    assert code == 0
    assert 'widget.py' not in err


def test_nested_test_function_counts(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A test_* function need not be a top-level def -- e.g. inside a parametrized helper."""
    write(repo, 'controls/fitness/widget.py', 'def main() -> int:\n    return 0\n')
    write(
        repo,
        'tests/controls/test_widget.py',
        'class TestWidget:\n    def test_something(self) -> None:\n        assert True\n',
    )

    code, _err = run(capsys)

    assert code == 0


def test_async_test_function_counts(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'controls/fitness/widget.py', 'def main() -> int:\n    return 0\n')
    write(repo, 'tests/controls/test_widget.py', 'async def test_something() -> None:\n    assert True\n')

    code, _err = run(capsys)

    assert code == 0


def test_unparseable_test_module_counts_as_empty(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'controls/fitness/widget.py', 'def main() -> int:\n    return 0\n')
    write(repo, 'tests/controls/test_widget.py', 'def (:\n')

    code, err = run(capsys)

    assert code == 1
    assert 'defines no test_* function' in err


def test_init_py_is_never_required_to_have_a_test(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'controls/fitness/__init__.py', '')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


def test_multiple_controls_are_each_reported(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'controls/fitness/alpha.py', 'x = 1\n')
    write(repo, 'controls/fitness/beta.py', 'x = 1\n')
    write(repo, 'tests/controls/test_alpha.py', 'def test_a() -> None:\n    assert True\n')

    code, err = run(capsys)

    assert code == 1
    assert 'alpha.py' not in err
    assert 'controls/fitness/beta.py' in err


def test_empty_controls_dir_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, err = run(capsys)

    assert code == 0
    assert err == ''
