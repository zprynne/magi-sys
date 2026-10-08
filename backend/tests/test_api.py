"""HTTP + SSE API, with a scripted model behind the live engine."""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from magi.events import RunStatus
from magi.llm import ConfigurationError
from magi.models import ModelSpec
from magi.paths import DEFAULT_TRACES_DIR
from magi.server import create_app
from magi.settings import Settings
from magi.traces import read_trace
from tests.fakes import ScriptedChatModel, standard_script


def settings_for(traces_dir: Path, **overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        anthropic_api_key="test-key",
        traces_dir=traces_dir,
        **overrides,
    )


def scripted(_spec: ModelSpec, _settings: Settings) -> ScriptedChatModel:
    return ScriptedChatModel(script=standard_script())


@pytest.fixture
async def client(traces_dir: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings_for(traces_dir), model_factory=scripted)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://magi"
    ) as c:
        yield c


def files_in(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def sse_events(body: str) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


async def start(client: httpx.AsyncClient, **body: Any) -> str:
    response = await client.post("/api/runs", json={"question": "Should we test this?", **body})
    assert response.status_code == 201, response.text
    run_id: str = response.json()["run_id"]
    return run_id


async def test_config(client: httpx.AsyncClient) -> None:
    data = (await client.get("/api/config")).json()
    assert data["mock"] is False
    assert data["api_key_configured"] is True
    assert [a["name"] for a in data["agents"]] == ["MELCHIOR-1", "BALTHASAR-2", "CASPAR-3"]
    assert data["replayable"] == []


async def test_run_streams_and_persists(client: httpx.AsyncClient, traces_dir: Path) -> None:
    run_id = await start(client, max_rounds=1, verdict_rule="unanimous")
    response = await client.get(f"/api/runs/{run_id}/events")
    assert response.headers["content-type"].startswith("text/event-stream")

    events = sse_events(response.text)
    assert events[0]["type"] == "run_started"
    assert events[0]["config"]["max_rounds"] == 1
    assert events[0]["config"]["verdict_rule"] == "unanimous"
    assert events[-1]["type"] == "run_completed"
    assert events[-1]["status"] == "completed"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert "id: 1\n" in response.text

    saved = read_trace(traces_dir / f"{run_id}.jsonl")
    assert [e.seq for e in saved] == [e["seq"] for e in events]

    listing = (await client.get("/api/traces")).json()
    assert listing[0]["trace_id"] == run_id
    assert listing[0]["outcome"] == "DENIED"

    detail = (await client.get(f"/api/traces/{run_id}")).json()
    assert len(detail["events"]) == len(events)


async def test_sse_resumes_after_last_event_id(client: httpx.AsyncClient) -> None:
    run_id = await start(client)
    full = sse_events((await client.get(f"/api/runs/{run_id}/events")).text)
    resumed = sse_events(
        (await client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "10"})).text
    )
    assert [e["seq"] for e in resumed] == [e["seq"] for e in full if e["seq"] > 10]
    via_query = sse_events((await client.get(f"/api/runs/{run_id}/events?after=20")).text)
    assert via_query[0]["seq"] == 21


async def test_unknown_run_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/runs/nope/events")).status_code == 404


async def test_saved_trace_streams_after_restart(traces_dir: Path) -> None:
    shutil.copy(DEFAULT_TRACES_DIR / "example-er-triage.jsonl", traces_dir)
    app = create_app(settings_for(traces_dir), model_factory=scripted)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://m") as c:
        events = sse_events((await c.get("/api/runs/example-er-triage/events")).text)
    assert events[-1]["type"] == "run_completed"


@pytest.mark.parametrize("trace_id", ["missing", "..%2F..%2Fetc%2Fpasswd", ".hidden"])
async def test_trace_lookup_is_safe(client: httpx.AsyncClient, trace_id: str) -> None:
    assert (await client.get(f"/api/traces/{trace_id}")).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"question": ""},
        {"question": "  hi "},
        {"question": "Valid question?", "max_rounds": 9},
        {"question": "Valid question?", "verdict_rule": "plurality"},
    ],
)
async def test_invalid_run_requests(client: httpx.AsyncClient, body: dict[str, Any]) -> None:
    assert (await client.post("/api/runs", json=body)).status_code == 422


async def test_missing_api_key_fails_the_run_cleanly(traces_dir: Path) -> None:
    def no_key(_spec: ModelSpec, _settings: Settings) -> ScriptedChatModel:
        raise ConfigurationError("ANTHROPIC_API_KEY is not set")

    app: FastAPI = create_app(settings_for(traces_dir), model_factory=no_key)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://m") as c:
        run_id = await start(c)
        events = sse_events((await c.get(f"/api/runs/{run_id}/events")).text)

    assert [e["type"] for e in events] == ["run_started", "run_error", "run_completed"]
    assert events[1]["fatal"] is True
    assert "ANTHROPIC_API_KEY" in events[1]["message"]
    assert events[2]["status"] == RunStatus.FAILED.value


async def test_mock_mode_replays_without_a_model(traces_dir: Path) -> None:
    shutil.copy(DEFAULT_TRACES_DIR / "example-delivery-drones.jsonl", traces_dir)

    def forbidden(_spec: ModelSpec, _settings: Settings) -> ScriptedChatModel:
        raise AssertionError("mock mode must not build a model")

    settings = settings_for(traces_dir, mock=True, mock_speed=1000.0)
    app = create_app(settings, model_factory=forbidden)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://m") as c:
        config = (await c.get("/api/config")).json()
        assert config["mock"] is True
        assert [t["trace_id"] for t in config["replayable"]] == ["example-delivery-drones"]

        assert (
            await c.post("/api/runs", json={"question": "q?!", "trace_id": "nope"})
        ).status_code == 404

        run_id = await start(c)
        events = sse_events((await c.get(f"/api/runs/{run_id}/events")).text)

    assert events[0]["config"]["mock"] is True
    assert {e["run_id"] for e in events} == {run_id}
    assert events[-1]["type"] == "run_completed"
    # Replays are not persisted a second time.
    assert files_in(traces_dir) == ["example-delivery-drones.jsonl"]


async def test_config_for_all_local_profile(traces_dir: Path) -> None:
    from magi.paths import REPO_ROOT

    settings = Settings(
        _env_file=None, traces_dir=traces_dir, models=REPO_ROOT / "models" / "mlx.yaml"
    )
    app = create_app(settings, model_factory=scripted)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://m") as c:
        data = (await c.get("/api/config")).json()
    assert data["profile"] == "mlx"
    assert data["requires_api_key"] is False
    assert data["api_key_configured"] is False
    assert {a["id"]: a["model"] for a in data["agents"]}["balthasar"] == (
        "mlx-community/Qwen3-8B-4bit"
    )
