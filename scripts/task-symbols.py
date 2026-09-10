#!/usr/bin/env python3
"""Advisory symbol check for one task file.

Reads a task file's frontmatter and body, pulls every backticked name out of its
``## Scope`` and ``## Acceptance`` sections only, and reports which of those names
resolve against ``src/`` (and, separately, ``tests/fixtures/``) and what kind of thing
each one actually is: a module-level function, a class, a method, a module-level
assignment, or a file path. It is an advisory reading aid for the ``planner`` (at
write time) and the ``task-critic`` (at dispatch time), never a gate: it always exits
0, on a clean task file, on one with unresolved names, and on a malformed one. It is
not wired into ``make check``, ``make controls``, ``make lint`` or ``make test``.

Usage::

    make task-symbols FILE=tasks/<slug>/T-NN-*.md
    # or: uv run python scripts/task-symbols.py tasks/<slug>/T-NN-*.md

Resolution is against the current working directory, matching how the make target
invokes it (from the repository root): ``src/`` and ``tests/fixtures/`` are read
relative to ``Path.cwd()``, and a ``path``-kind span is checked for existence the
same way.

The ``declared by this task`` exemption is presence-based, not a filename guess: a
name is only ever moved into that bucket once it actually resolves inside a file
listed in the task's own ``files:``. A name the task says it will create but has not
created yet stays in ``unresolved``, labelled ``claimed in Scope, not in files:`` so a
reader can tell it apart from a name that is simply wrong.

Identifiers are matched with ``\\w``, so a non-ASCII name (e.g. ``café_func``) is
treated like any other bare or dotted name; this script does not special-case script
or encoding.

An unterminated fenced-code block (an opening ``` with no closing partner) is
recovered rather than treated as "still fenced to EOF": everything from the
delimiter onward is scanned as ordinary content, and the report says so under a
``warnings`` heading, naming the line. Reporting a name that turns out to sit inside
a code sample costs a reader a moment; silently losing the rest of the file is the
failure this tool exists to avoid.

Two fences that are each independently unterminated sum to an even delimiter count
-- the same token sequence as one well-formed fenced block, by CommonMark's own
rules, so no amount of delimiter counting or per-fence tracking can tell the two
apart. Instead of guessing, whatever content a fence pairing actually drops is
checked for one of this tool's own known task-file section names (Goal, Scope,
Non-scope, Acceptance, Context, Manual QA) -- not any ``##``-shaped line, so a
fenced code sample's own unrelated banner (e.g. ``## Usage``) stays quiet. If it
finds one, the report warns that a section may be missing, named by line, rather
than staying silent. This
warning does not attempt to recover the dropped content -- there is no reliable way
to know which reading of the fences was intended, so guessing would trade a silent
loss for a wrong one.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

FRONT = re.compile(r'^---\n(.*?)\n---', re.DOTALL)
HEADER = re.compile(r'^##\s+(.+?)\s*$')
FENCE = re.compile(r'^\s*(```|~~~)')
BACKTICK = re.compile(r'`([^`]+)`')
# A dotted-or-bare name: unicode word characters and dots, not starting with a digit.
NAME = r'[^\d\W][\w.]*'
SIGNATURE = re.compile(rf'^({NAME})\((.*)\)$')
ARROW_SIGNATURE = re.compile(rf'^({NAME})\((.*)\)\s*->\s*({NAME})$')
IDENTIFIER = re.compile(rf'^{NAME}$')

SECTIONS_TO_SCAN = ('Scope', 'Acceptance')
# Every section name the task-file format (tasks/README.md) defines. Single source
# of truth for "is this really a task-file section header", so the swallowed-header
# warning in sections() cannot drift from what a header actually means here.
TASK_FILE_SECTIONS = frozenset(
    name.lower() for name in ('Goal', 'Scope', 'Non-scope', 'Acceptance', 'Context', 'Manual QA')
)
KNOWN_EXTENSIONS = (
    '.py',
    '.md',
    '.json',
    '.yaml',
    '.yml',
    '.toml',
    '.txt',
    '.db',
    '.cfg',
    '.ini',
    '.sh',
    '.js',
    '.ts',
    '.rst',
    '.lock',
)


def frontmatter(text: str) -> dict[str, object]:
    """Parse the ``---`` frontmatter block into a dict, best-effort.

    Scalars become strings; a ``key:`` with nothing after it, followed by indented
    ``- item`` lines, becomes a list. Returns ``{}`` for a file with no frontmatter
    block rather than raising — a malformed task file is something to report on, not
    crash on.
    """
    m = FRONT.match(text)
    if not m:
        return {}
    lines = m.group(1).splitlines()
    out: dict[str, object] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if ':' in line and not line.startswith(' '):
            k, v = line.split(':', 1)
            k = k.strip()
            v = v.split('#', 1)[0].strip()
            if v == '[]':
                out[k] = []
            elif v == '':
                items: list[str] = []
                j = i + 1
                while j < len(lines) and lines[j].startswith(' '):
                    item_line = lines[j].strip()
                    if item_line.startswith('- '):
                        items.append(item_line[2:].split('#', 1)[0].strip())
                    j += 1
                out[k] = items
                i = j - 1
            else:
                out[k] = v
        i += 1
    return out


def sections(body: str) -> tuple[dict[str, str], list[str]]:
    """Split the body on ``## Heading`` lines. Best-effort: no headers -> ``{}``.

    Tracks fenced-code state so a ``##``-looking line inside a ``` block is never
    mistaken for a real header, and accumulates content across repeated headers of
    the same name rather than overwriting -- both are silent-data-loss bugs
    otherwise: a real header line captured as body text, or an earlier section's
    content dropped outright.

    A fence that opens and never closes is a third way to lose content silently:
    treating "still in a fence" as a steady state would drop everything from the
    opener to EOF, headers included, and the report would show a false all-clear.
    Instead, an odd number of fence delimiters means the *last* one never really
    closed anything -- so it and everything after it is scanned as ordinary
    content, and a warning naming the line is returned alongside the sections.

    NOTE FOR THE NEXT EDITOR: fence handling and backtick-span matching have
    broken each other three times now. (1) A fence delimiter line contains
    literal backtick characters, which corrupts the naive backtick-pair regex
    downstream unless fenced lines are dropped before spans are extracted from
    the section text. (2) A single fence opened and never closed used to be
    treated as "in fence" forever, silently dropping everything to EOF; the odd/
    even parity check above and the recovery of the trailing unmatched delimiter
    fix that specific case. (3) Two *independent* fences that are each opened and
    never closed sum to an even delimiter count, which is byte-for-byte what one
    well-formed fenced block looks like -- CommonMark itself has no way to tell
    these apart, so no delimiter-counting or per-fence tracker can either. The
    guard below does not try: it inspects whatever a fence pairing actually
    dropped and warns if that content contains one of this tool's own known
    section headers (``TASK_FILE_SECTIONS``), because a vanished section is the
    one thing that actually matters, regardless of which reading of the fences
    produced it -- and a fenced code sample's unrelated ``## Usage`` banner is not
    that, so it stays quiet.
    """
    lines = body.splitlines()
    fence_line_indices = [i for i, line in enumerate(lines) if FENCE.match(line)]
    unterminated_index = fence_line_indices[-1] if len(fence_line_indices) % 2 == 1 else None
    warnings: list[str] = []
    if unterminated_index is not None:
        warnings.append(
            f'unterminated fence at line {unterminated_index + 1}: '
            'no closing delimiter found, content after it scanned as ordinary text'
        )

    def warn_if_fence_swallowed_a_header(fence_start: int, dropped: list[str]) -> None:
        for offset, dropped_line in enumerate(dropped):
            m = HEADER.match(dropped_line)
            # Matched the same way a real header is recognised below, but only
            # counts if the name is one of this tool's known task-file sections --
            # a fenced code sample's own "## Usage" banner or divider comment is
            # not task-file structure, and warning on it would just be noise.
            if m and m.group(1).strip().lower() in TASK_FILE_SECTIONS:
                header_line_no = fence_start + 2 + offset  # +1 for the delimiter, +1 to 1-index
                warnings.append(
                    f'fenced block starting at line {fence_start + 1} appears to have '
                    f'swallowed a section header at line {header_line_no} '
                    f'({dropped_line.strip()!r}); that section may be missing from this report'
                )

    out: dict[str, list[str]] = {}
    current: str | None = None
    buf: list[str] = []
    in_fence = False
    fence_start: int | None = None
    fence_buffer: list[str] = []
    for i, line in enumerate(lines):
        if FENCE.match(line):
            if i == unterminated_index:
                # This delimiter never closed anything. Drop just the delimiter
                # line itself (its literal backticks would otherwise corrupt
                # backtick-span matching downstream) and recover everything
                # after it as ordinary content -- never toggle into "in fence"
                # for a fence that has no partner.
                continue
            in_fence = not in_fence
            if in_fence:
                fence_start = i
                fence_buffer = []
            else:
                # Closing: whatever is in fence_buffer was just dropped, whether
                # this was a genuine fenced code sample or two unrelated
                # unterminated fences that happened to pair up syntactically.
                assert fence_start is not None
                warn_if_fence_swallowed_a_header(fence_start, fence_buffer)
                fence_start = None
                fence_buffer = []
            continue
        if in_fence:
            # The fence delimiter and everything inside it is code being quoted,
            # not prose to scan for backticked names -- and a fenced code sample
            # routinely contains its own literal backticks, which would otherwise
            # confuse the backtick-span matcher downstream. Drop it entirely (but
            # remember it, in case it turns out to have swallowed a header).
            fence_buffer.append(line)
            continue
        m = HEADER.match(line)
        if m:
            if current is not None:
                out.setdefault(current, []).append('\n'.join(buf))
            current = m.group(1).strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out.setdefault(current, []).append('\n'.join(buf))
    return {name: '\n'.join(parts) for name, parts in out.items()}, warnings


@dataclass
class Span:
    raw: str
    section: str
    kind: str  # path | dotted | bare | ignored
    name: str
    is_signature: bool


def classify_name(name: str, raw: str, section: str, is_signature: bool) -> Span:
    if any(ch.isspace() for ch in name) or '$' in name or name.startswith('-'):
        return Span(raw, section, 'ignored', name, is_signature)
    if '/' in name or any(name.endswith(ext) for ext in KNOWN_EXTENSIONS):
        return Span(raw, section, 'path', name, is_signature)
    if '.' in name:
        return Span(raw, section, 'dotted', name, is_signature)
    if IDENTIFIER.match(name):
        return Span(raw, section, 'bare', name, is_signature)
    return Span(raw, section, 'ignored', name, is_signature)


def classify(raw: str, section: str) -> list[Span]:
    """Classify one backticked span, possibly into more than one name.

    A signature with an arrow return type -- ``run_reflection(...) -> Summary`` --
    names two things at once: the callable and its return type. Both are checked;
    neither is silently dropped for not matching the plain ``Name(...)`` shape.
    """
    stripped = raw.strip()
    arrow = ARROW_SIGNATURE.match(stripped)
    if arrow:
        callable_name, _args, return_name = arrow.groups()
        return [
            classify_name(callable_name, raw, section, is_signature=True),
            classify_name(return_name, raw, section, is_signature=False),
        ]
    m = SIGNATURE.match(stripped)
    if m:
        return [classify_name(m.group(1), raw, section, is_signature=True)]
    return [classify_name(stripped, raw, section, is_signature=False)]


def extract_spans(body: str) -> tuple[list[Span], list[str]]:
    secs, warnings = sections(body)
    spans: list[Span] = []
    for name in SECTIONS_TO_SCAN:
        text = secs.get(name, '')
        for m in BACKTICK.finditer(text):
            spans.extend(classify(m.group(1), name))
    return spans, warnings


@dataclass
class SymbolIndex:
    functions: dict[str, list[tuple[Path, int]]] = field(default_factory=dict)
    classes: dict[str, list[tuple[Path, int]]] = field(default_factory=dict)
    methods: dict[str, list[tuple[Path, int]]] = field(default_factory=dict)
    method_bare: dict[str, list[tuple[Path, int, str]]] = field(default_factory=dict)
    assigns: dict[str, list[tuple[Path, int]]] = field(default_factory=dict)
    modules: dict[str, Path] = field(default_factory=dict)

    def add_file(self, root: Path, path: Path) -> None:
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            return
        rel = path.relative_to(root)
        parts = [*rel.parts[:-1], rel.stem]
        self.modules['.'.join(parts)] = path

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions.setdefault(node.name, []).append((path, node.lineno))
            elif isinstance(node, ast.ClassDef):
                self.classes.setdefault(node.name, []).append((path, node.lineno))
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        qualified = f'{node.name}.{item.name}'
                        self.methods.setdefault(qualified, []).append((path, item.lineno))
                        self.method_bare.setdefault(item.name, []).append((path, item.lineno, node.name))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.assigns.setdefault(target.id, []).append((path, node.lineno))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                self.assigns.setdefault(node.target.id, []).append((path, node.lineno))


def build_index(root: Path) -> SymbolIndex:
    idx = SymbolIndex()
    if not root.is_dir():
        return idx
    for path in sorted(root.rglob('*.py')):
        idx.add_file(root, path)
    return idx


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


@dataclass
class Resolution:
    label: str  # e.g. "module-level function", "method"
    path: Path
    lineno: int
    detail: str = ''  # extra qualifier, e.g. "(Worker.run_unit)"

    def render(self, name: str, *, fixture_only: bool = False) -> str:
        prefix = 'fixture-only ' if fixture_only else ''
        suffix = f' {self.detail}' if self.detail else ''
        return f'{name} → {prefix}{self.label}, {rel(self.path)}:{self.lineno}{suffix}'


def resolve_bare(name: str, idx: SymbolIndex) -> Resolution | None:
    if name in idx.functions:
        path, lineno = idx.functions[name][0]
        return Resolution('module-level function', path, lineno)
    if name in idx.classes:
        path, lineno = idx.classes[name][0]
        return Resolution('class', path, lineno)
    if name in idx.assigns:
        path, lineno = idx.assigns[name][0]
        return Resolution('module-level assignment', path, lineno)
    if name in idx.method_bare:
        path, lineno, cls = idx.method_bare[name][0]
        return Resolution('method', path, lineno, detail=f'({cls}.{name})')
    return None


def resolve_dotted(name: str, idx: SymbolIndex) -> Resolution | None:
    prefix, symbol = name.rsplit('.', 1)
    if prefix in idx.classes:
        qualified = f'{prefix}.{symbol}'
        if qualified in idx.methods:
            path, lineno = idx.methods[qualified][0]
            return Resolution('method', path, lineno, detail=f'({qualified})')
    if prefix in idx.modules:
        module_file = idx.modules[prefix]
        try:
            tree = ast.parse(module_file.read_text(), filename=str(module_file))
        except (SyntaxError, UnicodeDecodeError, OSError):
            return None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
                return Resolution('module-level function', module_file, node.lineno)
            if isinstance(node, ast.ClassDef) and node.name == symbol:
                return Resolution('class', module_file, node.lineno)
    return None


def resolve(name: str, kind: str, idx: SymbolIndex) -> Resolution | None:
    if kind == 'bare':
        return resolve_bare(name, idx)
    if kind == 'dotted':
        return resolve_dotted(name, idx)
    return None


def run(task_file: Path) -> str:
    try:
        text = task_file.read_text()
    except (UnicodeDecodeError, OSError) as exc:
        return f'task-symbols: {task_file}: could not read ({exc})\n'
    front = frontmatter(text)
    raw_files = front.get('files', [])
    files: list[str] = raw_files if isinstance(raw_files, list) else []
    spans, warnings = extract_spans(text)

    src_idx = build_index(Path.cwd() / 'src')
    fixture_idx = build_index(Path.cwd() / 'tests' / 'fixtures')

    seen: dict[str, Span] = {}
    for span in spans:
        seen.setdefault(span.name, span)

    resolved_lines: list[str] = []
    declared_lines: list[str] = []
    unresolved_lines: list[str] = []
    ignored_count = 0

    for name, span in seen.items():
        if span.kind == 'ignored':
            ignored_count += 1
            continue

        if span.kind == 'path':
            target = Path.cwd() / name
            if target.exists():
                resolved_lines.append(f'{name} → file, {name}')
            elif name in files:
                declared_lines.append(f'{name} → declared by this task (in files:)')
            else:
                unresolved_lines.append(f'{name} → unresolved, no such file')
            continue

        # dotted / bare
        found = resolve(name, span.kind, src_idx)
        if found is not None:
            if rel(found.path) in files:
                declared_lines.append(f'{found.render(name)} (declared by this task)')
            else:
                resolved_lines.append(found.render(name))
            continue

        found = resolve(name, span.kind, fixture_idx)
        if found is not None:
            resolved_lines.append(found.render(name, fixture_only=True))
            continue

        if span.is_signature and span.section == 'Scope':
            unresolved_lines.append(f'{name} → claimed in Scope, not in files:')
            continue

        unresolved_lines.append(f'{name} → unresolved, not found in src/ or tests/fixtures/')

    out: list[str] = []
    out.append(f'task-symbols: {task_file}')
    out.append('')
    if warnings:
        out.append(f'warnings ({len(warnings)})')
        out.extend(f'  {w}' for w in warnings)
        out.append('')
    out.append(f'resolved ({len(resolved_lines)})')
    out.extend(f'  {line}' for line in resolved_lines)
    out.append('')
    out.append(f'declared by this task ({len(declared_lines)})')
    out.extend(f'  {line}' for line in declared_lines)
    out.append('')
    out.append(f'unresolved ({len(unresolved_lines)})')
    out.extend(f'  {line}' for line in unresolved_lines)
    out.append('')
    out.append(
        f'{len(resolved_lines)} resolved, {len(declared_lines)} declared by this task, '
        f'{len(unresolved_lines)} unresolved, {ignored_count} ignored'
    )
    return '\n'.join(out) + '\n'


def main(path_str: str) -> None:
    task_file = Path(path_str)
    if not task_file.is_file():
        print(f'task-symbols: {task_file}: no such file')
        return
    print(run(task_file), end='')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('usage: task-symbols.py <task-file>')
    main(sys.argv[1])
