"""Acceptance test for T-02: `seshat --help` console script.

Invoked as a subprocess so the test proves the `[project.scripts]` entry point
wiring in `pyproject.toml`, not merely that `seshat.cli.main` exists.
"""

from __future__ import annotations

import subprocess

import pytest

from seshat.cli import main


def test_seshat_help_console_script_exits_zero_and_mentions_seshat() -> None:
    result = subprocess.run(
        ['uv', 'run', 'seshat', '--help'],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert 'seshat' in result.stdout


def test_main_exits_zero_with_no_subcommands() -> None:
    exit_code = main([])
    assert exit_code == 0


def test_main_help_flag_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    try:
        main(['--help'])
    except SystemExit as exc:
        assert exc.code == 0
    captured = capsys.readouterr()
    assert 'seshat' in captured.out
