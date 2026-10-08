"""Run lifecycle: start deliberations in the background, buffer their events
and let any number of SSE clients follow along (and resume) by sequence."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field, field_validator

from magi.brain import CouncilBrain
from magi.emitter import EventEmitter
from magi.events import (
    TERMINAL_EVENT_TYPES,
    EventBase,
    RunCompleted,
    RunConfig,
    RunError,
    RunStarted,
    RunStatus,
    VerdictRule,
)
from magi.graph import DeliberationContext, run_deliberation
from magi.models import ModelSpec, Roster, resolve_roster
from magi.personas import Persona
from magi.settings import Settings
from magi.traces import TraceStore, TraceWriter

log = logging.getLogger(__name__)


class StartRunRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    max_rounds: int | None = Field(default=None, ge=0, le=6)
    verdict_rule: VerdictRule | None = None
    trace_id: str | None = Field(default=None, description="Mock mode: which trace to replay.")

    @field_validator("question", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"


class RunChannel:
    """Append-only event buffer for one run with async fan-out to subscribers."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[EventBase] = []
        self.done = False
        self._changed = asyncio.Event()

    def publish(self, event: EventBase) -> None:
        self.events.append(event)
        if getattr(event, "type", None) in TERMINAL_EVENT_TYPES:
            self.done = True
        self._changed.set()
        self._changed = asyncio.Event()

    async def stream(
        self, after_seq: int = 0, heartbeat: float = 15.0
    ) -> AsyncIterator[EventBase | None]:
        """Yield events with ``seq > after_seq`` until the run finishes. Yields
        ``None`` after ``heartbeat`` seconds of silence so callers can keep the
        connection alive."""
        index = max(after_seq, 0)  # seq is 1-based, so seq N lives at index N-1
        while True:
            while index < len(self.events):
                yield self.events[index]
                index += 1
            if self.done:
                return
            changed = self._changed
            try:
                await asyncio.wait_for(changed.wait(), timeout=heartbeat)
            except TimeoutError:
                yield None


class Engine(Protocol):
    """Produces the events for one run through ``emitter``. Must emit
    ``run_started`` first and ``run_completed`` last."""

    async def run(self, emitter: EventEmitter, request: StartRunRequest) -> None: ...


ModelFactory = Callable[[ModelSpec, Settings], BaseChatModel]


class LiveEngine:
    """Runs the LangGraph deliberation, each agent on the model its roster assigns."""

    def __init__(
        self,
        settings: Settings,
        council: Sequence[Persona],
        model_factory: ModelFactory,
        roster: Roster | None = None,
    ) -> None:
        self.settings = settings
        self.council = list(council)
        self.roster = roster or resolve_roster(settings, council)
        self._model_factory = model_factory
        self._models: dict[str, BaseChatModel] = {}

    def _model(self, spec: ModelSpec) -> BaseChatModel:
        # One client per distinct spec: agents sharing a server share a client.
        if spec.key not in self._models:
            self._models[spec.key] = self._model_factory(spec, self.settings)
        return self._models[spec.key]

    def _brain(self) -> CouncilBrain:
        agent_models = {pid: self._model(spec) for pid, spec in self.roster.agents.items()}
        arbiter = self._model(self.roster.arbiter)
        default = next(iter(agent_models.values()), arbiter)
        return CouncilBrain(default, self.council, agent_models=agent_models, arbiter_model=arbiter)

    async def run(self, emitter: EventEmitter, request: StartRunRequest) -> None:
        settings = self.settings
        roster = self.roster
        config = RunConfig(
            max_rounds=request.max_rounds
            if request.max_rounds is not None
            else settings.max_rounds,
            verdict_rule=request.verdict_rule or settings.verdict_rule,
            model=roster.arbiter.name,
            profile=roster.profile,
            mock=False,
            early_consensus=settings.early_consensus,
        )
        started = time.monotonic()
        emitter.emit(
            RunStarted,
            question=request.question,
            agents=[p.info(model=roster.agents[p.id].name) for p in self.council],
            config=config,
        )
        status = RunStatus.COMPLETED
        try:
            ctx = DeliberationContext(
                brain=self._brain(), emitter=emitter, council=self.council, config=config
            )
            await run_deliberation(request.question, ctx)
        except Exception as exc:
            log.exception("run %s failed", emitter.run_id)
            emitter.emit(RunError, message=f"{type(exc).__name__}: {exc}", fatal=True)
            status = RunStatus.FAILED
        emitter.emit(
            RunCompleted, status=status, duration_ms=int((time.monotonic() - started) * 1000)
        )


class RunManager:
    def __init__(
        self,
        engine: Engine,
        store: TraceStore,
        *,
        persist: bool = True,
        max_retained: int = 50,
    ) -> None:
        self.engine = engine
        self.store = store
        self.persist = persist
        self.max_retained = max_retained
        self._runs: OrderedDict[str, RunChannel] = OrderedDict()
        self._tasks: set[asyncio.Task[None]] = set()

    def get(self, run_id: str) -> RunChannel | None:
        return self._runs.get(run_id)

    def start(self, request: StartRunRequest) -> RunChannel:
        run_id = new_run_id()
        channel = RunChannel(run_id)
        writer = self.store.writer(run_id) if self.persist else None
        sinks = [channel.publish] + ([writer] if writer else [])
        emitter = EventEmitter(run_id, sinks)

        self._runs[run_id] = channel
        while len(self._runs) > self.max_retained:
            oldest_id, oldest = next(iter(self._runs.items()))
            if not oldest.done:
                break
            del self._runs[oldest_id]

        task = asyncio.create_task(self._execute(emitter, request, channel, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return channel

    async def _execute(
        self,
        emitter: EventEmitter,
        request: StartRunRequest,
        channel: RunChannel,
        writer: TraceWriter | None,
    ) -> None:
        try:
            await self.engine.run(emitter, request)
        except Exception as exc:  # engines handle their own errors; this is a backstop
            log.exception("engine crashed for run %s", channel.run_id)
            if not channel.done:
                emitter.emit(RunError, message=f"{type(exc).__name__}: {exc}", fatal=True)
                emitter.emit(RunCompleted, status=RunStatus.FAILED, duration_ms=0)
        finally:
            if writer is not None:
                writer.close()

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
