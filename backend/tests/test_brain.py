from __future__ import annotations

import pytest
from pydantic import ValidationError

from magi.brain import (
    AgentOutputError,
    CouncilBrain,
    DebateOutput,
    OpeningOutput,
    VoteOutput,
    extract_json_object,
    parse_reply,
)
from magi.events import Stance, VoteChoice
from magi.personas import Persona
from tests.fakes import MELCHIOR, ScriptedChatModel, opening


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        'Here you go:\n```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        'Preamble {"a": 1} trailing words',
    ],
)
def test_extract_json_object(text: str) -> None:
    assert extract_json_object(text) == {"a": 1}


@pytest.mark.parametrize("text", ["", "no json here", "[1, 2]", '{"a": '])
def test_extract_json_object_rejects(text: str) -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        extract_json_object(text)


def test_stances_and_votes_are_normalised() -> None:
    out = parse_reply('{"stance": " deny ", "summary": "s", "argument": "a"}', OpeningOutput)
    assert out.stance is Stance.DENY
    vote = parse_reply('{"vote": "abstain", "confidence": 40, "rationale": "r"}', VoteOutput)
    assert vote.vote is VoteChoice.ABSTAIN
    assert vote.confidence == pytest.approx(0.4)


def test_debate_defaults() -> None:
    out = parse_reply('{"argument": "a", "stance": "APPROVE", "summary": "s"}', DebateOutput)
    assert out.responding_to == []
    assert out.revised is False


@pytest.mark.parametrize(
    "payload",
    [
        '{"vote": "MAYBE", "confidence": 0.5, "rationale": "r"}',
        '{"vote": "APPROVE", "confidence": 150, "rationale": "r"}',
        '{"vote": "APPROVE", "confidence": 0.5, "rationale": ""}',
    ],
)
def test_invalid_votes(payload: str) -> None:
    with pytest.raises(ValidationError):
        parse_reply(payload, VoteOutput)


async def test_repair_prompt_includes_the_error(council: list[Persona]) -> None:
    model = ScriptedChatModel(
        script={(MELCHIOR, "opening"): ['{"stance": "PERHAPS"}', opening("DENY")]}
    )
    out = await CouncilBrain(model, council).opening(council[0], "Q?")
    assert out.stance is Stance.DENY
    assert "could not be used" in model.prompts[1]
    assert "stance" in model.prompts[1]


async def test_gives_up_after_max_attempts(council: list[Persona]) -> None:
    model = ScriptedChatModel(script={(MELCHIOR, "opening"): "nope"})
    with pytest.raises(AgentOutputError, match="OpeningOutput"):
        await CouncilBrain(model, council, max_attempts=3).opening(council[0], "Q?")
    assert len(model.calls) == 3


async def test_refusal_is_not_retried(council: list[Persona]) -> None:
    model = ScriptedChatModel(script={(MELCHIOR, "opening"): "<refusal>"})
    with pytest.raises(AgentOutputError, match="declined"):
        await CouncilBrain(model, council).opening(council[0], "Q?")
    assert len(model.calls) == 1


async def test_system_prompt_names_the_whole_council(council: list[Persona]) -> None:
    brain = CouncilBrain(ScriptedChatModel(script={}), council)
    system = brain._system(council[1])
    assert system.startswith(council[1].system_prompt.strip())
    for persona in council:
        assert persona.name in system
