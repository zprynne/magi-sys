"""Vote counting and verdict rules.

* ``majority``  - an outcome needs more than half of the *whole council*
  (2 of 3). Abstentions count toward the electorate, so 1 APPROVE + 2 ABSTAIN
  is a DEADLOCK, not an approval.
* ``unanimous`` - APPROVED only if every member votes APPROVE. Anything else
  is DENIED: without unanimous consent the proposition does not pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from magi.events import Outcome, Tally, VerdictRule, VoteChoice


@dataclass(frozen=True)
class Ballot:
    agent_id: str
    vote: VoteChoice
    confidence: float
    rationale: str = ""


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    tally: Tally
    confidence: float


def tally_votes(ballots: Sequence[Ballot]) -> Tally:
    return Tally(
        approve=sum(b.vote is VoteChoice.APPROVE for b in ballots),
        deny=sum(b.vote is VoteChoice.DENY for b in ballots),
        abstain=sum(b.vote is VoteChoice.ABSTAIN for b in ballots),
    )


def decide(rule: VerdictRule, ballots: Sequence[Ballot], electorate: int | None = None) -> Decision:
    """Apply ``rule`` to the ballots. ``electorate`` is the council size; members
    who did not vote are treated as abstaining."""
    size = max(electorate if electorate is not None else len(ballots), len(ballots))
    if size == 0:
        return Decision(Outcome.DEADLOCK, Tally(), 0.0)
    tally = tally_votes(ballots)

    if rule is VerdictRule.MAJORITY:
        if tally.approve * 2 > size:
            outcome = Outcome.APPROVED
        elif tally.deny * 2 > size:
            outcome = Outcome.DENIED
        else:
            outcome = Outcome.DEADLOCK
    elif rule is VerdictRule.UNANIMOUS:
        outcome = Outcome.APPROVED if tally.approve == size else Outcome.DENIED
    else:  # pragma: no cover - exhaustive over VerdictRule
        raise ValueError(f"unknown verdict rule: {rule}")

    return Decision(outcome, tally, _side_confidence(outcome, ballots))


def _side_confidence(outcome: Outcome, ballots: Sequence[Ballot]) -> float:
    """Mean confidence of the ballots that agree with the outcome (0 if none)."""
    side = {Outcome.APPROVED: VoteChoice.APPROVE, Outcome.DENIED: VoteChoice.DENY}.get(outcome)
    supporting = [b.confidence for b in ballots if b.vote is side]
    if not supporting:
        return 0.0
    return round(sum(supporting) / len(supporting), 3)
