#!/usr/bin/env python3
"""Fitness control: exec and eval are confined to src/seshat/verify.py.

governance: enforces DEC-2

Fails if a call to the `exec` or `eval` builtin appears in any scanned file other
than `src/seshat/verify.py`. Walks each file's `ast` rather than matching the
string `exec`/`eval` — a docstring, a comment, or `compile(tree, '<verifier>',
'exec')`'s string literal must not trip it, and `verify.py` itself contains
exactly that string alongside its one legitimate call. See DEC-2.

The scan set is derived, not a hand-maintained list of directory names — DEC-1's
`SCAN_DIRS = ['src', 'controls', 'governance', 'tests']` silently missed `scripts/`
(see DEC-2's Context and `docs/ledger-findings.md` F-42), and a longer list would
only repeat that failure the next time a source directory appears. Instead every
`.py` file under the repo root is scanned, except one lying under a hidden
(dot-prefixed) directory, a `node_modules/`, `dist/`, `build/`, or `__pycache__/`
directory, or `tests/fixtures/` (committed probe-repo data, never linted or
rewritten).

A symlinked directory is never descended into, full stop (see DEC-2's Rule). An
earlier version of this control tried to walk into one if its target resolved
inside the repo root and fail if it resolved outside -- that reopened the exact
hole it was meant to close: a symlink with an ordinary name pointing at an
excluded directory (`src/venv_alias -> .venv`) bypassed the exclusion entirely,
because the exclusion check only ever looked at the link's own name, dragging
`.venv`'s ~100 third-party files into the scan and turning a 0.4s run into 18s.
The same trick reaches `.claude/worktrees/`, which holds full checkouts of this
repo on other branches -- the one thing that must never be scanned. Not
descending removes the hole outright instead of adding a third layer of
guarding against it. This does mean code reachable only through a symlinked
directory is invisible to this control; that is accepted, not hidden -- meeting
one inside a scanned area prints an informational line naming it, without
changing the exit code.

A file that cannot be decoded as UTF-8, or does not parse as Python, is reported
as a failure for that file and the scan continues — one unreadable file must not
hide a real violation reported later, in sort order, in some other file.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_DIR_NAMES = {'node_modules', 'dist', 'build', '__pycache__'}
EXCLUDED_DIRS = {REPO_ROOT / 'tests' / 'fixtures'}
ALLOWED_PATH = REPO_ROOT / 'src' / 'seshat' / 'verify.py'
GUARDED_NAMES = {'exec', 'eval'}


def _is_dir_excluded(path: Path) -> bool:
    """Whether to skip this directory (and everything under it) entirely."""
    if path.name.startswith('.'):
        return True
    if path.name in EXCLUDED_DIR_NAMES:
        return True
    return path in EXCLUDED_DIRS


def _walk(dir_path: Path, files: list[Path], skipped_symlinks: list[Path]) -> None:
    """Depth-first walk collecting `.py` files. Never descends into a symlinked directory."""
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: p.name)
    except OSError:
        return

    for entry in entries:
        if entry.is_dir():
            if _is_dir_excluded(entry):
                continue
            if entry.is_symlink():
                skipped_symlinks.append(entry)
                continue
            _walk(entry, files, skipped_symlinks)
        elif entry.is_file() and entry.suffix == '.py':
            files.append(entry)


def _iter_python_files() -> tuple[list[Path], list[Path]]:
    """Return (files, skipped_symlinked_dirs) rooted at REPO_ROOT."""
    files: list[Path] = []
    skipped_symlinks: list[Path] = []
    _walk(REPO_ROOT, files, skipped_symlinks)
    files.sort(key=lambda p: p.relative_to(REPO_ROOT).as_posix())
    skipped_symlinks.sort(key=lambda p: p.relative_to(REPO_ROOT).as_posix())
    return files, skipped_symlinks


def _guarded_calls(tree: ast.Module) -> list[int]:
    """Line numbers of calls to a bare `exec`/`eval` name in this module's tree."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in GUARDED_NAMES:
            lines.append(node.lineno)
    return lines


def main() -> int:
    violations: list[tuple[str, int]] = []
    unreadable: list[tuple[str, str]] = []

    files, skipped_symlinks = _iter_python_files()

    for path in files:
        if path == ALLOWED_PATH:
            continue
        try:
            source = path.read_text(encoding='utf-8')
        except UnicodeDecodeError as exc:
            unreadable.append((path.relative_to(REPO_ROOT).as_posix(), f'could not decode ({exc})'))
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            unreadable.append((path.relative_to(REPO_ROOT).as_posix(), f'could not parse ({exc})'))
            continue

        for lineno in _guarded_calls(tree):
            violations.append((path.relative_to(REPO_ROOT).as_posix(), lineno))

    for link in skipped_symlinks:
        rel = link.relative_to(REPO_ROOT).as_posix()
        print(f'INFO [DEC-2] {rel}: symlinked directory, not scanned — see DEC-2.')

    ok = True

    for offender, reason in unreadable:
        ok = False
        print(f'FAIL [DEC-2] {offender}: {reason}.', file=sys.stderr)

    for offender, lineno in violations:
        ok = False
        print(f'FAIL [DEC-2] {offender}:{lineno}', file=sys.stderr)
        print(
            '    exec/eval may be called only from src/seshat/verify.py — see DEC-2.',
            file=sys.stderr,
        )
        print(
            "    -> Remove this call, or route the need through verify.py's existing "
            'sandboxed exec if it truly belongs there.',
            file=sys.stderr,
        )

    if not ok:
        return 1
    print('ok [DEC-2] exec/eval confined to src/seshat/verify.py.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
