"""Plain-text rendering shared by the CLI's read-only commands (T-11).

One function, one job: turn a `Citation` into the exact line shape AGENTS.md's
"Always" list requires — claim id via the caller, qualified name, file path,
line span, `verified_sha`, the claim's own status, and the verifier's last
status, with a stale citation saying so inline. No color library, no rich/
click/typer — this module hands back a plain `str`.
"""

from __future__ import annotations

from seshat.ledger.models import Citation

__all__ = ['format_citation']


def format_citation(c: Citation) -> str:
    """`{qualified_name} {file_path}:{start_line}-{end_line} @{sha} [{last_status}]`.

    `verified_sha` and `last_status` are both nullable (`Citation`'s
    docstring) — each renders as `-` when `None`, never a raw `None` or a
    crash on `[:8]`. `[STALE]` is appended when `c.claim_status == 'stale'`
    or `c.last_status == 'fail'`: two different reasons a citation can no
    longer be trusted (the claim itself was invalidated by drift, or its own
    verifier's last run failed), both surfaced the same way, inline.
    """
    sha = c.verified_sha[:8] if c.verified_sha else '-'
    last_status = c.last_status if c.last_status else '-'
    text = f'{c.qualified_name} {c.file_path}:{c.start_line}-{c.end_line} @{sha} [{last_status}]'
    if c.claim_status == 'stale' or c.last_status == 'fail':
        text += ' [STALE]'
    return text
