"""Candidate-rule flagging: T-10 scope item 4.

Seshat flags a structural pattern that recurs with no exception as a
candidate rule; it never writes a governance decision itself — see
AGENTS.md "Never: emit a governance rule". `flag_candidates` only ever sets
`candidate_rule=1` and a `rule_sightings` count on the claims a qualifying
pattern cites. A human, and the rule-of-three convention it encodes,
decides what (if anything) becomes an actual decision from there; this
module never gets a vote in that.
"""

from __future__ import annotations

from seshat.agents.reflection import PatternDraft
from seshat.ledger.store import Ledger

# The rule of three is a heuristic for humans (see MEMORY.md); here it is
# only a threshold on a flag, never anything closer to a decision.
_SIGHTING_THRESHOLD = 3


def flag_candidates(ledger: Ledger, patterns: list[PatternDraft], run_id: str) -> int:
    """Flag each pattern's confirmed claims as a candidate rule if it qualifies.

    `sightings` is the number of distinct `unit_id`s among a pattern's
    `claim_ids` that are, right now, `confirmed` — a pattern may cite ids
    that do not exist or are not confirmed; those are simply not counted,
    never treated as an error. A pattern flags its confirmed claims only
    when `sightings >= 3` and it reports no exceptions; everything else is
    left untouched. `run_id` is accepted for symmetry with the rest of a
    reflection pass's writes; the `candidate_rule`/`rule_sightings` columns
    carry no run reference in the schema, so it is not itself persisted
    here.

    Returns the total number of claims flagged across every pattern.
    """
    flagged = 0
    for pattern in patterns:
        claims = ledger.claims_by_ids(pattern.claim_ids)
        confirmed = [claim for claim in claims if claim.status == 'confirmed']
        sightings = len({claim.unit_id for claim in confirmed})

        if sightings < _SIGHTING_THRESHOLD or pattern.exceptions:
            continue

        for claim in confirmed:
            ledger.set_candidate(claim.id, sightings)
            flagged += 1

    return flagged
