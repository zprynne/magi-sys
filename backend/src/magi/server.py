"""HTTP API: start runs, stream their events over SSE, browse saved traces.

    GET  /api/health
    GET  /api/config                    council, defaults, mock flag
    POST /api/runs                      start a deliberation -> {run_id}
    GET  /api/runs/{run_id}/events      SSE stream (resumable via Last-Event-ID)
    GET  /api/traces                    saved traces, newest first
    GET  /api/traces/{trace_id}         all events of one trace

If ``frontend/dist`` exists it is served at ``/`` as a single-page app.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from magi import __version__
from magi.events import AgentInfo, EventBase, MagiEvent, VerdictRule, dump_event
from magi.llm import build_chat_model
from magi.mock import MockEngine
from magi.paths import REPO_ROOT
from magi.personas import load_personas
from magi.runs import Engine, LiveEngine, ModelFactory, RunManager, StartRunRequest
from magi.settings import Effort, Settings, get_settings
from magi.traces import TraceNotFoundError, TraceStore, TraceSummary

log = logging.getLogger(__name__)

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class ConfigResponse(BaseModel):
    version: str
    mock: bool
    model: str
    effort: Effort
    api_key_configured: bool
    max_rounds: int
    verdict_rule: VerdictRule
    early_consensus: bool
    agents: list[AgentInfo]
    replayable: list[TraceSummary]


class StartRunResponse(BaseModel):
    run_id: str


class TraceDetail(BaseModel):
    trace_id: str
    events: list[MagiEvent]


def _sse(event: EventBase) -> str:
    return f"id: {event.seq}\ndata: {dump_event(event)}\n\n"


def create_app(
    settings: Settings | None = None,
    *,
    model_factory: ModelFactory = build_chat_model,
    engine: Engine | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    council = load_personas(settings.personas_dir)
    store = TraceStore(settings.traces_dir)
    if engine is None:
        engine = (
            MockEngine(store, speed=settings.mock_speed)
            if settings.mock
            else LiveEngine(settings, council, model_factory)
        )
    # Mock replays are copies of existing traces, so they are not persisted again.
    manager = RunManager(engine, store, persist=not settings.mock)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        mode = "MOCK (trace replay)" if settings.mock else f"LIVE ({settings.model})"
        log.info("MAGI online: %s, %d agents, traces in %s", mode, len(council), store.directory)
        yield
        await manager.shutdown()

    app = FastAPI(title="MAGI", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.manager = manager
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api")

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/config")
    def config() -> ConfigResponse:
        return ConfigResponse(
            version=__version__,
            mock=settings.mock,
            model=settings.model,
            effort=settings.effort,
            api_key_configured=settings.anthropic_api_key is not None,
            max_rounds=settings.max_rounds,
            verdict_rule=settings.verdict_rule,
            early_consensus=settings.early_consensus,
            agents=[p.info() for p in council],
            replayable=store.list() if settings.mock else [],
        )

    @api.post("/runs", status_code=status.HTTP_201_CREATED)
    async def start_run(request: StartRunRequest) -> StartRunResponse:
        if isinstance(engine, MockEngine):
            try:
                await run_in_threadpool(engine.resolve, request)
            except TraceNotFoundError as exc:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, f"no trace to replay: {exc}"
                ) from None
        channel = manager.start(request)
        return StartRunResponse(run_id=channel.run_id)

    @api.get("/runs/{run_id}/events", response_class=StreamingResponse)
    async def run_events(
        run_id: str,
        after: int = Query(default=0, ge=0, description="Resume after this seq."),
        last_event_id: str | None = Header(default=None),
    ) -> StreamingResponse:
        header_seq = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
        resume_after = max(after, header_seq)
        channel = manager.get(run_id)

        if channel is None:
            # Not live in this process: fall back to the saved trace, if any.
            try:
                saved = store.load(run_id)
            except TraceNotFoundError:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown run {run_id}") from None

            async def replay_saved() -> AsyncIterator[str]:
                for event in saved:
                    if event.seq > resume_after:
                        yield _sse(event)

            return StreamingResponse(
                replay_saved(), media_type="text/event-stream", headers=SSE_HEADERS
            )

        async def follow() -> AsyncIterator[str]:
            yield "retry: 2000\n\n"
            async for event in channel.stream(after_seq=resume_after):
                yield ": keep-alive\n\n" if event is None else _sse(event)

        return StreamingResponse(follow(), media_type="text/event-stream", headers=SSE_HEADERS)

    # Plain `def` endpoints touch the filesystem and run in FastAPI's threadpool.
    @api.get("/traces")
    def list_traces() -> list[TraceSummary]:
        return store.list()

    @api.get("/traces/{trace_id}")
    def get_trace(trace_id: str) -> TraceDetail:
        try:
            return TraceDetail(trace_id=trace_id, events=store.load(trace_id))
        except TraceNotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown trace {trace_id}") from None

    app.include_router(api)

    if FRONTEND_DIST.is_dir():
        _mount_frontend(app, FRONTEND_DIST)

    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the MAGI API server.")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "magi.server:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(Path(__file__).parent)] if args.reload else None,
    )


if __name__ == "__main__":
    main()
