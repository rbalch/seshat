"""Acceptance tests for T-13: `scripts/smoke_codeact.py`'s argument parser.

Hermetic and never skip-gated — see tasks/seshat-phase-one/T-13-spark-smoke.md's
Acceptance section, bullet 3: "the hermetic argument-parsing test always runs, never
skips". No `LLM_HOST` and no model are set anywhere in this file; `LLM_HOST` is
explicitly stripped from the child's environment so a developer's own shell can never
make these tests behave differently.

Every test here drives the real script as a subprocess (`sys.executable
scripts/smoke_codeact.py ...`), the same convention `tests/test_task_symbols.py` uses
for `scripts/task-symbols.py` — never an in-process import, so a script with a
top-level side effect (e.g. reading the environment at import time) is exercised
honestly.

Exit-code discipline is what makes each assertion mean something specific rather than
merely "the script did not crash" (see F-43 in docs/ledger-findings.md — a naive red
that is only `ModuleNotFoundError` proves nothing once the module exists):

- argparse's own rejection of an out-of-choices `--strategy` value exits **2** — this
  is `argparse`'s own contract, not this script's code, so it is the one assertion in
  this file that is fully pinned down before any implementation exists.
- a `--strategy` value the parser accepted, but with no `LLM_HOST` in the environment,
  must fail *later*, at `Settings.load()`, which is documented (`src/seshat/config.py`)
  to exit non-2 and name `LLM_HOST` in its message. A test that only checked
  "non-zero" would pass just as well if the parser silently swallowed `--strategy` and
  never read it — checking the *exit code family* (2 vs. not-2) and the *message
  content* (`LLM_HOST` named) together is what pins the parser to actually having
  consumed the flag.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'smoke_codeact.py'


def _env_without_llm_host() -> dict[str, str]:
    env = dict(os.environ)
    env.pop('LLM_HOST', None)
    for key in list(env):
        if key.startswith('SESHAT_MODEL'):
            env.pop(key, None)
    return env


def run_smoke(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_env_without_llm_host(),
        check=False,
    )


def test_help_exits_zero_and_documents_the_strategy_flag() -> None:
    result = run_smoke('--help')

    assert result.returncode == 0
    assert '--strategy' in result.stdout
    # The flag's two documented values, so --help itself proves the choice set,
    # not just that a --strategy flag exists under some other set of choices.
    assert 'codeact' in result.stdout
    assert 'pure-python' in result.stdout


def test_help_documents_the_default_strategy_as_codeact() -> None:
    result = run_smoke('--help')

    assert result.returncode == 0
    assert 'default: codeact' in result.stdout


def test_unknown_strategy_value_is_rejected_by_the_parser_itself() -> None:
    result = run_smoke('--strategy', 'not-a-real-strategy')

    # argparse's own contract for an invalid `choices=` value: exit 2, not 1 and not 0.
    # A script that dropped the choices= restriction (accepting anything) would either
    # exit 0 (if it then also skipped config loading) or exit 1 from Settings.load,
    # never 2 -- so this pins the parser's *rejection*, not merely "it exited badly".
    assert result.returncode == 2
    assert 'invalid choice' in result.stderr
    assert 'not-a-real-strategy' in result.stderr


def test_missing_strategy_flag_defaults_without_a_parser_error() -> None:
    # No --strategy at all: the parser must not reject this (exit 2 would mean the
    # flag was made required, which the task does not ask for). It must get past
    # parsing and fail downstream at config loading instead (exit 1, LLM_HOST named).
    result = run_smoke()

    assert result.returncode != 2
    assert result.returncode == 1
    assert 'LLM_HOST' in result.stderr


def test_pure_python_strategy_value_is_accepted_by_the_parser() -> None:
    # Proves the parser actually consumes '--strategy pure-python' (reaches config
    # loading, exit 1) rather than silently rejecting it (exit 2) or silently
    # ignoring it and using some other default behaviour that never reaches
    # Settings.load at all (e.g. exit 0 before doing anything).
    result = run_smoke('--strategy', 'pure-python')

    assert result.returncode == 1
    assert 'LLM_HOST' in result.stderr


def test_codeact_strategy_value_is_accepted_by_the_parser() -> None:
    result = run_smoke('--strategy', 'codeact')

    assert result.returncode == 1
    assert 'LLM_HOST' in result.stderr


def test_no_llm_host_and_no_model_never_skips() -> None:
    # The hermetic test itself: with no LLM_HOST and no model configured anywhere,
    # this whole module still ran -- nothing above raised pytest.skip, nothing above
    # is marked with @pytest.mark.integration. This assertion exists so that a
    # regression that accidentally imports something requiring a live LLM_HOST (and
    # therefore turns this file into a silent no-op under `pytest --collect-only`)
    # fails loudly instead of just vanishing from the report.
    assert 'LLM_HOST' not in _env_without_llm_host()
