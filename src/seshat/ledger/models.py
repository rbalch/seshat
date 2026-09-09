"""Frozen dataclasses mirroring the ledger tables in plan.md §4.

These are plain data carriers; the store (`store.py`) is the only code that turns
them into rows or rows back into them. Status fields are `Literal` types whose
members match the comments beside each column in plan.md §4 exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RunStatus = Literal['running', 'stopped_budget', 'stopped_complete', 'failed']
RunMode = Literal['claims', 'prose']

UnitKind = Literal['class', 'function', 'method', 'module']
UnitStatus = Literal['pending', 'scanned', 'changed', 'vanished']

ClaimKind = Literal['structural', 'behavioral']
ClaimSource = Literal['code', 'readme', 'docstring']
ClaimMode = Literal['claims', 'prose']
ClaimStatus = Literal['conjectured', 'confirmed', 'refuted', 'stale']

VerifierStatus = Literal['pass', 'fail', 'error']

ConceptStatus = Literal['current', 'stale']


@dataclass(frozen=True)
class Run:
    id: str
    repo_id: str
    commit_sha: str | None
    started_at: str | None
    finished_at: str | None
    model: str | None
    thinking: int
    workers: int
    budget_units: int | None
    budget_minutes: int | None
    budget_tokens: int | None
    units_done: int
    claims_confirmed: int
    claims_refuted: int
    tokens_used: int
    mode: RunMode
    status: RunStatus


@dataclass(frozen=True)
class Unit:
    id: str
    repo_id: str
    file_path: str
    qualified_name: str
    kind: UnitKind
    start_line: int
    end_line: int
    # `None` means the unit's file or symbol could not be found on the last
    # attempt to hash it — see `seshat.units.ast_hash` and T-06's contract
    # note: a `None` hash is exactly what drives a unit to `status='vanished'`
    # in `sync_units`, so the type has to admit it rather than force a sentinel
    # string into a column that means "no hash computed".
    ast_hash: str | None
    inbound_calls: int
    first_seen_run: str
    last_seen_run: str
    last_scanned_run: str
    status: UnitStatus


@dataclass(frozen=True)
class Claim:
    id: str
    repo_id: str
    unit_id: str
    text: str
    kind: ClaimKind
    source: ClaimSource
    mode: ClaimMode
    status: ClaimStatus
    confidence: float
    candidate_rule: int
    rule_sightings: int
    created_run: str
    verified_run: str | None
    verified_sha: str | None
    retries: int


@dataclass(frozen=True)
class Verifier:
    id: str
    repo_id: str
    claim_id: str
    source: str
    expected: str
    depends_on: list[str] = field(default_factory=list)
    last_run: str | None = None
    last_status: VerifierStatus | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class Concept:
    id: str
    repo_id: str
    title: str
    body: str
    created_run: str
    status: ConceptStatus


@dataclass(frozen=True)
class Citation:
    """What T-12 renders. All eight fields plan §4/AGENTS.md "Always" require.

    `claim_status` and `last_status` are two different axes and must not be
    conflated: `claim_status` is the claim's own lifecycle
    (conjectured/confirmed/refuted/stale), the thing a stale citation needs
    to say inline; `last_status` is the verifier's last execution outcome
    (pass/fail/error, or None if it has never run).
    """

    claim_id: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    verified_sha: str | None
    last_status: VerifierStatus | None
    claim_status: ClaimStatus
