#!/usr/bin/env python3
"""Fitness control: every fitness control has its own test module.

governance: enforces DEC-3

Fails if a `.py` module directly under `controls/fitness/` has no corresponding
`tests/controls/test_<stem>.py`, or if that test module exists but defines zero
`test_*` functions.

This does not check that the tests are *good* -- it cannot tell whether a guard
clause inside a control is actually exercised, only whether a test module exists
and is non-trivial. That narrower, mechanical claim is deliberate. See DEC-3's
Rule and Rejected alternatives for why a stronger claim (every branch a control
takes is provably load-bearing) is not attempted here.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROLS_DIR = REPO_ROOT / 'controls' / 'fitness'
TESTS_DIR = REPO_ROOT / 'tests' / 'controls'
EXCLUDED_NAMES = {'__init__.py'}


def _control_modules() -> list[Path]:
    if not CONTROLS_DIR.is_dir():
        return []
    return sorted(p for p in CONTROLS_DIR.glob('*.py') if p.name not in EXCLUDED_NAMES)


def _has_a_test_function(path: Path) -> bool:
    """Whether this module defines at least one `test_*` function, at any nesting."""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_')
        for node in ast.walk(tree)
    )


def main() -> int:
    missing: list[tuple[str, str]] = []
    empty: list[tuple[str, str]] = []

    for control in _control_modules():
        expected = TESTS_DIR / f'test_{control.stem}.py'
        rel_control = control.relative_to(REPO_ROOT).as_posix()
        rel_expected = (
            expected.relative_to(REPO_ROOT).as_posix()
            if TESTS_DIR.exists()
            else f'tests/controls/test_{control.stem}.py'
        )

        if not expected.is_file():
            missing.append((rel_control, rel_expected))
            continue
        if not _has_a_test_function(expected):
            empty.append((rel_control, rel_expected))

    ok = True

    for rel_control, rel_expected in missing:
        ok = False
        print(f'FAIL [DEC-3] {rel_control}: no test module at {rel_expected}.', file=sys.stderr)
        print(
            f'    -> Add {rel_expected} with at least one test_* function that proves the '
            'control by execution, not by reading.',
            file=sys.stderr,
        )

    for rel_control, rel_expected in empty:
        ok = False
        print(f'FAIL [DEC-3] {rel_control}: {rel_expected} defines no test_* function.', file=sys.stderr)
        print(
            '    -> A present-but-empty test module gives the same false confidence as no '
            'module at all -- add a real test.',
            file=sys.stderr,
        )

    if not ok:
        return 1
    print('ok [DEC-3] every controls/fitness/*.py module has a non-empty test module.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
