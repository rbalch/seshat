"""Acceptance tests for ``scripts/task-symbols.py`` (CT-01).

Every fixture task file and every fixture ``src/`` tree is built under ``tmp_path``.
Nothing here reads a real file under ``tasks/`` — that directory is untracked and will
not exist on another machine or in CI.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'task-symbols.py'


def run_task_symbols(cwd: Path, task_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(task_file)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def write_task(
    tmp_path: Path,
    *,
    files: list[str] | None = None,
    scope: str = '',
    acceptance: str = '',
    goal: str = '',
    non_scope: str = '',
    context: str = '',
    manual_qa: str = '',
    frontmatter: bool = True,
) -> Path:
    task_dir = tmp_path / 'tasks' / 'fixture-plan'
    task_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / 'T-01-fixture.md'
    body = ''
    if frontmatter:
        files_block = '\n'.join(f'  - {f}' for f in (files or []))
        body += textwrap.dedent(f"""\
            ---
            id: T-01
            plan: fixture-plan
            title: Fixture task
            depends_on: []
            files:
            {files_block}
            rules: []
            ---

            """)
    body += f'## Goal\n\n{goal}\n\n'
    body += f'## Scope\n\n{scope}\n\n'
    body += f'## Non-scope\n\n{non_scope}\n\n'
    body += f'## Acceptance\n\n{acceptance}\n\n'
    body += f'## Context\n\n{context}\n\n'
    body += f'## Manual QA\n\n{manual_qa}\n\n'
    task_file.write_text(body)
    return task_file


def make_src_file(tmp_path: Path, rel_path: str, code: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(code))
    return p


def test_undefined_name_reported_unresolved(tmp_path):
    task_file = write_task(tmp_path, scope='Calls `after_scan` when done.')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'unresolved' in result.stdout
    assert 'after_scan' in result.stdout


def test_module_level_function_resolves_with_kind_and_location(tmp_path):
    make_src_file(
        tmp_path,
        'src/pkg/worker.py',
        """
        def run_unit():
            pass
        """,
    )
    task_file = write_task(tmp_path, scope='Calls `run_unit` on each item.')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'run_unit' in result.stdout
    assert 'module-level function' in result.stdout
    assert 'src/pkg/worker.py:2' in result.stdout


def test_method_resolves_and_is_reported_as_method(tmp_path):
    make_src_file(
        tmp_path,
        'src/pkg/worker.py',
        """
        class Worker:
            def run_unit(self):
                pass
        """,
    )
    task_file = write_task(tmp_path, scope='Calls `run_unit` as a module-level function.')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'method' in result.stdout
    assert 'module-level function' not in result.stdout


def test_name_defined_only_in_fixtures_reported_as_fixture_not_missing(tmp_path):
    make_src_file(
        tmp_path,
        'tests/fixtures/target/scanner.py',
        """
        def scan_target():
            pass
        """,
    )
    task_file = write_task(tmp_path, scope='Calls `scan_target` on the tree.')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'fixture' in result.stdout
    # Not reported under the unresolved bucket.
    unresolved_section = result.stdout.split('declared by this task')[0]
    assert 'scan_target' not in unresolved_section or 'fixture' in unresolved_section


def test_path_declared_by_this_task_files_list(tmp_path):
    task_file = write_task(
        tmp_path,
        files=['src/seshat/newmod.py'],
        scope='Creates `src/seshat/newmod.py`.',
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'declared by this task' in result.stdout
    assert 'src/seshat/newmod.py' in result.stdout
    # Must not be filed as unresolved.
    unresolved_section = result.stdout.split('declared by this task')[0]
    assert 'src/seshat/newmod.py' not in unresolved_section


def test_sections_outside_scope_and_acceptance_are_not_extracted(tmp_path):
    task_file = write_task(
        tmp_path,
        goal='Uses `GoalOnlyName` somewhere.',
        non_scope='Never touches `NonScopeOnlyName`.',
        context='See `ContextOnlyName` for background.',
        manual_qa='Check `ManualQAOnlyName` by hand.',
        scope='Nothing new here.',
        acceptance='`make check` passes.',
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    for name in (
        'GoalOnlyName',
        'NonScopeOnlyName',
        'ContextOnlyName',
        'ManualQAOnlyName',
    ):
        assert name not in result.stdout


def test_shell_commands_and_flags_are_ignored(tmp_path):
    task_file = write_task(
        tmp_path,
        scope='Run `--units 2` for a quick pass.',
        acceptance='`uv run pytest -q` and `make check` both exit 0.',
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    unresolved_section = result.stdout.split('declared by this task')[0]
    for token in ('uv run pytest -q', 'make check', '--units 2'):
        assert token not in unresolved_section
    assert 'ignored' in result.stdout.lower()


def test_exit_code_zero_when_names_unresolved(tmp_path):
    task_file = write_task(tmp_path, scope='Calls `TotallyMissingSymbol`.')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'unresolved' in result.stdout
    assert 'TotallyMissingSymbol' in result.stdout


def test_exit_code_zero_on_malformed_task_file_no_frontmatter_no_sections(tmp_path):
    task_dir = tmp_path / 'tasks' / 'fixture-plan'
    task_dir.mkdir(parents=True)
    task_file = task_dir / 'T-99-broken.md'
    task_file.write_text('just some prose, no frontmatter, no headers at all\n')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    # It says what it found (nothing), rather than crashing silently.
    assert '0 resolved' in result.stdout
    assert '0 unresolved' in result.stdout


def test_missing_path_reported_unresolved(tmp_path):
    task_file = write_task(tmp_path, acceptance='Check that `src/does/not/exist.py` is present.')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'unresolved' in result.stdout
    assert 'src/does/not/exist.py' in result.stdout


def test_regression_bare_run_unit_reports_kind_not_verdict(tmp_path):
    """F-24-shaped regression: a bare name resolves as a module-level function
    while a same-named method does not exist on an unrelated class. The tool
    must report the *kind*, never a verdict on whether the task file is right.
    """
    make_src_file(
        tmp_path,
        'src/pkg/worker.py',
        """
        def run_unit():
            pass


        class Worker:
            pass
        """,
    )
    task_file = write_task(tmp_path, scope='Calls `run_unit` on each item.')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'module-level function' in result.stdout
    assert 'src/pkg/worker.py' in result.stdout


def test_make_task_symbols_target_present_and_not_gated():
    makefile = (ROOT / 'Makefile').read_text()
    assert re.search(r'(?m)^task-symbols:', makefile), 'task-symbols target missing from Makefile'

    def recipe_for(target: str) -> str:
        m = re.search(rf'(?m)^{re.escape(target)}:.*$\n((?:^\t.*\n?)*)', makefile)
        assert m, f'{target} target not found'
        return m.group(0)

    for gate in ('check', 'controls', 'lint', 'test'):
        recipe = recipe_for(gate)
        assert 'task-symbols' not in recipe, f'{gate} must not reach task-symbols'


# --- Fix round 1 -------------------------------------------------------------
#
# Reviewers found the "declared by this task" exemption was a heuristic (item 1),
# section parsing silently drops content (item 2), the tool can crash on unreadable
# input (item 3), and an arrow-return signature loses both names (item 4).


def test_unrelated_files_entry_does_not_exempt_signature_shaped_name(tmp_path):
    """The `after_scan(ledger, run)` case from the task file itself: a `files:`
    entry that does not actually define the name must NOT exempt it. Presence,
    not plausibility -- an unrelated .py entry in `files:` is not enough.
    """
    task_file = write_task(
        tmp_path,
        files=['src/seshat/unrelated.py'],
        scope='Calls `after_scan(ledger, run)` once the scan completes.',
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'claimed in Scope, not in files:' in result.stdout
    declared_section = result.stdout.split('declared by this task (')[1].split('unresolved (')[0]
    assert 'after_scan' not in declared_section


def test_signature_shaped_name_actually_defined_in_a_listed_file_is_declared(tmp_path):
    """The positive case: the name is exempt only once it is actually present in a
    file the task lists in `files:` -- not because the filename looks plausible.
    """
    make_src_file(
        tmp_path,
        'src/pkg/created.py',
        """
        def after_scan(ledger, run):
            pass
        """,
    )
    task_file = write_task(
        tmp_path,
        files=['src/pkg/created.py'],
        scope='Calls `after_scan(ledger, run)` once the scan completes.',
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    declared_section = result.stdout.split('declared by this task (')[1].split('unresolved (')[0]
    assert 'after_scan' in declared_section


def test_fenced_code_block_does_not_end_a_section_early(tmp_path):
    scope = (
        'before the fence.\n\n'
        '```\n'
        'some code\n'
        '## not a real header\n'
        'more code\n'
        '```\n\n'
        'after the fence, calls `after_fence_symbol`.\n'
    )
    task_file = write_task(tmp_path, scope=scope)
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'after_fence_symbol' in result.stdout


def test_repeated_section_header_accumulates_instead_of_overwriting(tmp_path):
    task_dir = tmp_path / 'tasks' / 'fixture-plan'
    task_dir.mkdir(parents=True)
    task_file = task_dir / 'T-02-repeated.md'
    task_file.write_text(
        '---\n'
        'id: T-02\n'
        'plan: fixture-plan\n'
        'title: Repeated headers\n'
        'depends_on: []\n'
        'files: []\n'
        'rules: []\n'
        '---\n\n'
        '## Scope\n\n'
        'Calls `first_symbol`.\n\n'
        '## Non-scope\n\n'
        'Nothing.\n\n'
        '## Scope\n\n'
        'Also calls `second_symbol`.\n\n'
        '## Acceptance\n\n'
        '`make check` passes.\n'
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'first_symbol' in result.stdout
    assert 'second_symbol' in result.stdout


def test_unreadable_task_file_exits_zero_and_reports_could_not_read(tmp_path):
    task_dir = tmp_path / 'tasks' / 'fixture-plan'
    task_dir.mkdir(parents=True)
    task_file = task_dir / 'T-03-binary.md'
    task_file.write_bytes(b'\xff\xfe\x00\x01not valid utf-8 \xff')
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'could not read' in result.stdout.lower()


def test_arrow_return_signature_checks_both_names(tmp_path):
    task_file = write_task(
        tmp_path,
        scope='Adds `run_reflection(agent, ledger, run_id, batch_size=40) -> ReflectionSummary`.',
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'run_reflection' in result.stdout
    assert 'ReflectionSummary' in result.stdout


# --- Fix round 2 -------------------------------------------------------------
#
# An unclosed fence must recover rather than silently swallow the rest of the
# file (item 1), and the resolved-vs-declared membership check needs a test of
# its own so a "files: merely non-empty" mutation cannot ship unnoticed (item 2).


def test_unterminated_fence_recovers_content_and_warns(tmp_path):
    scope = (
        'before the fence.\n\n'
        '```\n'
        'some code that never gets a closing fence\n'
        'calls `after_unclosed_fence_symbol` right here.\n'
    )
    task_file = write_task(
        tmp_path,
        scope=scope,
        acceptance='`make check` passes.',
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    # The warning names the problem instead of staying silent about it.
    assert 'unterminated fence' in result.stdout.lower()
    # And the content after the unclosed fence was not simply dropped: the
    # summary is not a false all-clear, and the symbol is still reported.
    assert 'after_unclosed_fence_symbol' in result.stdout
    assert '0 resolved, 0 declared by this task, 0 unresolved, 0 ignored' not in result.stdout


def test_resolved_name_not_in_files_stays_resolved_not_declared(tmp_path):
    """Pins the membership check itself: a name resolving in a file that is NOT
    in this task's `files:` must be plain `resolved`, never `declared by this
    task`, even though `files:` is non-empty. A mutation that loosens the check
    to "files: is merely non-empty" must fail this test.
    """
    make_src_file(
        tmp_path,
        'src/pkg/other.py',
        """
        def some_helper():
            pass
        """,
    )
    task_file = write_task(
        tmp_path,
        files=['src/pkg/unrelated_target.py'],
        scope='Calls `some_helper` internally.',
    )
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    resolved_section = result.stdout.split('resolved (')[1].split('declared by this task (')[0]
    assert 'some_helper' in resolved_section
    declared_section = result.stdout.split('declared by this task (')[1].split('unresolved (')[0]
    assert 'some_helper' not in declared_section


# --- Fix round 3 -------------------------------------------------------------
#
# Two fences that are each independently opened and never closed sum to an even
# delimiter count -- indistinguishable, by CommonMark's own rules, from one
# well-formed fenced block. A parity check sees nothing wrong, so a real section
# header and a real symbol between the two "opens" are dropped with zero warning.
# The fix does not try to tell the two cases apart (it can't); it warns whenever
# whatever got fenced off looks like it contained real task-file structure.


def test_two_unterminated_fences_that_pair_up_still_warn_about_swallowed_header(tmp_path):
    """The reviewer's exact case: two fences, each opened and never closed by its
    author, one in Scope and one meant to start in Acceptance, with a real
    header and a real symbol dropped in between. Today this produces zero
    warnings and the symbol never appears anywhere in the report.
    """
    scope = (
        'before the fences.\n\n'
        '```\n'
        'fence one, meant to never close\n\n'
        '## Acceptance\n\n'
        'Calls `swallowed_symbol` in between the two fences.\n'
        '```\n\n'
        'fence two, also meant to never close, but pairs with fence one instead.\n'
    )
    task_file = write_task(tmp_path, scope=scope)
    result = run_task_symbols(tmp_path, task_file)
    assert result.returncode == 0
    assert 'swallowed a section header' in result.stdout.lower()
    assert '## Acceptance' in result.stdout


# --- Fix round 4 -------------------------------------------------------------
#
# The swallowed-header warning fired on any `##`-shaped line, including a
# legitimate fenced code sample's own section divider or usage banner. Narrowed
# to the task-file section names this tool already knows.


def test_swallowed_header_warning_ignores_non_task_section_names_but_still_fires_on_real_ones(
    tmp_path,
):
    # A fenced code sample with its own, unrelated "## Usage" banner: no warning.
    usage_scope = (
        'before the fence.\n\n```\nsome cli --help output\n\n## Usage\n\ndo the thing\n```\n\nafter the fence.\n'
    )
    usage_task = write_task(tmp_path, scope=usage_scope)
    usage_result = run_task_symbols(tmp_path, usage_task)
    assert usage_result.returncode == 0
    assert 'swallowed a section header' not in usage_result.stdout.lower()

    # A fenced code sample that swallows a real task-file section name: still warns.
    accept_scope = (
        'before the fence.\n\n'
        '```\n'
        'some code\n\n'
        '## Acceptance\n\n'
        'Calls `swallowed_by_real_section` here.\n'
        '```\n\n'
        'after the fence.\n'
    )
    accept_task = write_task(tmp_path, scope=accept_scope)
    accept_result = run_task_symbols(tmp_path, accept_task)
    assert accept_result.returncode == 0
    assert 'swallowed a section header' in accept_result.stdout.lower()
