from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from magi.events import (
    AgentMessage,
    RunCompleted,
    RunStarted,
    Verdict,
    VoteCast,
    json_schema,
    json_schema_text,
    parse_event,
    utcnow,
)
from magi.paths import DEFAULT_TRACES_DIR, SCHEMA_FILE
from magi.traces import read_trace

EXAMPLES = sorted(DEFAULT_TRACES_DIR.glob("example-*.jsonl"))


def test_committed_schema_matches_models() -> None:
    """schema/magi-events.schema.json (and the TS types generated from it) must
    be regenerated whenever events.py changes: `uv run magi-schema`."""
    assert SCHEMA_FILE.read_text() == json_schema_text()


def test_schema_covers_every_event_type() -> None:
    schema = json_schema()
    mapping = schema["discriminator"]["mapping"]
    assert set(mapping) == {
        "run_started",
        "phase_started",
        "agent_thinking",
        "agent_message",
        "agent_revised_position",
        "vote_cast",
        "verdict",
        "run_error",
        "run_completed",
    }
    # Envelope fields are required on every event.
    for ref in mapping.values():
        definition = schema["$defs"][ref.rsplit("/", 1)[-1]]
        assert {"run_id", "seq", "timestamp", "type"} <= set(definition["required"])


def test_round_trip_through_json() -> None:
    event = VoteCast(
        run_id="r",
        seq=7,
        timestamp=utcnow(),
        agent_id="m",
        vote="DENY",
        confidence=0.4,
        rationale="x",
    )
    parsed = parse_event(event.model_dump_json())
    assert parsed == event
    assert isinstance(parsed, VoteCast)


def test_discriminator_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        parse_event(
            {"type": "agent_dancing", "run_id": "r", "seq": 1, "timestamp": "2026-01-01T00:00:00Z"}
        )


def test_extra_fields_are_rejected() -> None:
    payload = json.loads(
        RunCompleted(
            run_id="r", seq=1, timestamp=utcnow(), status="completed", duration_ms=1
        ).model_dump_json()
    )
    payload["surprise"] = True
    with pytest.raises(ValidationError):
        parse_event(payload)


def test_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        VoteCast(
            run_id="r",
            seq=1,
            timestamp=utcnow(),
            agent_id="m",
            vote="APPROVE",
            confidence=1.2,
            rationale="",
        )


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_traces_are_well_formed(path: Path) -> None:
    events = read_trace(path)
    assert isinstance(events[0], RunStarted)
    assert isinstance(events[-1], RunCompleted)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert {e.run_id for e in events} == {path.stem}
    timestamps = [e.timestamp for e in events]
    assert timestamps == sorted(timestamps)

    messages: dict[str, AgentMessage] = {}
    for event in events:
        if isinstance(event, AgentMessage):
            for ref in event.reply_to:
                assert ref.message_id in messages, f"{event.message_id} replies to unseen {ref}"
                assert messages[ref.message_id].agent_id == ref.agent_id
            messages[event.message_id] = event
    verdict = next(e for e in events if isinstance(e, Verdict))
    for arg in verdict.decisive_arguments:
        assert arg.message_id in messages


def test_there_are_two_examples() -> None:
    assert len(EXAMPLES) == 2
