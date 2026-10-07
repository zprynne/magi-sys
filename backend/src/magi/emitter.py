"""Stamps events with the run envelope (run_id, seq, timestamp) and fans them
out to sinks (the live SSE channel, the JSONL trace writer, test collectors)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from magi.events import EventBase, utcnow

EventSink = Callable[[EventBase], None]


class EventEmitter:
    def __init__(
        self,
        run_id: str,
        sinks: Sequence[EventSink] = (),
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.run_id = run_id
        self._sinks = list(sinks)
        self._clock = clock
        self._seq = 0

    @property
    def last_seq(self) -> int:
        return self._seq

    def add_sink(self, sink: EventSink) -> None:
        self._sinks.append(sink)

    def emit[E: EventBase](self, cls: type[E], **fields: Any) -> E:
        """Build an event of type ``cls`` from payload ``fields`` and publish it."""
        self._seq += 1
        event = cls(run_id=self.run_id, seq=self._seq, timestamp=self._clock(), **fields)
        self._publish(event)
        return event

    def republish[E: EventBase](self, event: E, **overrides: Any) -> E:
        """Re-stamp an existing event (e.g. from a replayed trace) into this run."""
        self._seq += 1
        update = {"run_id": self.run_id, "seq": self._seq, "timestamp": self._clock(), **overrides}
        restamped = event.model_copy(update=update)
        self._publish(restamped)
        return restamped

    def _publish(self, event: EventBase) -> None:
        for sink in self._sinks:
            sink(event)
