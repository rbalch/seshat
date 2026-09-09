---
adr-id: ADR-0002
status: accepted
date: 2026-09-09
components: [src/seshat/source.py, src/seshat/units.py, src/seshat/graph.py, src/seshat/agents/worker.py]
tags: [encoding, failure-direction, drift]
decision-makers: [ryan]
related-adrs: [ADR-0001]
supersedes: []
superseded-by: []
---

# ADR-0002: Read a target's source as bytes and honour declared encodings, rather than catching the decode error

## Summary (Y-Statement)

In the context of Seshat crashing on any repo containing one non-UTF-8 source file,
facing the choice between catching `UnicodeDecodeError` at each read site and reading
bytes so `ast.parse` can apply the file's own PEP 263 declaration, we decided for
reading bytes through one shared reader, plus a distinct `unreadable` unit status, and
against widening the existing `except` clauses, to achieve correct parsing of valid
non-UTF-8 Python and an honest, recoverable record of files we genuinely cannot read,
accepting a new module, a fourth unit status, and more code than a one-line fix.

## Context and Problem Statement

`Graph.decorators` (`graph.py:253`) and `ast_hash` (`units.py:80`) read a target's
source with `Path.read_text()`. Neither guards `UnicodeDecodeError`. Reproduced
end-to-end during planning: codegraph indexes a latin-1 Python file as a module node,
and `enumerate_units` — the first step of any scan — raises on it, so no scan of that
repo produces anything at all. Seshat's premise is surveying repos it did not write,
where a stray non-UTF-8 file is ordinary.

`worker.py`'s `_read_span` had the identical gap and was fixed in T-08 (PR #8) by
catching the error and returning `''`. Logged as `F-28`: one guard fixed, two
identical ones three modules away missed.

The obvious repair is to copy T-08's fix to the other two sites. The problem is that
those two sites parse, and `_read_span` does not.

## Decision Drivers

- `AGENTS.md`: ambiguity fails closed, never toward a false "unchanged" or a false
  "nothing found". A false success is always blocking.
- A claim's whole value is that it can be re-checked; a unit wrongly recorded as gone
  retires real claims about real code.
- `F-28`'s lesson: the same failure mode implemented separately at three sites drifts
  apart, and did.

## Considered Options

1. **Widen the `except` clauses** — add `UnicodeDecodeError` to each site, return
   `None`/`[]`.
2. **Read bytes and let `ast.parse` decode** — one shared reader; parse paths take
   bytes, the prompt path detects the encoding and falls back to `errors='replace'`.
3. **Detect the encoding and decode to text everywhere** — `tokenize.detect_encoding`
   at every site, then decode.

## Decision Outcome

Chosen: **option 2**, with a new `src/seshat/source.py` holding the only two functions
that read a target's source off disk, and a new `unreadable` unit status distinct from
`vanished`.

The deciding fact is that **a non-UTF-8 file is often perfectly valid Python**. PEP 263
lets a file declare its own encoding, and `ast.parse` applies that declaration when
given bytes. Verified during planning:

```
ast.parse(bytes) OK -> ['coût']          # '# -*- coding: latin-1 -*-'
read_text path CRASH: UnicodeDecodeError
```

So option 1 does not merely fail to fix the problem — it converts a loud crash into a
quiet wrong answer. Every file in this class would be hashed as `None`, marked
`vanished`, and have its claims retired, while the code sits there readable and
unchanged. That is a false "nothing here" about present code, which the failure-
direction rule forbids outright, and it would be invisible: no exception, no test
failure, just units quietly disappearing from repos that use a declared encoding.

Option 3 reaches the same correctness for the parse paths but decodes to text only to
have `ast` re-encode it, and needs its own fallback for undecodable files anyway. It is
option 2 with an extra step, and it keeps the encoding logic at each call site.

`_read_span` keeps a text path because a prompt needs a `str`, but it now honours the
declaration too and falls back to `errors='replace'` rather than the empty string T-08
shipped. Degraded text beats no text there: a weaker brief can only make the model's
claims weaker, never fabricate a passing verifier, because `verify_claim` still runs
the verifier against the graph.

### The `unreadable` status

`ast_hash` currently flattens two different facts into `None` — "the file could not be
read" and "the symbol is not in the file" — and both become `vanished`. Once encodings
are handled correctly the first case is rare, but it is also the one that can reverse:
a file may be readable tomorrow. `units.py` documents that a unit `vanished` on the
first sync that ever saw it has no recovery path, and that reasoning is right for a
deleted symbol and wrong for an unreadable file.

`unreadable` was chosen over reusing `vanished` even though it costs a fourth status,
because the alternative is a permanently invisible unit with no way back. It is cheap:
`status` is `TEXT NOT NULL` with no `CHECK`, so no migration, and `build_queue` selects
`pending` and `changed` by construction, so the new status is excluded from the queue
without touching it.

### Consequences

- Good: valid non-UTF-8 Python is parsed and hashed correctly instead of vanishing; a
  scan completes on any repo; one reader means the next fix lands in one place.
- Good: "cannot read" and "no longer exists" stop being the same row, and the first
  recovers.
- Bad: a new module, a fourth unit status, and a wider change than the one-line fix
  `F-28` implied.
- Bad: `errors='replace'` in the prompt path can put replacement characters in a
  brief. Accepted — the alternative is no source at all for that unit.
- Neutral: undeclared non-UTF-8 files still cannot be hashed. They are `unreadable`,
  reported, and recoverable, which is the honest answer rather than a guess at the
  encoding.

## More Information

`F-28` in `docs/ledger-findings.md`. Implemented by T-14. The crash was found by T-08's
builder while proving an unrelated fix red, in a module T-08 did not own, and reported
rather than patched.
