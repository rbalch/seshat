"""Acceptance tests for T-14 — the one shared source reader.

Each test below corresponds to one bullet of the Acceptance section of
tasks/seshat-phase-one/T-14-unreadable-source-files.md. Committed alone,
before any implementation exists, per the project's red-then-green contract.
"""

from __future__ import annotations

from pathlib import Path

from seshat.source import read_source_bytes, read_source_text

# Valid Python under a PEP 263 declaration: latin-1 bytes with a coding
# declaration naming latin-1. From the task's Context section.
_LATIN1_DECLARED = '# -*- coding: latin-1 -*-\ndef co\xfbt():\n    return 1\n'.encode('latin-1')

# Undeclared non-UTF-8 bytes, this module's own test data (not one of the
# Context's three labelled byte strings): `tokenize.detect_encoding` only
# inspects the first two physical lines looking for a coding cookie, so the
# bad byte has to sit past that point or detect_encoding raises `SyntaxError`
# itself ("invalid or missing encoding declaration") rather than exercising
# the `errors='replace'` decode this test is actually about.
_UNDECLARED_UNDECODABLE = b'x = 1\ny = 2\nz = "co\xfbt"\n'


def test_read_source_bytes_returns_raw_bytes_of_a_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / 'mod.py'
    path.write_bytes(b'def f():\n    return 1\n')

    assert read_source_bytes(path) == b'def f():\n    return 1\n'


def test_read_source_bytes_returns_none_for_missing_path(tmp_path: Path) -> None:
    assert read_source_bytes(tmp_path / 'does_not_exist.py') is None


def test_read_source_text_on_declared_latin1_file_decodes_correctly(tmp_path: Path) -> None:
    path = tmp_path / 'mod.py'
    path.write_bytes(_LATIN1_DECLARED)

    text = read_source_text(path)

    assert text is not None
    assert 'coût' in text
    # Not replacement characters -- a real decode using the declared encoding.
    assert '�' not in text


def test_read_source_text_on_undeclared_non_utf8_bytes_returns_text_not_none(tmp_path: Path) -> None:
    path = tmp_path / 'mod.py'
    path.write_bytes(_UNDECLARED_UNDECODABLE)

    text = read_source_text(path)

    assert text is not None
    assert isinstance(text, str)


def test_read_source_text_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert read_source_text(tmp_path / 'does_not_exist.py') is None
