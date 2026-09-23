#!/usr/bin/env python3
"""Fitness control: no review-round citations in code comments, docstrings, or test
section headers.

governance: enforces DEC-4

Fails if a comment or docstring under `src/` or `tests/` cites review-process
history — "fix round 1", "fix round 2, item 1", "finding 4" — because this repo
squashes every PR to one commit before it lands on `develop`. Once squashed, a
round or finding number names a review artifact that no longer exists; the
citation reads as precise and points at nothing. Task ids (`T-15`, `PT-01`) are
house style and are never flagged — they name the task file, which survives the
squash. See DEC-4.

Scanning is comments (via `tokenize`) and docstrings (via `ast.get_docstring` on
the module, and on every class/function/async-function definition) — never
arbitrary string literals. A test fixture's source-as-a-string, e.g. a constant
holding `"# TODO: implement def check(graph)"` as *data* for a verifier-sandbox
test, is a `STRING` token to `tokenize` and an ordinary assignment's RHS to
`ast`, so it is never mistaken for this repo's own commentary. That distinction
is load-bearing: matching on raw text would flag the string fixtures already
in `tests/test_verify.py`, which quote round numbers as sandboxed *content*
under test, not as a citation.

Scope is `src/` and `tests/`, excluding `tests/fixtures/` (committed probe-repo
data, per DEC-2's precedent) and any hidden (dot-prefixed) or `__pycache__`
directory component. `docs/` is deliberately out of scope: the ledger and its
findings narrate review history on purpose, in prose meant to be read as
history, not as a live pointer into a PR.
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ('src', 'tests')
EXCLUDED_DIRS = {REPO_ROOT / 'tests' / 'fixtures'}
EXCLUDED_DIR_NAMES = {'__pycache__'}

PATTERN = re.compile(r'\bfix\s+round\b|\bfinding\s+\d', re.IGNORECASE)


def _is_dir_excluded(path: Path) -> bool:
    if path.name.startswith('.'):
        return True
    if path.name in EXCLUDED_DIR_NAMES:
        return True
    return path in EXCLUDED_DIRS


def _walk(dir_path: Path, files: list[Path]) -> None:
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: p.name)
    except OSError:
        return

    for entry in entries:
        if entry.is_dir():
            if _is_dir_excluded(entry) or entry.is_symlink():
                continue
            _walk(entry, files)
        elif entry.is_file() and entry.suffix == '.py':
            files.append(entry)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if root.is_dir():
            _walk(root, files)
    files.sort(key=lambda p: p.relative_to(REPO_ROOT).as_posix())
    return files


def _comment_hits(source: str) -> list[tuple[int, str]]:
    """Line numbers and text of comments matching PATTERN, via the real tokenizer."""
    hits: list[tuple[int, str]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT and PATTERN.search(tok.string):
                hits.append((tok.start[0], tok.string.strip()))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return hits


def _docstring_hits(tree: ast.Module) -> list[tuple[int, str]]:
    """Line numbers and text of module/class/function docstrings matching PATTERN."""
    hits: list[tuple[int, str]] = []
    nodes: list[ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = [tree]
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            nodes.append(node)

    for node in nodes:
        doc = ast.get_docstring(node)
        if doc and PATTERN.search(doc):
            body = node.body
            lineno = body[0].lineno if body else getattr(node, 'lineno', 1)
            snippet = next((line.strip() for line in doc.splitlines() if PATTERN.search(line)), doc.strip())
            hits.append((lineno, snippet))
    return hits


def main() -> int:
    violations: list[tuple[str, int, str]] = []
    unreadable: list[tuple[str, str]] = []

    for path in _iter_python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding='utf-8')
        except UnicodeDecodeError as exc:
            unreadable.append((rel, f'could not decode ({exc})'))
            continue

        for lineno, text in _comment_hits(source):
            violations.append((rel, lineno, text))

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            unreadable.append((rel, f'could not parse ({exc})'))
            continue

        for lineno, text in _docstring_hits(tree):
            violations.append((rel, lineno, text))

    violations.sort(key=lambda v: (v[0], v[1]))

    ok = True

    for offender, reason in unreadable:
        ok = False
        print(f'FAIL [DEC-4] {offender}: {reason}.', file=sys.stderr)

    for rel, lineno, text in violations:
        ok = False
        print(f'FAIL [DEC-4] {rel}:{lineno}: {text!r}', file=sys.stderr)
        print(
            '    cites review-round or finding history that a squashed PR erases — see DEC-4.',
            file=sys.stderr,
        )
        print(
            '    -> Reword to the plain reason for the code (task ids like T-15/PT-01 are fine).',
            file=sys.stderr,
        )

    if not ok:
        return 1
    print('ok [DEC-4] no review-round citations in src/ or tests/.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
