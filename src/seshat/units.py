"""Unit enumeration, `ast_hash`, and drift diff — plan.md §5 steps 4-5.

Deterministic code, no model calls: list every unit codegraph knows about, hash
each one's own AST, upsert into the ledger, work out what changed or vanished
since the last run, mark the claims that rested on it stale, and hand back the
ordered work queue for a worker turn. See AGENTS.md and
tasks/seshat-phase-one/T-06-units-and-drift.md.

Two contract decisions made here, not in the task file, both documented at the
point they bite:

- `Unit.ast_hash` (`seshat/ledger/models.py`) is now `str | None` and the
  `units.ast_hash` column is nullable (was `NOT NULL`) — see the comments at
  both. `None` is not a sentinel string; it is the literal trigger for
  `status='vanished'` in `sync_units` below.
- Whether a docstring-only edit counts as a change is this module's call: it
  does. `ast_hash` hashes `ast.dump` verbatim (no attribute stripping beyond
  line numbers), and a docstring is an ordinary `ast.Expr`/`ast.Constant` node
  in that dump, so it is not special-cased out. A docstring is content a claim
  can cite, and AGENTS.md's failure direction is explicit: ambiguity about
  whether something changed fails closed toward "rerun the verifier", never
  toward a false "unchanged". Comments, unlike docstrings, never reach `ast`
  at all, so a comment-only edit is unchanged for free.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from seshat.graph import Graph, Node
from seshat.ledger.models import Unit, UnitKind, Verifier
from seshat.ledger.store import Ledger

# -- identity ----------------------------------------------------------------


def unit_id(file_path: str, qualified_name: str) -> str:
    """Stable id for `(file_path, qualified_name)`: sha256, first 32 hex chars."""
    digest = hashlib.sha256(f'{file_path}\0{qualified_name}'.encode()).hexdigest()
    return digest[:32]


# -- ast_hash ------------------------------------------------------------


def _find_symbol(
    body: list[ast.stmt], parts: list[str]
) -> ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Walk `body` following dotted `parts`, the same nesting `Graph._find_def`

    walks for decorators: a class holding a method, or a function holding a
    nested function (codegraph's `logged::wrapper` in the fixture target,
    normalized to `logged.wrapper` by `Graph`). Not shared with `graph.py`
    directly — `units.py` sits above the helper API seam in AGENTS.md's
    architecture diagram and reads source text itself, not through `Graph`.
    """
    name, rest = parts[0], parts[1:]
    for stmt in body:
        if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == name:
            if not rest:
                return stmt
            return _find_symbol(stmt.body, rest)
    return None


def ast_hash(repo: Path, node: Node) -> str | None:
    """Sha256 of the node's own AST, normalized so line numbers don't count.

    `None` if the file is missing or the symbol can no longer be found in it —
    both cases mean the same thing to a drift scan (the unit is gone) and both
    must never be mistaken for "unchanged": see the module docstring and
    AGENTS.md's failure direction.
    """
    source_path = repo / node.file_path
    try:
        source = source_path.read_text()
    except OSError:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    target: ast.AST
    if node.kind == 'module':
        target = tree
    else:
        found = _find_symbol(tree.body, node.qualified_name.split('.'))
        if found is None:
            return None
        target = found

    dumped = ast.dump(target, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode()).hexdigest()


# -- enumeration ---------------------------------------------------------


def enumerate_units(graph: Graph, repo: Path) -> list[Unit]:
    """One `Unit` per graph node of kind class/function/method, plus one
    `module` unit per Python file (codegraph's own `file` nodes, surfaced by
    `Graph` as `kind='module'`).

    Ledger-bookkeeping fields (`repo_id`, the three run-id fields, `status`)
    are placeholders here — `sync_units` is the only code that decides them,
    against what is already in the ledger.
    """
    units: list[Unit] = []
    for node in graph.nodes(kinds=['class', 'function', 'method', 'module']):
        units.append(
            Unit(
                id=unit_id(node.file_path, node.qualified_name),
                repo_id='',
                file_path=node.file_path,
                qualified_name=node.qualified_name,
                # Safe: graph.nodes(kinds=[...]) was asked for exactly these
                # four kinds, and Graph._row_to_node already maps codegraph's
                # own 'file' rows to 'module' before Node ever exists.
                kind=cast(UnitKind, node.kind),
                start_line=node.start_line,
                end_line=node.end_line,
                ast_hash=ast_hash(repo, node),
                inbound_calls=graph.inbound_call_count(node.qualified_name),
                first_seen_run='',
                last_seen_run='',
                last_scanned_run='',
                status='pending',
            )
        )
    return units


# -- drift diff ------------------------------------------------------------


@dataclass(frozen=True)
class UnitDiff:
    new: list[str]
    unchanged: list[str]
    changed: list[str]
    vanished: list[str]


def sync_units(ledger: Ledger, units: list[Unit], run_id: str) -> UnitDiff:
    """Upsert `units` into the ledger and report what moved since the last sync.

    - not in the ledger yet -> `new`: inserted `status='pending'`,
      `first_seen_run=last_seen_run=run_id`.
    - same `ast_hash` as the ledger row -> `unchanged`: `last_seen_run=run_id`,
      status left alone.
    - different `ast_hash` -> `changed`: `status='changed'`. `last_seen_run` is
      bumped (the unit was seen, just different), `last_scanned_run` is left at
      whatever it already was — nothing has actually scanned this unit this
      run, only detected that it moved. See the note on `set_unit_status`
      below for the corresponding case that could *not* be made to preserve
      this distinction.
    - `ast_hash is None` (the unit's node is still in the graph but its file or
      symbol can't be read/parsed right now), or a unit present in the ledger
      but absent from `units` entirely (its graph node itself is gone) ->
      `vanished`. Both sub-cases write `ast_hash=None` to the ledger row, not
      the last real hash that was there before — see the paragraph below on
      why a cached stale hash is a bug, not a nicety — and both go through
      `upsert_unit`, which is the only reason either can write `ast_hash` at
      all (`set_unit_status` cannot). `upsert_unit` unconditionally stamps
      `last_seen_run=run_id`, with no way to ask it to preserve the prior
      value, so both sub-cases bump `last_seen_run` even though, for the
      "node disappeared from `units` entirely" sub-case, nothing in this run
      actually saw the node at all — the semantically honest value would be
      `prior.last_seen_run`, unchanged. That mismatch is an accepted
      deviation, not an oversight: the alternative, going back to
      `set_unit_status` to keep `last_seen_run` exact, is what caused the
      permanent-vanished bug this docstring exists to explain, and a `last_seen_run`
      that is off by one run in a metadata column is a far smaller defect than
      a unit that can never recover. `last_scanned_run`, by contrast, *is*
      preserved exactly (`prior.last_scanned_run`) in both sub-cases, because
      `upsert_unit` only forces `last_seen_run`, not `last_scanned_run`.

    Decision: a unit can be `vanished` on the very first sync that ever sees
    it — the graph still lists the node (no `codegraph init` has run since),
    but its symbol or file is already gone by the time `ast_hash` reads the
    source, so `prior is None` and `unit.ast_hash is None` at once. That id
    still goes in `diff.vanished` below, and it is still given a real ledger
    row (`status='vanished'`, `ast_hash=None`, all three run-id fields stamped
    to this `run_id`) rather than only reported and left unpersisted. The
    alternative — drop the id from `vanished` because there is nothing to
    persist it against — was rejected: it hands a caller (`build_queue`, a
    future citation) an id with no way to tell "unresolvable" apart from "I
    made this id up by mistake," which is exactly the kind of silent gap
    AGENTS.md's failure direction warns against. A resolvable row that says
    `vanished` is honest about what happened; a bare id that resolves to
    nothing is not.

    Why every vanished row's `ast_hash` is nulled out, not left at its last
    real value: `set_unit_status` cannot write `ast_hash` at all, so an
    earlier version of this code called it for both vanished sub-cases and
    left the ledger's cached hash untouched. That is a real bug, not a
    historical nicety, and it showed up twice, independently, before being
    fixed both places — a transiently-unreadable file (a `SyntaxError`
    mid-edit) recovering to exactly its pre-corruption content
    (`test_transient_syntax_error_self_heals_into_changed`), and a node
    dropped from the graph entirely reappearing with byte-identical content
    (`test_node_removed_from_graph_then_reappears_self_heals_into_changed`).
    Both would compare their real, current hash against the stale cached one,
    read "same hash, no change," and leave `status` stuck at `'vanished'`
    forever — permanently invisible to `build_queue`, no path back. Writing
    `ast_hash=None` through `upsert_unit` for every vanished row, never
    through `set_unit_status`, means the next real hash, whatever it is,
    always compares unequal to `None` and the unit reliably falls into
    `changed` on recovery. `set_unit_status` is not called anywhere in this
    function any more, for exactly this reason.

    For changed and vanished units together, `ledger.mark_stale_for_units`
    marks their claims stale.

    Finding, not a fix: `Ledger.set_unit_status` (`ledger/store.py`) writes
    `status` and `last_scanned_run` together, so any future caller that uses
    it to flip a unit to `vanished` (or `changed`) inherits both the
    `last_scanned_run` stomp described below and the `ast_hash`-staleness bug
    described above — it should not be used for either transition, here or
    anywhere else this ledger is touched. `units.py` may not carry its own SQL
    (task Context) and does not own `store.py`, so this is reported rather
    than fixed at the source. This function itself no longer calls
    `set_unit_status` at all: every branch below builds its row from a real
    `Unit` (either the freshly enumerated one, or, for a node dropped from the
    graph entirely, `prior_row` in the loop below — the unit's own prior
    ledger row, which was a `Unit` all along) and writes it through
    `upsert_unit`.

    The one place `last_scanned_run` still gets stamped to `run_id` instead of
    preserved is the vanished-on-first-sight branch (`prior is None` and
    `unit.ast_hash is None`): it is forced, not a choice, because
    `units.last_scanned_run` is `NOT NULL` with a foreign key to `runs.id`,
    and there is no prior run to inherit a value from — the unit has never had
    a row before. The ordinary `new` branch is in the same position (no prior
    row either, so it too stamps all three run-id fields to `run_id`), but the
    two are not equally consequential: for `new`, the stamp is a temporary
    fiction a later real worker scan overwrites once the unit actually gets
    processed. For vanished-on-first-sight there is no such later scan to
    correct it — nothing will ever scan a unit that is already vanished, so
    this row's `last_scanned_run` will read "scanned in the run that
    discovered it was already gone" for as long as the row exists. Among the
    two vanished sub-cases specifically, this is the only one with no prior
    row to preserve `last_seen_run` or `last_scanned_run` from; the other
    vanished sub-case (a node still in `units`, or dropped from it entirely)
    always has a `prior` or `prior_row` to inherit `last_scanned_run` from,
    which is why only this one stamps both to `run_id`.
    """
    existing = {u.id: u for u in ledger.units()}
    seen_ids: set[str] = set()
    new_ids: list[str] = []
    unchanged_ids: list[str] = []
    changed_ids: list[str] = []
    vanished_ids: list[str] = []

    for unit in units:
        seen_ids.add(unit.id)
        prior = existing.get(unit.id)

        if unit.ast_hash is None:
            if prior is not None:
                # `unit.ast_hash` is already None here (that's why we're in
                # this branch) — write it through via upsert_unit rather than
                # `set_unit_status`, which cannot touch the ast_hash column at
                # all and would leave the row's last real hash cached. A
                # cached stale hash is not a historical nicety: the next sync
                # that restores the file byte-for-byte would then compare a
                # real hash against that same stale value, read "no change",
                # and leave `status='vanished'` forever — a unit that came
                # back stuck permanently invisible to `build_queue`. See
                # `test_transient_syntax_error_self_heals_into_changed`.
                lost = replace(
                    unit,
                    first_seen_run=prior.first_seen_run,
                    last_seen_run=run_id,
                    last_scanned_run=prior.last_scanned_run,
                    status='vanished',
                )
                ledger.upsert_unit(lost, run_id)
            else:
                # Vanished on first sight: never in the ledger, and already
                # unresolvable now. Persist it rather than reporting an id
                # ledger.unit() can't answer for — see the docstring above.
                stillborn = replace(
                    unit,
                    first_seen_run=run_id,
                    last_seen_run=run_id,
                    last_scanned_run=run_id,
                    status='vanished',
                )
                ledger.upsert_unit(stillborn, run_id)
            vanished_ids.append(unit.id)
            continue

        if prior is None:
            new_unit = replace(
                unit,
                first_seen_run=run_id,
                last_seen_run=run_id,
                last_scanned_run=run_id,
                status='pending',
            )
            ledger.upsert_unit(new_unit, run_id)
            new_ids.append(unit.id)
            continue

        if prior.ast_hash == unit.ast_hash:
            same = replace(
                unit,
                first_seen_run=prior.first_seen_run,
                last_seen_run=run_id,
                last_scanned_run=prior.last_scanned_run,
                status=prior.status,
            )
            ledger.upsert_unit(same, run_id)
            unchanged_ids.append(unit.id)
        else:
            moved = replace(
                unit,
                first_seen_run=prior.first_seen_run,
                last_seen_run=run_id,
                last_scanned_run=prior.last_scanned_run,
                status='changed',
            )
            ledger.upsert_unit(moved, run_id)
            changed_ids.append(unit.id)

    for existing_id, prior_row in existing.items():
        if existing_id not in seen_ids:
            # Same fix, same reason as the `unit.ast_hash is None` branch
            # above: write ast_hash=None through upsert_unit rather than
            # leaving the row's last real hash cached via set_unit_status,
            # which cannot touch that column. `prior_row` (the unit's own
            # prior ledger row) is already a `Unit` to build the upsert
            # from — there was no missing object here, only a branch that
            # hadn't been fixed yet.
            gone = replace(prior_row, ast_hash=None, status='vanished')
            ledger.upsert_unit(gone, run_id)
            vanished_ids.append(existing_id)

    stale_targets = changed_ids + vanished_ids
    if stale_targets:
        ledger.mark_stale_for_units(stale_targets, run_id)

    return UnitDiff(new=new_ids, unchanged=unchanged_ids, changed=changed_ids, vanished=vanished_ids)


def verifiers_to_rerun(ledger: Ledger, diff: UnitDiff, full: bool = False) -> list[Verifier]:
    """Verifiers to rerun after a sync: every verifier touching a changed or

    vanished unit, or every verifier at all if `full`. Actually rerunning them
    is T-09's job — this only names them.
    """
    if full:
        return ledger.all_verifiers()
    return ledger.verifiers_touching(diff.changed + diff.vanished)


# -- queue -----------------------------------------------------------------


def build_queue(ledger: Ledger, seed_names: set[str]) -> list[Unit]:
    """Pending + changed units, ordered for a worker to pick up.

    Seeded units (named in `seed_names`, e.g. from a doc seed) come first;
    within and after that, highest `inbound_calls` first so callees tend to be
    confirmed before their callers; ties broken by `(file_path, start_line)`
    for a deterministic order. `scanned` and `vanished` units are excluded by
    construction — only `pending` and `changed` rows are ever fetched.
    """
    candidates = ledger.units(status='pending') + ledger.units(status='changed')

    def sort_key(unit: Unit) -> tuple[bool, int, str, int]:
        not_seeded = unit.qualified_name not in seed_names
        return (not_seeded, -unit.inbound_calls, unit.file_path, unit.start_line)

    return sorted(candidates, key=sort_key)
