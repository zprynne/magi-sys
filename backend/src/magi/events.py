"""MAGI event schema.

This module is the single source of truth for every event the backend emits,
streams to the browser over SSE, and persists as JSONL traces. The JSON Schema
in ``schema/magi-events.schema.json`` and the TypeScript types in
``frontend/src/types/events.generated.ts`` are generated from these models
(``uv run magi-schema`` then ``npm run gen:types``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

SCHEMA_VERSION = "1.0"


class Phase(StrEnum):
    OPENING = "opening"
    DEBATE = "debate"
    VOTE = "vote"
    VERDICT = "verdict"


class Stance(StrEnum):
    """An agent's current leaning on the proposition (pre-vote)."""

    APPROVE = "APPROVE"
    DENY = "DENY"
    UNDECIDED = "UNDECIDED"


class VoteChoice(StrEnum):
    APPROVE = "APPROVE"
    DENY = "DENY"
    ABSTAIN = "ABSTAIN"


class VerdictRule(StrEnum):
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"


class Outcome(StrEnum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    DEADLOCK = "DEADLOCK"


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        # Fields with defaults are always present on the wire, so mark them required
        # in the (serialization-mode) JSON Schema and therefore in TypeScript.
        json_schema_serialization_defaults_required=True,
    )


# --------------------------------------------------------------------------- #
# Payload building blocks
# --------------------------------------------------------------------------- #


class AgentInfo(_Model):
    id: str = Field(description="Stable lowercase id, e.g. 'melchior'.")
    name: str = Field(description="Display name, e.g. 'MELCHIOR-1'.")
    title: str = Field(description="Persona title, e.g. 'The Scientist'.")
    color: str = Field(description="CSS color used for this agent in the UI.")
    priorities: list[str] = Field(default_factory=list)


class RunConfig(_Model):
    max_rounds: int = Field(ge=0)
    verdict_rule: VerdictRule
    model: str
    mock: bool = False
    early_consensus: bool = True


class ReplyRef(_Model):
    agent_id: str
    message_id: str


class Tally(_Model):
    approve: int = 0
    deny: int = 0
    abstain: int = 0


class DecisiveArgument(_Model):
    agent_id: str
    message_id: str | None = None
    reason: str


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #


class EventBase(_Model):
    run_id: str
    seq: int = Field(ge=1, description="1-based, strictly increasing within a run.")
    timestamp: datetime


class RunStarted(EventBase):
    type: Literal["run_started"] = "run_started"
    schema_version: str = SCHEMA_VERSION
    question: str
    agents: list[AgentInfo]
    config: RunConfig


class PhaseStarted(EventBase):
    type: Literal["phase_started"] = "phase_started"
    phase: Phase
    round: int | None = Field(
        default=None, description="0 for opening, 1..N for debate rounds, null otherwise."
    )


class AgentThinking(EventBase):
    type: Literal["agent_thinking"] = "agent_thinking"
    agent_id: str
    phase: Phase
    round: int | None = None


class AgentMessage(EventBase):
    type: Literal["agent_message"] = "agent_message"
    agent_id: str
    message_id: str
    phase: Phase
    round: int
    content: str
    stance: Stance
    summary: str = Field(description="One-sentence statement of the agent's current position.")
    reply_to: list[ReplyRef] = Field(default_factory=list)


class AgentRevisedPosition(EventBase):
    type: Literal["agent_revised_position"] = "agent_revised_position"
    agent_id: str
    message_id: str
    round: int
    previous_stance: Stance
    new_stance: Stance
    previous_summary: str
    new_summary: str
    reason: str


class VoteCast(EventBase):
    type: Literal["vote_cast"] = "vote_cast"
    agent_id: str
    vote: VoteChoice
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class Verdict(EventBase):
    type: Literal["verdict"] = "verdict"
    rule: VerdictRule
    outcome: Outcome
    tally: Tally
    confidence: float = Field(
        ge=0.0, le=1.0, description="Mean confidence of the agents on the winning side."
    )
    summary: str
    decisive_arguments: list[DecisiveArgument] = Field(default_factory=list)


class RunError(EventBase):
    type: Literal["run_error"] = "run_error"
    message: str
    agent_id: str | None = None
    fatal: bool = False


class RunCompleted(EventBase):
    type: Literal["run_completed"] = "run_completed"
    status: RunStatus
    duration_ms: int = Field(ge=0)


MagiEvent = Annotated[
    RunStarted
    | PhaseStarted
    | AgentThinking
    | AgentMessage
    | AgentRevisedPosition
    | VoteCast
    | Verdict
    | RunError
    | RunCompleted,
    Field(discriminator="type"),
]

EVENT_ADAPTER: TypeAdapter[MagiEvent] = TypeAdapter(MagiEvent)

EVENT_TYPES: dict[str, type[EventBase]] = {
    cls.model_fields["type"].default: cls
    for cls in (
        RunStarted,
        PhaseStarted,
        AgentThinking,
        AgentMessage,
        AgentRevisedPosition,
        VoteCast,
        Verdict,
        RunError,
        RunCompleted,
    )
}

TERMINAL_EVENT_TYPES = frozenset({"run_completed"})


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_event(data: str | bytes | dict[str, Any]) -> MagiEvent:
    if isinstance(data, dict):
        return EVENT_ADAPTER.validate_python(data)
    return EVENT_ADAPTER.validate_json(data)


def dump_event(event: EventBase) -> str:
    return event.model_dump_json()


def json_schema() -> dict[str, Any]:
    """JSON Schema for the event union, in serialization mode so that fields with
    defaults are still marked required (they are always present on the wire)."""
    schema = EVENT_ADAPTER.json_schema(mode="serialization")
    # Property-level titles make json-schema-to-typescript emit one alias per field
    # (RunId1, Seq3, ...). Keep titles only on named definitions.
    for definition in schema.get("$defs", {}).values():
        for prop in definition.get("properties", {}).values():
            prop.pop("title", None)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://magi.local/schema/magi-events.schema.json",
        "title": "MagiEvent",
        "description": "Any event emitted by a MAGI deliberation run.",
        **schema,
    }


def json_schema_text() -> str:
    return json.dumps(json_schema(), indent=2, sort_keys=True) + "\n"
