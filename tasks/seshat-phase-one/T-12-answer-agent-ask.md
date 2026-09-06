---
id: T-12
plan: seshat-phase-one
title: Answer agent and seshat ask
status: todo
depends_on: [T-11]
files:
  - src/seshat/agents/answer.py
  - src/seshat/cli.py
  - tests/agents/test_answer.py
rules: []
---

## Goal

`seshat ask <repo>` is a REPL over the ledger. The answer agent searches claims and
concepts through tools, answers with at least one citation per sentence, and says
"nothing in the ledger" when the search comes back empty. It never reads working
memory.

## Scope

1. `AnswerAgent(nooa.Agent)`, `CodeActStrategy`, tools:
   - `search_claims(query) -> list[dict]` and `search_concepts(query) -> list[dict]`
     over the ledger FTS, each hit carrying its citation string;
   - `claims_for(qualified_name) -> list[dict]`;
   - `concept(id) -> dict` with evidence citations.
   Generation method `answer(self, question: str) -> Answer: ...` returning
   `Answer(sentences: list[Sentence])`, `Sentence(text: str, citations: list[str])`
   where each citation is a claim or concept id.
2. `validate_answer(answer, ledger) -> Answer`: deterministic. Drops any citation id
   that does not exist in the ledger; a sentence left with no citation is replaced
   by `[uncited sentence removed]`; an answer with no cited sentence at all becomes
   the single sentence `Nothing in the ledger answers that.` with no citations.
3. `render_answer(answer, ledger) -> str`: each sentence followed by its citations
   through `format_citation` (T-11), stale ones marked.
4. `seshat ask <repo> [--no-thinking] [--model MODEL]`: prompt loop on stdin,
   `exit` or EOF ends it; `seshat ask <repo> -q "question"` answers once and exits.
5. The agent has no memory tool and no access to `.seshat/memory.db`.

## Non-scope

- No vectors, no embeddings, no cross-repo search (plan §10 phase 2).
- No answer from the model's own knowledge: `validate_answer` is what enforces it,
  and the prompt says so too.

## Acceptance

- `uv run pytest tests/agents/test_answer.py -q` → exit 0, hermetic, on a ledger
  filled with a few confirmed claims and one concept, covers:
  - `validate_answer` drops unknown citation ids and removes uncited sentences;
  - an answer with no valid citations becomes exactly the "Nothing in the ledger"
    sentence;
  - `render_answer` marks a stale claim's citation `[STALE]`;
  - `search_claims('OrderNotFound')` returns a hit with a citation string;
  - with `FakeLLMClient` scripted to return an `Answer` citing one real id,
    `ask -q` prints the sentence and its citation, exit 0;
  - the agent's tool list (introspected from the class) contains no `recall` or
    memory method.
- `uv run pytest -m integration tests/agents/test_answer.py -q` → skipped without
  `LLM_HOST`; with it, one real question over a scanned fixture returns at least
  one cited sentence.
- `uv run seshat --help` lists `ask`.
- `make check` → exit 0

## Context

- plan §2 (answer row), §7 contract, §9 acceptance questions, §11 "Doc seeds
  leaking as facts". Decisions Q12, Q26, Q27. `AGENTS.md` Never: the answer agent
  cites working memory or writes an uncited sentence.
- FTS methods and `citation()` are in `ledger/store.py` (T-03); `format_citation`
  in `render.py` (T-11).

## Manual QA

The phase-one bar: ask the five questions from plan §9 against
`~/code/labs-OO-Agents` after a full scan. Questions 3 and 4 must cite a source
constant, not the README. Then edit one function, rescan, and confirm `seshat
drift` names exactly the rotted rows.
