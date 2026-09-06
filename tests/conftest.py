"""Repo-wide pytest fixtures.

`fixture_target` and `fixture_graph_db` point at the hand-written probe repo under
`tests/fixtures/target/`, whose `.codegraph/codegraph.db` is committed alongside its
source (see `tests/fixtures/REBUILD.md`). Every later task's tests open that DB
read-only through these fixtures instead of re-deriving the path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / 'fixtures'


@pytest.fixture(scope='session')
def fixture_target() -> Path:
    """Absolute path to the fixture target repo root."""
    return (FIXTURES_DIR / 'target').resolve()


@pytest.fixture(scope='session')
def fixture_graph_db(fixture_target: Path) -> Path:
    """Absolute path to the fixture target's committed codegraph DB."""
    return fixture_target / '.codegraph' / 'codegraph.db'
