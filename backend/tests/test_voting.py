from __future__ import annotations

import pytest

from magi.events import Outcome, Tally, VerdictRule, VoteChoice
from magi.voting import Ballot, decide, tally_votes

A, D, X = VoteChoice.APPROVE, VoteChoice.DENY, VoteChoice.ABSTAIN


def ballots(*votes: VoteChoice, confidence: float = 0.8) -> list[Ballot]:
    return [Ballot(f"agent{i}", vote, confidence) for i, vote in enumerate(votes)]


@pytest.mark.parametrize(
    ("votes", "expected"),
    [
        ((A, A, A), Outcome.APPROVED),
        ((A, A, D), Outcome.APPROVED),
        ((A, A, X), Outcome.APPROVED),
        ((D, D, A), Outcome.DENIED),
        ((D, D, D), Outcome.DENIED),
        ((D, X, X), Outcome.DEADLOCK),  # one denial is not a majority of the council
        ((A, D, X), Outcome.DEADLOCK),
        ((A, X, X), Outcome.DEADLOCK),
        ((X, X, X), Outcome.DEADLOCK),
    ],
)
def test_majority_rule(votes: tuple[VoteChoice, ...], expected: Outcome) -> None:
    assert decide(VerdictRule.MAJORITY, ballots(*votes)).outcome is expected


@pytest.mark.parametrize(
    ("votes", "expected"),
    [
        ((A, A, A), Outcome.APPROVED),
        ((A, A, D), Outcome.DENIED),
        ((A, A, X), Outcome.DENIED),  # an abstention blocks unanimity
        ((D, D, D), Outcome.DENIED),
        ((X, X, X), Outcome.DENIED),
    ],
)
def test_unanimous_rule(votes: tuple[VoteChoice, ...], expected: Outcome) -> None:
    assert decide(VerdictRule.UNANIMOUS, ballots(*votes)).outcome is expected


def test_missing_voters_count_against_the_electorate() -> None:
    # Two approvals out of a council of five is not a majority.
    assert decide(VerdictRule.MAJORITY, ballots(A, A), electorate=5).outcome is Outcome.DEADLOCK
    assert decide(VerdictRule.MAJORITY, ballots(A, A, A), electorate=5).outcome is Outcome.APPROVED
    assert decide(VerdictRule.UNANIMOUS, ballots(A, A), electorate=3).outcome is Outcome.DENIED


def test_even_council_tie_is_deadlock() -> None:
    assert decide(VerdictRule.MAJORITY, ballots(A, A, D, D)).outcome is Outcome.DEADLOCK


def test_empty_council() -> None:
    decision = decide(VerdictRule.MAJORITY, [], electorate=0)
    assert decision.outcome is Outcome.DEADLOCK
    assert decision.confidence == 0.0


def test_tally() -> None:
    assert tally_votes(ballots(A, D, X, A)) == Tally(approve=2, deny=1, abstain=1)


def test_confidence_is_mean_of_winning_side() -> None:
    votes = [
        Ballot("m", A, 0.9),
        Ballot("b", D, 0.2),
        Ballot("c", A, 0.6),
    ]
    decision = decide(VerdictRule.MAJORITY, votes)
    assert decision.outcome is Outcome.APPROVED
    assert decision.confidence == pytest.approx(0.75)


def test_confidence_zero_when_no_vote_supports_outcome() -> None:
    # Unanimous rule fails on an abstention: DENIED, but nobody voted DENY.
    decision = decide(VerdictRule.UNANIMOUS, ballots(A, A, X))
    assert decision.outcome is Outcome.DENIED
    assert decision.confidence == 0.0
    assert decide(VerdictRule.MAJORITY, ballots(A, D, X)).confidence == 0.0
