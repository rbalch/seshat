"""Tests for the DEC-2 exec/eval confinement control.

`controls/fitness/exec_confinement.py` is a fitness gate: it scans this repo's own
tree by default. Every test here repoints its module-level path constants at a
throwaway `tmp_path`, mirroring `tests/governance/conftest.py`'s pattern for
`check_governance`/`build_views`, so the control can be exercised against a
synthetic tree without touching anything real.

Nothing in this file is a stand-in for running the control against the real repo --
`make governance` still does that. This file exists because the control's own
exclusion rules (hidden directories, `tests/fixtures/`, not descending into a
symlinked directory, decode failures) are exactly the kind of logic that can be
silently broken by an edit that the real tree is too clean to catch (see
`docs/ledger-findings.md` F-38).
"""

from __future__ import annotations

import os
from pathlib import Path

import exec_confinement as ec
import pytest


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo root with the control's constants repointed at it."""
    monkeypatch.setattr(ec, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(ec, 'EXCLUDED_DIRS', {tmp_path / 'tests' / 'fixtures'})
    monkeypatch.setattr(ec, 'ALLOWED_PATH', tmp_path / 'src' / 'seshat' / 'verify.py')
    return tmp_path


def write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def run(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = ec.main()
    return code, capsys.readouterr().err


def run_full(capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Like `run`, but also returns stdout -- the informational symlink line lives there."""
    code = ec.main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- A violation is caught in every directory the derived scan set covers -------


@pytest.mark.parametrize(
    'rel',
    [
        'src/seshat/thing.py',
        'controls/fitness/other.py',
        'governance/scripts/other.py',
        'tests/test_other.py',
        'scripts/tool.py',
        # A directory name that exists in no hand-written list anywhere in this
        # repo -- proves the scan set is derived, not enumerated.
        'apps/worker/main.py',
    ],
)
def test_violation_caught_in_every_covered_directory(repo: Path, capsys: pytest.CaptureFixture[str], rel: str) -> None:
    write(repo, rel, 'x = eval("1")\n')

    code, err = run(capsys)

    assert code == 1
    assert rel in err


def test_clean_tree_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'src/seshat/thing.py', 'x = 1\n')

    code, err = run(capsys)

    assert code == 0
    assert err == ''


# --- verify.py's one legitimate call, and only that path --------------------------


def test_verify_py_call_is_allowed(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'src/seshat/verify.py', 'x = eval("1")\n')

    code, _ = run(capsys)

    assert code == 0


def test_allowance_does_not_extend_to_a_sibling_file(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A file that merely lives beside verify.py gets no free pass."""
    write(repo, 'src/seshat/verify.py', 'x = 1\n')
    write(repo, 'src/seshat/verify_helper.py', 'x = eval("1")\n')

    code, err = run(capsys)

    assert code == 1
    assert 'src/seshat/verify_helper.py' in err


# --- exclusions: each one pinned, each one provably load-bearing ------------------


def test_tests_fixtures_is_excluded(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'tests/fixtures/target/thing.py', 'x = eval("1")\n')

    code, _ = run(capsys)

    assert code == 0


def test_tests_fixtures_guard_is_load_bearing(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Red-first proof: without the guard, the fixture violation above is caught."""
    write(repo, 'tests/fixtures/target/thing.py', 'x = eval("1")\n')
    ec.EXCLUDED_DIRS.clear()  # simulate the guard being deleted

    code, err = run(capsys)

    assert code == 1
    assert 'tests/fixtures/target/thing.py' in err


@pytest.mark.parametrize('rel', ['.git/hooks/thing.py', '.venv/lib/thing.py', '.claude/skills/thing.py'])
def test_hidden_directory_component_is_excluded(repo: Path, capsys: pytest.CaptureFixture[str], rel: str) -> None:
    write(repo, rel, 'x = eval("1")\n')

    code, _ = run(capsys)

    assert code == 0


@pytest.mark.parametrize('name', ['node_modules', 'dist', 'build', '__pycache__'])
def test_build_and_dependency_directories_are_excluded(
    repo: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    write(repo, f'src/{name}/thing.py', 'x = eval("1")\n')

    code, _ = run(capsys)

    assert code == 0


# --- symlinked directories: never descended, never silent about it ----------------


def test_symlinked_directory_is_not_descended_into(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A violation reachable only through a symlinked directory is not caught.

    The real directory lives under a dot-prefixed name, so it is invisible to the
    walk on its own -- the non-hidden symlink alias is the only other way in, and
    since the control never follows it, the violation inside must go unseen.
    """
    real = repo / '.hidden_real'
    write(real, 'thing.py', 'x = eval("1")\n')
    link = repo / 'src' / 'linked'
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(real, link, target_is_directory=True)

    code, _out, err = run_full(capsys)

    assert code == 0
    assert 'linked' not in err


def test_symlinked_directory_not_descended_guard_is_load_bearing(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red-first proof: a walk that still descends into symlinks catches the violation above."""
    real = repo / '.hidden_real'
    write(real, 'thing.py', 'x = eval("1")\n')
    link = repo / 'src' / 'linked'
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(real, link, target_is_directory=True)

    def descending_walk(dir_path: Path, files: list[Path], skipped_symlinks: list[Path]) -> None:
        # Same body as ec._walk, minus the "it's a symlink, don't descend" skip.
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for entry in entries:
            if entry.is_dir():
                if ec._is_dir_excluded(entry):
                    continue
                descending_walk(entry, files, skipped_symlinks)
            elif entry.is_file() and entry.suffix == '.py':
                files.append(entry)

    monkeypatch.setattr(ec, '_walk', descending_walk)

    code, err = run(capsys)

    assert code == 1
    assert 'src/linked/thing.py' in err


def test_symlinked_directory_reported_informationally(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Meeting a symlinked directory in a scanned area prints an info line naming it."""
    real = repo / '.hidden_real'
    write(real, 'thing.py', 'x = 1\n')
    link = repo / 'src' / 'linked'
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(real, link, target_is_directory=True)

    code, out, _err = run_full(capsys)

    assert code == 0
    assert 'src/linked' in out
    assert 'not scanned' in out


def test_symlinked_directory_does_not_change_exit_code(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The info line is not a failure: a real violation elsewhere still drives the exit code,

    and its presence or absence is unaffected by an unrelated symlinked directory.
    """
    real = repo / '.hidden_real'
    write(real, 'thing.py', 'x = 1\n')
    link = repo / 'src' / 'linked'
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(real, link, target_is_directory=True)
    write(repo, 'src/seshat/thing.py', 'y = eval("1")\n')

    code, out, err = run_full(capsys)

    assert code == 1
    assert 'src/linked' in out
    assert 'src/seshat/thing.py:1' in err


def test_symlink_to_excluded_directory_pulls_nothing_in(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The finding that started this: an innocuously-named symlink into an excluded dir.

    `src/venv_alias -> .venv`-shaped: the link's own name is ordinary, so the old
    name-based exclusion check never saw it, and the old descent logic happily
    walked hundreds of third-party files behind it. Not descending into any
    symlinked directory removes the hole regardless of what it points to.
    """
    excluded_target = repo / '.venv'
    write(excluded_target, 'site-packages/thirdparty.py', 'x = eval("1")\n')
    alias = repo / 'src' / 'venv_alias'
    alias.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(excluded_target, alias, target_is_directory=True)

    code, _out, err = run_full(capsys)

    assert code == 0
    assert 'thirdparty.py' not in err


def test_symlink_cycle_does_not_crash(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A symlink pointing back at an ancestor must not raise. Trivially true now that no

    symlinked directory is ever descended into, but a regression here would be bad enough
    to pin anyway.
    """
    write(repo, 'src/seshat/thing.py', 'x = 1\n')
    loop = repo / 'src' / 'loop'
    os.symlink(repo / 'src', loop, target_is_directory=True)

    code, _ = run(capsys)

    assert code == 0


# --- unreadable files: reported, not fatal -----------------------------------------


def test_non_utf8_file_is_reported_and_scan_continues(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = repo / 'src' / 'seshat' / 'binaryish.py'
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b'x = 1  # \xff\xfe not valid utf-8\n')
    # Sorts after 'binaryish.py' so a return-on-first-error bug would hide this one.
    write(repo, 'src/seshat/zzz_later.py', 'y = eval("1")\n')

    code, err = run(capsys)

    assert code == 1
    assert 'binaryish.py' in err
    assert 'could not decode' in err
    assert 'src/seshat/zzz_later.py' in err


def test_syntax_error_file_is_reported_and_scan_continues(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, 'src/seshat/broken.py', 'def (:\n')
    write(repo, 'src/seshat/zzz_later.py', 'y = eval("1")\n')

    code, err = run(capsys)

    assert code == 1
    assert 'broken.py' in err
    assert 'could not parse' in err
    assert 'src/seshat/zzz_later.py' in err
