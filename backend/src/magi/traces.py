"""JSONL trace persistence: one file per run in the traces directory, one event
per line, in sequence order."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import IO

from pydantic import BaseModel, ValidationError

from magi.events import (
    EventBase,
    MagiEvent,
    Outcome,
    RunCompleted,
    RunStarted,
    RunStatus,
    Verdict,
    VerdictRule,
    dump_event,
    parse_event,
)

log = logging.getLogger(__name__)

_TRACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EXAMPLE_PREFIX = "example-"


class TraceNotFoundError(LookupError):
    pass


class TraceSummary(BaseModel):
    trace_id: str
    question: str
    started_at: datetime
    verdict_rule: VerdictRule
    outcome: Outcome | None
    status: RunStatus | None
    event_count: int
    example: bool


class TraceWriter:
    """Event sink that appends each event to a JSONL file as it happens."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: IO[str] | None = None

    def __call__(self, event: EventBase) -> None:
        if self._file is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("a", encoding="utf-8", newline="\n")
        self._file.write(dump_event(event) + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


class TraceStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path_for(self, trace_id: str) -> Path:
        if not _TRACE_ID.match(trace_id):
            raise TraceNotFoundError(trace_id)
        return self.directory / f"{trace_id}.jsonl"

    def writer(self, run_id: str) -> TraceWriter:
        return TraceWriter(self.path_for(run_id))

    def load(self, trace_id: str) -> list[MagiEvent]:
        path = self.path_for(trace_id)
        if not path.is_file():
            raise TraceNotFoundError(trace_id)
        return read_trace(path)

    def list(self) -> list[TraceSummary]:
        summaries: list[TraceSummary] = []
        if not self.directory.is_dir():
            return summaries
        for path in self.directory.glob("*.jsonl"):
            try:
                summary = summarize(path.stem, read_trace(path))
            except (ValidationError, ValueError) as exc:
                log.warning("skipping unreadable trace %s: %s", path.name, exc)
                continue
            if summary is not None:
                summaries.append(summary)
        # Recorded runs first (newest first), bundled examples last.
        summaries.sort(key=lambda s: (s.example, -s.started_at.timestamp()))
        return summaries


def read_trace(path: Path) -> list[MagiEvent]:
    with path.open(encoding="utf-8") as handle:
        return [parse_event(line) for line in handle if line.strip()]


def summarize(trace_id: str, events: list[MagiEvent]) -> TraceSummary | None:
    started = next((e for e in events if isinstance(e, RunStarted)), None)
    if started is None:
        return None
    verdict = next((e for e in events if isinstance(e, Verdict)), None)
    completed = next((e for e in events if isinstance(e, RunCompleted)), None)
    return TraceSummary(
        trace_id=trace_id,
        question=started.question,
        started_at=started.timestamp,
        verdict_rule=started.config.verdict_rule,
        outcome=verdict.outcome if verdict else None,
        status=completed.status if completed else None,
        event_count=len(events),
        example=trace_id.startswith(EXAMPLE_PREFIX),
    )
