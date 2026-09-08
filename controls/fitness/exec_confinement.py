#!/usr/bin/env python3
"""Fitness control: exec and eval are confined to src/seshat/verify.py.

governance: enforces DEC-1

Fails if a call to the `exec` or `eval` builtin appears in any scanned file other
than `src/seshat/verify.py`. Walks each file's `ast` rather than matching the
string `exec`/`eval` — a docstring, a comment, or `compile(tree, '<verifier>',
'exec')`'s string literal must not trip it, and `verify.py` itself contains
exactly that string alongside its one legitimate call. See DEC-1.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ['src', 'controls', 'governance', 'tests']
EXCLUDED_DIRS = {REPO_ROOT / 'tests' / 'fixtures'}
ALLOWED_PATH = REPO_ROOT / 'src' / 'seshat' / 'verify.py'
GUARDED_NAMES = {'exec', 'eval'}


def _is_excluded(path: Path) -> bool:
    return any(excluded in path.parents or excluded == path for excluded in EXCLUDED_DIRS)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for scan_dir in SCAN_DIRS:
        root = REPO_ROOT / scan_dir
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*.py')):
            if not _is_excluded(path):
                files.append(path)
    return files


def _guarded_calls(tree: ast.Module) -> list[int]:
    """Line numbers of calls to a bare `exec`/`eval` name in this module's tree."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in GUARDED_NAMES:
            lines.append(node.lineno)
    return lines


def main() -> int:
    violations: list[tuple[str, int]] = []

    for path in _iter_python_files():
        if path == ALLOWED_PATH:
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        except SyntaxError as exc:
            print(f'FAIL [DEC-1] {path.relative_to(REPO_ROOT)}: could not parse ({exc}).', file=sys.stderr)
            return 1

        for lineno in _guarded_calls(tree):
            violations.append((path.relative_to(REPO_ROOT).as_posix(), lineno))

    for offender, lineno in violations:
        print(f'FAIL [DEC-1] {offender}:{lineno}', file=sys.stderr)
        print(
            '    exec/eval may be called only from src/seshat/verify.py — see DEC-1.',
            file=sys.stderr,
        )
        print(
            "    -> Remove this call, or route the need through verify.py's existing "
            'sandboxed exec if it truly belongs there.',
            file=sys.stderr,
        )

    if violations:
        return 1
    print('ok [DEC-1] exec/eval confined to src/seshat/verify.py.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
