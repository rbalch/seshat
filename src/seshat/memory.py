"""Working memory: a `nooa-memory` store wired with the offline hashing embedder.

Hypotheses, recall queries, and dead ends live here, never in the ledger — see
AGENTS.md and tasks/seshat-phase-one/T-08-worker-agent.md scope item 1. Decay
stays on (`nooa_memory`'s default forgetting policy); nothing stored here is
meant to be durable, unlike the ledger's `.seshat/ledger.db`, which never decays.

This module never runs a full `nooa_memory.MemoryManager` (that mixin wires an
agent's event hooks, spontaneous recall, and reflection — none of which this
task needs): it talks to `nooa_memory.MemoryStore` and `RetrievalEngine`
directly, so `open_working_memory`/`seed_docs` are usable hermetically, with no
`nooa.Agent` in sight, exactly as the acceptance tests need them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from nooa_memory import HashingEmbedder, Memory, MemoryType
from nooa_memory.config import RetrievalConfig
from nooa_memory.retrieval import RetrievalEngine
from nooa_memory.store import MemoryStore

# A token immediately followed by `.` or `(` — the dot/paren is a lookahead
# filter, never captured, so `` `OrderRepository.get` `` yields
# `OrderRepository`, not `OrderRepository.get` (task scope item 1).
_TOKEN_BEFORE_DOT_OR_PAREN = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)(?=[.(])')

# Every paragraph seeded from a doc gets this tag, so a worker's `recall()`
# (or a future citation) can tell a doc-derived memory apart from one the
# worker wrote itself.
_README_TAG = 'source=readme'


def _looks_like_code_identifier(token: str) -> bool:
    """CamelCase (an uppercase letter after the first, alongside a lowercase
    one) or snake_case (an underscore anywhere) — the two shapes scope item 1
    calls out. An ordinary lowercase English word ending a sentence (`'the
    repository.'`) is neither, so it never sneaks in just because it precedes
    a period.
    """
    return '_' in token or (any(c.isupper() for c in token[1:]) and any(c.islower() for c in token))


def _find_code_identifiers(text: str) -> set[str]:
    return {token for token in _TOKEN_BEFORE_DOT_OR_PAREN.findall(text) if _looks_like_code_identifier(token)}


@dataclass
class WorkingMemory:
    """A `nooa_memory` store plus the hashing embedder and retrieval engine
    needed to write to and read from it, without an owning `nooa.Agent`.
    """

    store: MemoryStore
    embedder: HashingEmbedder
    retrieval: RetrievalEngine

    def remember(self, text: str, kind: str = 'scratch', *, tags: list[str] | None = None) -> str:
        """Write one memory of type `kind` (a `nooa_memory.MemoryType` value) and return its id."""
        memory = Memory(content=text, type=MemoryType(kind), tags=list(tags or []))
        embedding = self.embedder.embed(memory.embedding_text())
        self.store.add(memory, embedding)
        return memory.id

    def recall(self, query: str, k: int = 5) -> list[str]:
        """Associative + keyword recall (`RetrievalEngine.recall`), as plain text."""
        return [hit.content for hit in self.retrieval.recall(query, k=k)]


def open_working_memory(repo: Path) -> WorkingMemory:
    """A `WorkingMemory` backed by `<repo>/.seshat/memory.db`, the hashing embedder.

    The hashing embedder (`nooa_memory.HashingEmbedder`) is deterministic and
    offline — no external embedding service, and no non-determinism in tests.
    """
    path = Path(repo) / '.seshat' / 'memory.db'
    embedder = HashingEmbedder()
    store = MemoryStore(path, embedding_dim=embedder.dim)
    retrieval = RetrievalEngine(store, embedder, RetrievalConfig())
    return WorkingMemory(store=store, embedder=embedder, retrieval=retrieval)


def _doc_paths(repo: Path) -> list[Path]:
    """`README.md` (if present) then every `docs/**/*.md`, in a stable order."""
    paths: list[Path] = []
    readme = repo / 'README.md'
    if readme.is_file():
        paths.append(readme)
    docs_dir = repo / 'docs'
    if docs_dir.is_dir():
        paths.extend(sorted(docs_dir.rglob('*.md')))
    return paths


def seed_docs(memory: WorkingMemory, repo: Path) -> list[str]:
    """Store each paragraph of `README.md` and `docs/**/*.md` as an `info` memory.

    Each paragraph (text separated by a blank line) becomes one memory, typed
    `info` and tagged `source=readme` — a hypothesis, not a claim, per
    AGENTS.md's "Never: let a README statement into the ledger unverified."
    Returns the sorted set of code identifiers found across every paragraph
    (see `_looks_like_code_identifier`), for `build_queue`'s seed-name boost.
    """
    identifiers: set[str] = set()
    for path in _doc_paths(repo):
        text = path.read_text()
        for paragraph in text.split('\n\n'):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            memory.remember(paragraph, 'info', tags=[_README_TAG])
            identifiers |= _find_code_identifiers(paragraph)
    return sorted(identifiers)
