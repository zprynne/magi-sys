"""Graph logic, exercised end to end with scripted (mocked) chat models."""

from __future__ import annotations

import asyncio

import pytest

from magi.events import (
    AgentMessage,
    AgentRevisedPosition,
    AgentThinking,
    EventBase,
    Outcome,
    Phase,
    PhaseStarted,
    ReplyRef,
    RunError,
    Stance,
    Verdict,
    VerdictRule,
    VoteCast,
    VoteChoice,
)
from magi.graph import run_deliberation
from tests.conftest import ContextFactory
from tests.fakes import BALTHASAR, CASPAR, MELCHIOR, opening, rebuttal


def of[E: EventBase](events: list[EventBase], cls: type[E]) -> list[E]:
    return [e for e in events if isinstance(e, cls)]


def phases(events: list[EventBase]) -> list[tuple[Phase, int | None]]:
    return [(e.phase, e.round) for e in of(events, PhaseStarted)]


async def test_full_deliberation_event_sequence(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context()
    await run_deliberation("Should we?", ctx)

    assert phases(events) == [
        (Phase.OPENING, 0),
        (Phase.DEBATE, 1),
        (Phase.DEBATE, 2),
        (Phase.VOTE, None),
        (Phase.VERDICT, None),
    ]
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert {e.run_id for e in events} == {"test-run"}

    messages = of(events, AgentMessage)
    assert [m.message_id for m in messages if m.round == 0] == [
        "melchior-r0",
        "balthasar-r0",
        "caspar-r0",
    ]
    assert len(messages) == 9  # 3 agents x (opening + 2 rounds)
    assert len(of(events, VoteCast)) == 3

    verdict = of(events, Verdict)[0]
    assert events[-1] is verdict
    assert verdict.outcome is Outcome.APPROVED
    assert verdict.tally.approve == 2
    assert verdict.tally.deny == 1
    assert verdict.confidence == pytest.approx(0.75)


async def test_each_agent_thinks_before_it_speaks(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context()
    await run_deliberation("Should we?", ctx)

    for message in of(events, AgentMessage):
        thinking = [
            e
            for e in of(events, AgentThinking)
            if e.agent_id == message.agent_id and e.round == message.round
        ]
        assert len(thinking) == 1
        assert thinking[0].seq < message.seq


async def test_agents_in_a_phase_run_in_parallel(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context(delay=0.05)
    loop = asyncio.get_running_loop()
    started = loop.time()
    await run_deliberation("Should we?", ctx)
    elapsed = loop.time() - started

    # 3 agents x 4 agent phases + synthesis = 13 sequential calls (0.65s); in
    # parallel the agent phases take one delay each (5 x 0.05s).
    assert elapsed < 0.45
    # All three openings start thinking before any opening message arrives.
    first_message = of(events, AgentMessage)[0].seq
    opening_thoughts = [e for e in of(events, AgentThinking) if e.phase is Phase.OPENING]
    assert all(t.seq < first_message for t in opening_thoughts)


async def test_reply_to_resolves_names_to_latest_messages(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context()
    await run_deliberation("Should we?", ctx)
    by_id = {m.message_id: m for m in of(events, AgentMessage)}

    # BALTHASAR-2 answered "Melchior" and "caspar" (free-text refs) in round 1.
    assert by_id["balthasar-r1"].reply_to == [
        ReplyRef(agent_id="melchior", message_id="melchior-r0"),
        ReplyRef(agent_id="caspar", message_id="caspar-r0"),
    ]
    # Round 2 replies point at round 1 messages.
    assert by_id["melchior-r2"].reply_to == [ReplyRef(agent_id="caspar", message_id="caspar-r1")]
    # Opening statements answer nobody.
    assert all(not m.reply_to for m in by_id.values() if m.round == 0)


async def test_unknown_and_self_references_are_dropped(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context(
        overrides={(MELCHIOR, "debate1"): rebuttal("APPROVE", "MELCHIOR-1", "GENDO", BALTHASAR)}
    )
    await run_deliberation("Should we?", ctx)
    melchior_r1 = next(m for m in of(events, AgentMessage) if m.message_id == "melchior-r1")
    assert [r.agent_id for r in melchior_r1.reply_to] == ["balthasar"]


async def test_debate_sees_other_agents_latest_arguments(make_context: ContextFactory) -> None:
    ctx, _, model = make_context()
    await run_deliberation("Should we?", ctx)

    round_two = [p for p in model.prompts if "DEBATE ROUND 2" in p]
    assert len(round_two) == 3
    for prompt in round_two:
        assert "-r1]" in prompt  # sees round-1 arguments...
        assert "-r0]" not in prompt  # ...not stale openings


async def test_stance_change_emits_revision(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context()
    await run_deliberation("Should we?", ctx)

    revisions = of(events, AgentRevisedPosition)
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision.agent_id == "caspar"
    assert revision.round == 1
    assert revision.previous_stance is Stance.UNDECIDED
    assert revision.new_stance is Stance.APPROVE
    assert revision.reason == "Opt-in solves it."
    message = next(m for m in of(events, AgentMessage) if m.message_id == revision.message_id)
    assert message.seq < revision.seq


async def test_explicit_revision_without_stance_change(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context(
        overrides={(BALTHASAR, "debate2"): rebuttal("DENY", CASPAR, revised=True, reason="Nuance")}
    )
    await run_deliberation("Should we?", ctx)
    revision = next(r for r in of(events, AgentRevisedPosition) if r.agent_id == "balthasar")
    assert revision.previous_stance is revision.new_stance is Stance.DENY
    assert revision.reason == "Nuance"


async def test_early_consensus_skips_remaining_rounds(make_context: ContextFactory) -> None:
    agree = {
        (who, "debate1"): rebuttal("DENY", other)
        for who, other in ((MELCHIOR, BALTHASAR), (BALTHASAR, CASPAR), (CASPAR, MELCHIOR))
    }
    ctx, events, model = make_context(
        max_rounds=3,
        overrides={
            (MELCHIOR, "opening"): opening("DENY"),
            (CASPAR, "opening"): opening("DENY"),
            **agree,
        },
    )
    await run_deliberation("Should we?", ctx)
    assert phases(events)[:3] == [(Phase.OPENING, 0), (Phase.DEBATE, 1), (Phase.VOTE, None)]
    assert not any(phase == "debate2" for _, phase in model.calls)


async def test_no_early_exit_when_disabled(make_context: ContextFactory) -> None:
    agree = {
        (who, f"debate{r}"): rebuttal("DENY")
        for who in (MELCHIOR, BALTHASAR, CASPAR)
        for r in (1, 2)
    }
    ctx, events, _ = make_context(
        early_consensus=False,
        overrides={
            (MELCHIOR, "opening"): opening("DENY"),
            (CASPAR, "opening"): opening("DENY"),
            **agree,
        },
    )
    await run_deliberation("Should we?", ctx)
    assert (Phase.DEBATE, 2) in phases(events)


async def test_consensus_in_the_opening_still_debates_once(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context(
        overrides={
            (MELCHIOR, "opening"): opening("DENY"),
            (CASPAR, "opening"): opening("DENY"),
        }
    )
    await run_deliberation("Should we?", ctx)
    assert (Phase.DEBATE, 1) in phases(events)


async def test_zero_rounds_goes_straight_to_vote(make_context: ContextFactory) -> None:
    ctx, events, model = make_context(max_rounds=0)
    await run_deliberation("Should we?", ctx)
    assert phases(events) == [(Phase.OPENING, 0), (Phase.VOTE, None), (Phase.VERDICT, None)]
    assert not any(phase.startswith("debate") for _, phase in model.calls)


async def test_unanimous_rule_denies_split_vote(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context(rule=VerdictRule.UNANIMOUS)
    await run_deliberation("Should we?", ctx)
    verdict = of(events, Verdict)[0]
    assert verdict.rule is VerdictRule.UNANIMOUS
    assert verdict.outcome is Outcome.DENIED


async def test_synthesis_citations_are_validated(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context()
    await run_deliberation("Should we?", ctx)
    verdict = of(events, Verdict)[0]
    # "[caspar-r1]" is normalised; "bogus-r9" does not exist and is dropped.
    assert [(d.agent_id, d.message_id) for d in verdict.decisive_arguments] == [
        ("caspar", "caspar-r1")
    ]


async def test_unparseable_agent_degrades_without_failing_run(make_context: ContextFactory) -> None:
    ctx, events, model = make_context(
        overrides={(BALTHASAR, "vote"): ["not json", "still not json"]}
    )
    await run_deliberation("Should we?", ctx)

    assert model.calls.count((BALTHASAR, "vote")) == 2  # one repair attempt
    errors = of(events, RunError)
    assert len(errors) == 1
    assert errors[0].agent_id == "balthasar"
    assert errors[0].fatal is False
    vote = next(v for v in of(events, VoteCast) if v.agent_id == "balthasar")
    assert vote.vote is VoteChoice.ABSTAIN
    assert vote.confidence == 0.0
    # Two approvals of three is still a majority.
    assert of(events, Verdict)[0].outcome is Outcome.APPROVED


async def test_repair_retry_recovers(make_context: ContextFactory) -> None:
    ctx, events, model = make_context(
        overrides={(MELCHIOR, "opening"): ["Sure! Here's my view.", opening("APPROVE")]}
    )
    await run_deliberation("Should we?", ctx)
    assert model.calls.count((MELCHIOR, "opening")) == 2
    assert not of(events, RunError)


async def test_refusal_in_opening_holds_undecided(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context(overrides={(CASPAR, "opening"): "<refusal>"})
    await run_deliberation("Should we?", ctx)
    caspar_r0 = next(m for m in of(events, AgentMessage) if m.message_id == "caspar-r0")
    assert caspar_r0.stance is Stance.UNDECIDED
    assert of(events, RunError)[0].agent_id == "caspar"


async def test_failed_debate_turn_keeps_previous_position(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context(overrides={(BALTHASAR, "debate1"): "<refusal>"})
    await run_deliberation("Should we?", ctx)
    by_id = {m.message_id: m for m in of(events, AgentMessage)}
    assert by_id["balthasar-r1"].stance is by_id["balthasar-r0"].stance
    assert by_id["balthasar-r1"].summary == by_id["balthasar-r0"].summary
    assert not [r for r in of(events, AgentRevisedPosition) if r.agent_id == "balthasar"]


async def test_synthesis_failure_falls_back_to_rationales(make_context: ContextFactory) -> None:
    ctx, events, _ = make_context(overrides={("ARBITER", "synthesis"): "<refusal>"})
    await run_deliberation("Should we?", ctx)
    verdict = of(events, Verdict)[0]
    assert verdict.outcome is Outcome.APPROVED
    assert "APPROVED" in verdict.summary
    assert [d.agent_id for d in verdict.decisive_arguments] == ["melchior", "balthasar", "caspar"]
    assert of(events, RunError)[0].agent_id is None


async def test_unexpected_errors_propagate(make_context: ContextFactory) -> None:
    ctx, _, _ = make_context(overrides={(MELCHIOR, "vote"): RuntimeError("API down")})
    with pytest.raises(RuntimeError, match="API down"):
        await run_deliberation("Should we?", ctx)


async def test_votes_are_case_insensitive_and_percentages_normalised(
    make_context: ContextFactory,
) -> None:
    ctx, events, _ = make_context(
        overrides={(CASPAR, "vote"): {"vote": "approve", "confidence": 85, "rationale": "Yes."}}
    )
    await run_deliberation("Should we?", ctx)
    vote = next(v for v in of(events, VoteCast) if v.agent_id == "caspar")
    assert vote.vote is VoteChoice.APPROVE
    assert vote.confidence == pytest.approx(0.85)
