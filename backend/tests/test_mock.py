from __future__ import annotations

import shutil
from itertools import pairwise
from pathlib import Path

import pytest

from magi.emitter import EventEmitter
from magi.events import EventBase, RunCompleted, RunStarted
from magi.mock import MockEngine, choose_trace
from magi.paths import DEFAULT_TRACES_DIR
from magi.runs import StartRunRequest
from magi.traces import TraceNotFoundError, TraceStore, read_trace


@pytest.fixture
def store(traces_dir: Path) -> TraceStore:
    for example in DEFAULT_TRACES_DIR.glob("example-*.jsonl"):
        shutil.copy(example, traces_dir)
    return TraceStore(traces_dir)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Should drones deliver parcels over houses?", "example-delivery-drones"),
        ("Can an AI make triage decisions in the ER?", "example-er-triage"),
    ],
)
def test_choose_trace_by_overlap(store: TraceStore, question: str, expected: str) -> None:
    assert choose_trace(question, store.list()).trace_id == expected


def test_choose_trace_without_overlap_is_deterministic(store: TraceStore) -> None:
    first = choose_trace("Is pineapple pizza good?", store.list())
    assert choose_trace("Is pineapple pizza good?", store.list()) == first


def test_choose_trace_needs_traces() -> None:
    with pytest.raises(TraceNotFoundError):
        choose_trace("anything", [])


async def test_replay_restamps_events_and_keeps_timing(store: TraceStore) -> None:
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    engine = MockEngine(store, speed=2.0, max_gap=5.0, sleep=fake_sleep)
    emitted: list[EventBase] = []
    request = StartRunRequest(question="anything", trace_id="example-er-triage")
    await engine.run(EventEmitter("new-run", [emitted.append]), request)

    original = read_trace(store.path_for("example-er-triage"))
    assert len(emitted) == len(original)
    assert [e.seq for e in emitted] == list(range(1, len(original) + 1))
    assert {e.run_id for e in emitted} == {"new-run"}
    assert [type(e) for e in emitted] == [type(e) for e in original]

    started = emitted[0]
    assert isinstance(started, RunStarted)
    assert started.config.mock is True
    assert isinstance(emitted[-1], RunCompleted)

    # Gaps follow the recording, divided by speed and capped at max_gap.
    gaps = [(b.timestamp - a.timestamp).total_seconds() for a, b in pairwise(original)]
    expected = [min(g, 5.0) / 2.0 for g in gaps if g > 0]
    assert delays == pytest.approx(expected)
    assert max(delays) <= 2.5


def test_resolve_rejects_unknown_trace(store: TraceStore) -> None:
    with pytest.raises(TraceNotFoundError):
        MockEngine(store).resolve(StartRunRequest(question="q?!", trace_id="nope"))
    with pytest.raises(TraceNotFoundError):
        MockEngine(store).resolve(StartRunRequest(question="q?!", trace_id="../secrets"))
