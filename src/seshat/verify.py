"""Runs a verifier's Python source against a `Graph` and says pass, fail or error.

A verifier is the thing that promotes a conjectured claim toward confirmed (T-08
decides confirmed/refuted; this module only reports pass/fail/error and records
the run). Three things run before, or in place of, the verifier's `check`
function ever mattering:

- an `ast` walk that rejects any `import` statement outside `json`/`re` before
  the source is ever executed;
- an explicit allow-list of builtins in the exec namespace (`_ALLOWED_BUILTINS`)
  — no `__import__`, `open`, `eval`, `exec`, `compile`, or anything else that
  reaches the interpreter or the filesystem directly;
- the tautology gate, `is_tautological`, which rejects a verifier whose only
  graph call re-queries the very unit its claim was derived from via
  `graph.node(...)` (or whose only `graph.node(...)` call cannot be proven,
  by a non-literal argument, to name a different unit at all) — that proves
  nothing, see AGENTS.md "Always: a check from a different angle than the
  claim". Any call to a graph method other than `node` proves real work
  regardless of its argument — `subclasses`, `callers`, `callees`, `imports`
  cannot be a disguised re-query of the unit by construction.

**What this does and does not close, stated plainly.** The import gate and
the builtins allow-list together close the *direct* routes to running
arbitrary code or reaching the filesystem: a verifier cannot `import os`,
cannot call `__import__('os')`, cannot `open()` a file, and cannot nest
another `eval`/`exec`. **They do not close attribute-traversal escapes, and
the gap is arbitrary code execution, not mere introspection**: a verifier
that reaches a live module through some object's internals without going
through any builtin at all — e.g. `().__class__.__bases__[0].__subclasses__()`,
or `json.__loader__.__class__.__init__.__globals__['sys']` — can run any
command the Seshat process itself can run (`os.system`, arbitrary subprocess
execution, filesystem writes, network calls), and the only thing standing
between that and a reported `pass` is that no verifier has been written to do
it. This is accepted for phase 1 only because verifier source is
model-authored against a trusted code graph, not attacker-supplied; it is not
safe against an adversarial verifier author. Closing it for real requires
process isolation, deferred to the phase-1.5 behavioral agent's sandbox; see
DEC-1 and `tests/test_verify.py`'s dunder-traversal test, which pins this gap
in the suite rather than leaving it implied.

**Sets vs. lists in a verifier's return value.** Every `Graph` accessor
(`subclasses`, `callers`, `callees`, `nodes`, ...) returns a `list`, in the
graph helper API's own query order — so a verifier that returns one of those
lists straight through inherits an ordering dependency on that query order,
even if the underlying claim does not actually depend on order (see
`_canonicalize`). A verifier whose claim is order-independent should wrap
the result in a `set` (or otherwise convert it) before returning, so
`_canonicalize` sorts it instead of comparing it position-by-position.

See AGENTS.md and tasks/seshat-phase-one/T-05-verifier-runner.md.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from seshat.graph import Graph, Node, _normalize_qname

if TYPE_CHECKING:
    from seshat.ledger.models import Verifier
    from seshat.ledger.store import Ledger

logger = logging.getLogger(__name__)

VerifierStatus = Literal['pass', 'fail', 'error']

# The only names an import statement in a verifier's source may bring in.
# `Graph`/`Node` are not importable by name — they are handed to the source
# through the namespace it runs in, never through an `import` — so they are
# not listed here; this set is purely about what `import`/`from ... import`
# statements are tolerated.
_ALLOWED_IMPORT_MODULES = {'json', 're'}

# Allow-list, not deny-list: `_build_namespace` hands the verifier's `check`
# exactly these names as `__builtins__`, and nothing else — CPython does not
# repopulate a dict-shaped `__builtins__`, so anything left out is simply
# unresolvable. Each entry below is either a plain data/algorithm builtin a
# structural verifier plausibly needs (comparing, sorting, counting, type
# checks), or `ValueError`/`Exception`, needed because
# `tests/test_verify.py`'s own regression source raises `ValueError` to
# simulate a verifier bug. Deliberately absent: `__import__`, `open`, `eval`,
# `exec`, `compile`, `input`, `breakpoint`, `globals`, `locals`, `vars`,
# `getattr`, `setattr`, `delattr` — every name that reaches the interpreter,
# the filesystem, or dynamic attribute access directly.
_ALLOWED_BUILTINS: dict[str, Any] = {
    'len': len,
    'sorted': sorted,
    'reversed': reversed,
    'enumerate': enumerate,
    'zip': zip,
    'range': range,
    'sum': sum,
    'min': min,
    'max': max,
    'any': any,
    'all': all,
    'abs': abs,
    'isinstance': isinstance,
    'str': str,
    'int': int,
    'float': float,
    'bool': bool,
    'list': list,
    'tuple': tuple,
    'dict': dict,
    'set': set,
    'frozenset': frozenset,
    'repr': repr,
    'type': type,
    'Exception': Exception,
    'ValueError': ValueError,
}


@dataclass(frozen=True)
class VerifierResult:
    status: VerifierStatus
    actual: Any | None
    error: str | None


def _find_check_function(tree: ast.Module) -> ast.FunctionDef | None:
    """The top-level `def check(graph): ...` the source must define, or `None`."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'check' and node.args.args:
            return node
    return None


def _find_disallowed_import(tree: ast.Module) -> str | None:
    """The first module name imported outside `_ALLOWED_IMPORT_MODULES`, or `None`.

    Walks the whole tree rather than trusting a naive `'import' in source`
    check, and runs before any `compile`/`exec` of the source — an `import` of
    a disallowed module is rejected structurally, never by letting it run and
    catching `ImportError`.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split('.')[0]
                if top not in _ALLOWED_IMPORT_MODULES:
                    return alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            top = module.split('.')[0]
            if top not in _ALLOWED_IMPORT_MODULES:
                return module or '<relative import>'
    return None


def _graph_calls_in(fn: ast.FunctionDef) -> list[tuple[str, str | None]]:
    """`(method_name, literal_first_arg_or_None)` for every `graph.<method>(...)` call in `fn`.

    Only calls whose receiver is the literal name `graph` count — the
    parameter name `check(graph)` is required to be exactly that by
    `_find_check_function` reading `def check(graph)` from the scope, so this
    does not need to resolve aliasing. `None` for the argument means the first
    argument is not a literal string (an f-string, a concatenation, a
    variable, ...) — `is_tautological` treats that as unknown, not as safe.
    """
    calls: list[tuple[str, str | None]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == 'graph'):
            continue
        first_arg = None
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            first_arg = node.args[0].value
        calls.append((func.attr, first_arg))
    return calls


def is_tautological(source: str, unit_qualified_name: str) -> str | None:
    """A reason string if `source`'s `check` cannot be proven to do real work, else `None`.

    Tautological when the source's only graph calls are `graph.node(...)` on
    `unit_qualified_name` (either the dotted or `::` name form), or when it
    makes no graph call at all. Only `graph.node(...)` can possibly be a
    disguised re-query of the unit — every other graph method (`subclasses`,
    `callers`, `callees`, `imports`, ...) is a check from a different angle
    *by construction*, whatever argument it is called with, so any call to a
    method other than `node` proves real work regardless of whether that
    argument is a literal string.

    A `graph.node(...)` call is only informative when its argument is a
    literal string: naming a different unit is a genuine different-angle
    check; naming `unit_qualified_name` itself is the tautology this gate
    exists to catch. A non-literal argument to `graph.node(...)` (an
    f-string, a concatenation, a variable) cannot be proven to be either —
    it is treated as unproven, not as evidence of real work, but it does not
    by itself make the verifier tautological if some other call already did.
    If nothing in the source proves real work — no call at all, only
    self-`graph.node(...)` calls, or only unprovable `graph.node(...)` calls —
    the gate fails closed and reports tautological.
    """
    tree = ast.parse(source)
    check_fn = _find_check_function(tree)
    if check_fn is None:
        return None  # not this gate's problem; run_verifier's `check` check catches it

    calls = _graph_calls_in(check_fn)
    if not calls:
        return 'tautology: verifier makes no graph call'

    target_forms = {unit_qualified_name, _normalize_qname(unit_qualified_name)}
    saw_real_angle = False
    for method, arg in calls:
        if method != 'node':
            saw_real_angle = True
            continue
        if arg is None:
            continue  # unprovable node lookup: not proof of real work, but not fatal on its own
        if arg not in target_forms:
            saw_real_angle = True
    if saw_real_angle:
        return None
    return (
        f'tautology: verifier does not prove work on a unit other than {unit_qualified_name!r} — its only '
        'graph calls are graph.node(...) on that same unit, and/or graph.node(...) calls whose argument is '
        'not a literal string and so cannot be proven to name a different unit'
    )


def _canonical_sort_key(item: Any) -> str:
    """A stable, total ordering key used when canonicalizing a `set`/`frozenset`.

    Elements are already plain JSON-safe values (dicts/lists/str/int/float/
    bool/None) by the time this runs, so a sorted-key JSON dump is a total
    order across mixed element types without inventing a bespoke comparator.
    """
    return json.dumps(item, sort_keys=True, default=str)


def _canonicalize(value: Any) -> Any:
    """`Node` -> dict of its five fields. `set`/`frozenset` sorted; `list`/`tuple` order preserved.

    The task contract is "lists sorted where they were sets", not "every
    list sorted": a verifier that returns a `set` (whose iteration order is
    not meaningful and not guaranteed stable across runs) must not fail on
    ordering, but a verifier that returns a `list`/`tuple` may be making a
    claim that genuinely depends on order, and canonicalizing that away would
    let a claim about order silently pass regardless of order. Applied to
    both `actual` and `expected` before comparison; `expected` (parsed from
    JSON) is always a `list`, so `expected`'s order is preserved the same way
    an ordered `actual` list's is — the verifier author who returns a `set`
    is expected to write `expected` in this function's own canonical sorted
    order to match.
    """
    if isinstance(value, Node):
        return {
            'qualified_name': value.qualified_name,
            'file_path': value.file_path,
            'kind': value.kind,
            'start_line': value.start_line,
            'end_line': value.end_line,
        }
    if isinstance(value, dict):
        return {key: _canonicalize(v) for key, v in value.items()}
    if isinstance(value, (set, frozenset)):
        canon_items = [_canonicalize(v) for v in value]
        return sorted(canon_items, key=_canonical_sort_key)
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    return value


def _build_namespace() -> dict[str, Any]:
    """The namespace a verifier's `check` runs in: an allow-list of builtins, `json`, `re`, `Graph`, `Node`.

    `'__builtins__'` is set to a plain `dict`, not the real `builtins` module
    or its `__dict__` — CPython only auto-populates `__builtins__` with the
    real builtins when the key is *absent*; handing it an explicit dict here
    means only these names are ever resolvable, never the rest of the real
    module.
    """
    return {
        '__builtins__': dict(_ALLOWED_BUILTINS),
        'json': json,
        're': re,
        'Graph': Graph,
        'Node': Node,
    }


def run_verifier(
    source: str,
    expected_json: str,
    graph: Graph,
    *,
    unit_qualified_name: str,
) -> VerifierResult:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return VerifierResult('error', None, f'source does not parse: {exc}')

    if _find_check_function(tree) is None:
        return VerifierResult('error', None, "source must define 'def check(graph): ...'")

    bad_import = _find_disallowed_import(tree)
    if bad_import is not None:
        return VerifierResult(
            'error',
            None,
            f'import of {bad_import!r} is not allowed: the verifier namespace exposes only '
            "an allow-list of builtins, 'json', 're', and the Graph/Node types",
        )

    tautology_reason = is_tautological(source, unit_qualified_name)
    if tautology_reason is not None:
        return VerifierResult('error', None, tautology_reason)

    namespace = _build_namespace()
    try:
        code = compile(tree, '<verifier>', 'exec')
        exec(code, namespace)  # this module *is* Seshat's own sandboxed exec, see module docstring
        actual = namespace['check'](graph)
    except Exception as exc:
        # A verifier erroring is an expected, routine outcome recorded as evidence by
        # design (a bad model-authored verifier), not a bug in the runner — so this
        # logs at DEBUG with `exc_info=True` rather than `logger.exception` (which
        # logs at ERROR): DEBUG is silent under any normal logging configuration, so
        # it does not bury real problems in thousands of routine `error` results, but
        # the full traceback is still there for anyone who turns DEBUG logging on to
        # investigate a specific run.
        logger.debug('verifier check() raised %s: %s', type(exc).__name__, exc, exc_info=True)
        return VerifierResult('error', None, f'{type(exc).__name__}: {exc}')

    try:
        expected = json.loads(expected_json)
    except json.JSONDecodeError as exc:
        return VerifierResult('error', None, f'expected_json does not parse: {exc}')

    canon_actual = _canonicalize(actual)
    canon_expected = _canonicalize(expected)
    if canon_actual == canon_expected:
        return VerifierResult('pass', None, None)
    return VerifierResult('fail', canon_actual, None)


def verify_and_record(ledger: Ledger, verifier: Verifier, graph: Graph, run_id: str) -> VerifierResult:
    """Run `verifier` and persist the outcome. Never touches the claim's status (T-08's job)."""
    citation = ledger.citation(verifier.claim_id)
    result = run_verifier(
        verifier.source,
        verifier.expected,
        graph,
        unit_qualified_name=citation.qualified_name,
    )
    ledger.record_verifier_run(verifier.id, result.status, result.error, run_id)
    return result
