"""Mock mode (``MAGI_MOCK=1``): replay a saved trace as a new live run.

Events are re-stamped with the new run id, fresh sequence numbers and current
timestamps, and are released with the same gaps as in the recording (divided
by ``MAGI_MOCK_SPEED``), so the UI behaves exactly as it would against the
real model, without any API calls.
"""

from __future__ import annotations

import asyncio
import re
import zlib
from collections.abc import Awaitable, Callable
from typing import Any

from magi.emitter import EventEmitter
from magi.events import RunCompleted, RunStarted, RunStatus
from magi.runs import StartRunRequest
from magi.traces import TraceNotFoundError, TraceStore, TraceSummary

_WORD = re.compile(r"[a-z]{4,}")

Sleep = Callable[[float], Awaitable[Any]]


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def choose_trace(question: str, candidates: list[TraceSummary]) -> TraceSummary:
    """Pick the trace whose question best overlaps ``question``. With no overlap,
    pick deterministically by hash so different questions show different traces."""
    if not candidates:
        raise TraceNotFoundError("no traces available to replay")
    asked = _words(question)

    def score(summary: TraceSummary) -> float:
        theirs = _words(summary.question)
        union = asked | theirs
        return len(asked & theirs) / len(union) if union else 0.0

    best = max(candidates, key=score)
    if score(best) > 0:
        return best
    return candidates[zlib.crc32(question.encode()) % len(candidates)]


class MockEngine:
    def __init__(
        self,
        store: TraceStore,
        speed: float = 1.0,
        max_gap: float = 15.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.store = store
        self.speed = speed
        self.max_gap = max_gap
        self._sleep = sleep

    def resolve(self, request: StartRunRequest) -> str:
        """The trace id this request will replay (raises TraceNotFoundError)."""
        if request.trace_id:
            if not self.store.path_for(request.trace_id).is_file():
                raise TraceNotFoundError(request.trace_id)
            return request.trace_id
        return choose_trace(request.question, self.store.list()).trace_id

    async def run(self, emitter: EventEmitter, request: StartRunRequest) -> None:
        events = self.store.load(self.resolve(request))
        previous = None
        for event in events:
            if previous is not None:
                gap = (event.timestamp - previous).total_seconds()
                delay = min(max(gap, 0.0), self.max_gap) / self.speed
                if delay > 0:
                    await self._sleep(delay)
            previous = event.timestamp

            overrides: dict[str, Any] = {}
            if isinstance(event, RunStarted):
                overrides["config"] = event.config.model_copy(update={"mock": True})
            emitter.republish(event, **overrides)

        if not any(isinstance(e, RunCompleted) for e in events):
            emitter.emit(RunCompleted, status=RunStatus.COMPLETED, duration_ms=0)
