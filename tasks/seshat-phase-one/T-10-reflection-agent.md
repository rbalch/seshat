---
id: T-10
plan: seshat-phase-one
title: Reflection agent and candidate rules
status: todo
depends_on: [T-03]
files:
  - src/seshat/agents/reflection.py
  - src/seshat/candidates.py
  - tests/agents/test_reflection.py
rules: []
---

## Goal

After a scan, confirmed claims are rolled into `Concept` rows with evidence links,
and structural patterns that hold across three or more units with no exception get
`candidate_rule=1` and a sightings count. Seshat flags; it never writes a rule.

## Scope

1. `ConceptDraft` pydantic: `title`, `body` (prose that references claims by id in
   square brackets), `evidence: list[str]` (claim ids). `PatternDraft`:
   `description`, `claim_ids: list[str]`, `exceptions: list[str]` (free text; empty
   means none found). `ReflectionOutput(concepts, patterns)`.
2. `ReflectionAgent(nooa.Agent)`, `PredictStrategy`, generation method
   `reflect(self, claims: list[Claim]) -> ReflectionOutput: ...` with a docstring
   prompt: group related confirmed claims into concepts, cite only the ids given,
   report structural patterns that recur, name exceptions honestly.
3. `run_reflection(agent, ledger, run_id, batch_size=40) -> ReflectionSummary`:
   pages `ledger.confirmed_claims`, calls `reflect` per batch, and for each concept
   drops any evidence id that is not in the batch and not `confirmed`, then
   `ledger.add_concept`. A concept left with no evidence is discarded and counted.
4. `src/seshat/candidates.py`, `flag_candidates(ledger, patterns, run_id) -> int`:
   for each pattern, sightings = number of distinct `unit_id`s among its cited
   claims that are `confirmed`; if sightings ≥ 3 and `exceptions` is empty, set
   `candidate_rule=1, rule_sightings=sightings` on those claims; otherwise leave
   them untouched. Returns the number of claims flagged.
5. `after_scan` adapter `reflect_after_scan(settings)` returning a callable with
   T-09's `after_scan(ledger, run)` signature.

## Non-scope

- No governance decision, control, or ADR is written (plan §1, `AGENTS.md` Never).
- No NOOA memory reflection here; that stays on inside the working pool by NOOA.
- No CLI.

## Acceptance

- `uv run pytest tests/agents/test_reflection.py -q` → exit 0, hermetic with
  `FakeLLMClient`, on a ledger pre-filled with confirmed, refuted and conjectured
  claims across four units, covers:
  - a scripted `ReflectionOutput` with one concept citing two confirmed claims →
    one concept row and two `concept_evidence` rows;
  - a concept citing a refuted claim id → that id is dropped and the concept is
    still written with the remaining evidence;
  - a concept whose evidence is all invalid → not written, counted in the summary;
  - a pattern citing confirmed claims on three units with no exceptions → those
    claims get `candidate_rule=1`, `rule_sightings=3`;
  - the same pattern on two units → nothing flagged;
  - three units but one exception string → nothing flagged;
  - `batch_size=2` over five claims → `fake.call_count == 3`.
- `make check` → exit 0

## Context

- plan §2 (reflection row), §3 promotion rule, §5 steps 8–9, §11 "Hallucinated
  rules". Decisions Q5, Q16, Q25. Memory note in `MEMORY.md`: the rule of three is
  a heuristic for humans; here it is only a threshold on a flag.
- Ledger API: `confirmed_claims`, `add_concept` (raises `EvidenceNotConfirmed`),
  and the claim columns `candidate_rule`, `rule_sightings` (T-03). Add a
  `set_candidate(claim_id, sightings)` method to the store if T-03 did not.

## Manual QA

None until the dogfood run.
