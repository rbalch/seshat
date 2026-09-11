"""The one way anything reads a target repo's source off disk. T-14.

Two functions, both pure: no `Graph`, no `Ledger`, no repo root — just an
absolute `Path` in, `bytes | None` or `str | None` out. Kept model-free and
import-light on purpose so `seshat.units` (deterministic code, no model
calls) can keep importing it without dragging anything above the model seam
along.

`read_source_bytes` hands raw bytes to a caller like `ast.parse`, which
honours a file's own PEP 263 coding declaration when given bytes rather than
a str decoded ahead of time with a guessed encoding — see
`docs/adr/0002-read-source-as-bytes-and-honour-declared-encodings.md`.
`read_source_text` is for callers that need text (prompts, spans): it uses
`tokenize.detect_encoding` to find the same declared encoding (or a BOM) and
decodes with `errors='replace'`, so a file that mostly decodes fine but has a
stray bad byte still returns text — degraded text beats no text for a
prompt, per AGENTS.md's failure direction.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path


def read_source_bytes(path: Path) -> bytes | None:
    """The file's raw bytes, or `None` if it can't be read at all.

    No decoding happens here — `ast.parse` accepts bytes and applies PEP 263
    itself, which is the whole point of keeping this function bytes-only.
    """
    try:
        return path.read_bytes()
    except OSError:
        return None


def read_source_text(path: Path) -> str | None:
    """Text for prompts and spans, or `None` if the file can't be read at all.

    Honours a coding declaration or BOM via `tokenize.detect_encoding`, then
    decodes with that encoding and `errors='replace'` — a file that decodes
    with a few replacement characters still returns text, not `None`. Only
    `OSError` (file missing/unreadable) or `detect_encoding` itself raising
    `SyntaxError` (a malformed coding declaration) produce `None`.
    """
    raw = read_source_bytes(path)
    if raw is None:
        return None
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    except SyntaxError:
        return None
    return raw.decode(encoding, errors='replace')
