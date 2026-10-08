"""Model profiles: which model runs each agent, and how clients get built."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from magi.emitter import EventEmitter
from magi.events import AgentMessage, RunStarted
from magi.llm import ConfigurationError, build_chat_model
from magi.mlx_launcher import PlanError, plan_servers
from magi.models import ModelSpec, ProfileError, resolve_roster
from magi.paths import REPO_ROOT
from magi.personas import Persona
from magi.runs import LiveEngine, StartRunRequest
from magi.settings import Settings
from tests.fakes import ScriptedChatModel, standard_script

MLX_PROFILE = REPO_ROOT / "models" / "mlx.yaml"


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def write_profile(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "profile.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_no_profile_uses_default_model_everywhere(council: list[Persona]) -> None:
    roster = resolve_roster(settings(model="claude-opus-5-5"), council)
    assert roster.profile is None
    assert {s.name for s in roster.specs} == {"claude-opus-5-5"}
    assert roster.requires_api_key


def test_bundled_mlx_profile(council: list[Persona]) -> None:
    roster = resolve_roster(settings(models=MLX_PROFILE), council)
    assert roster.profile == "mlx"
    assert not roster.requires_api_key
    assert roster.agents["melchior"].name == "mlx-community/Qwen3.5-9B-MLX-4bit"
    assert roster.agents["caspar"].base_url == "http://127.0.0.1:8093/v1"
    # Defaults are merged into each entry; entries can override them.
    assert roster.agents["balthasar"].temperature == 0.7
    assert roster.arbiter.temperature == 0.2
    assert roster.agents["caspar"].extra_body == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert all(spec.is_local for spec in roster.specs)


def test_unlisted_agents_keep_the_default(council: list[Persona], tmp_path: Path) -> None:
    path = write_profile(
        tmp_path,
        "agents:\n  caspar: {provider: openai, name: local, base_url: 'http://127.0.0.1:9/v1'}\n",
    )
    roster = resolve_roster(settings(models=path, model="claude-opus-5-5"), council)
    assert roster.agents["melchior"].name == "claude-opus-5-5"
    assert roster.agents["caspar"].name == "local"
    assert roster.arbiter.name == "claude-opus-5-5"
    assert roster.requires_api_key  # mixed council still needs the key


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("agents:\n  gendo: {name: x}\n", "no persona with id"),
        ("agents:\n  melchior: {provider: openai, name: x}\n", "needs a base_url"),
        ("agents:\n  melchior: {provider: ollama, name: x}\n", "melchior"),
        ("surprise: true\n", "invalid model profile"),
    ],
)
def test_invalid_profiles(council: list[Persona], tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ProfileError, match=message):
        resolve_roster(settings(models=write_profile(tmp_path, text)), council)


def test_missing_profile_file(council: list[Persona], tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="not found"):
        resolve_roster(settings(models=tmp_path / "nope.yaml"), council)


def test_openai_compatible_client() -> None:
    spec = ModelSpec(
        provider="openai",
        name="mlx-community/Qwen3-8B-4bit",
        base_url="http://127.0.0.1:8092/v1",
        max_tokens=900,
        temperature=0.3,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    model = build_chat_model(spec, settings())
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == spec.name
    assert model.openai_api_base == spec.base_url
    assert model.max_tokens == 900
    assert model.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert model.use_responses_api is False


def test_openai_compatible_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ModelSpec(provider="openai", name="m", base_url="http://h/v1", api_key_env="MY_KEY")
    with pytest.raises(ConfigurationError, match="MY_KEY"):
        build_chat_model(spec, settings())
    monkeypatch.setenv("MY_KEY", "secret")
    assert isinstance(build_chat_model(spec, settings()), ChatOpenAI)


def test_anthropic_client_needs_key() -> None:
    spec = ModelSpec(name="claude-opus-5-5")
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        build_chat_model(spec, settings())
    assert isinstance(build_chat_model(spec, settings(anthropic_api_key="k")), ChatAnthropic)


async def test_each_agent_runs_on_its_own_model(council: list[Persona]) -> None:
    built: list[tuple[ModelSpec, ScriptedChatModel]] = []

    def factory(spec: ModelSpec, _settings: Settings) -> ScriptedChatModel:
        model = ScriptedChatModel(script=standard_script())
        built.append((spec, model))
        return model

    engine = LiveEngine(settings(models=MLX_PROFILE), council, factory)
    events: list[Any] = []
    request = StartRunRequest(question="Should we?", max_rounds=1)
    await engine.run(EventEmitter("r", [events.append]), request)

    speakers: dict[str, set[str]] = {}
    for spec, model in built:
        speakers.setdefault(spec.name, set()).update(who for who, _ in model.calls)
    # The arbiter shares MELCHIOR's model (and server); its lower temperature
    # just means a separate client.
    assert speakers == {
        "mlx-community/Qwen3.5-9B-MLX-4bit": {"MELCHIOR-1", "ARBITER"},
        "mlx-community/Qwen3-8B-4bit": {"BALTHASAR-2"},
        "mlx-community/Llama-3.2-3B-Instruct-4bit": {"CASPAR-3"},
    }
    assert len(built) == 4  # one client per distinct spec, reused across rounds

    started = events[0]
    assert isinstance(started, RunStarted)
    assert started.config.profile == "mlx"
    assert started.config.model == "mlx-community/Qwen3.5-9B-MLX-4bit"
    assert {a.id: a.model for a in started.agents}["caspar"] == (
        "mlx-community/Llama-3.2-3B-Instruct-4bit"
    )
    assert any(isinstance(e, AgentMessage) for e in events)


def test_plan_servers_shares_ports(council: list[Persona]) -> None:
    roster = resolve_roster(settings(models=MLX_PROFILE), council)
    plans = plan_servers({**roster.agents, "arbiter": roster.arbiter})
    assert [(p.port, p.agents) for p in plans] == [
        (8091, ("melchior", "arbiter")),
        (8092, ("balthasar",)),
        (8093, ("caspar",)),
    ]


def test_plan_servers_rejects_two_models_on_one_port() -> None:
    url = "http://127.0.0.1:8091/v1"
    with pytest.raises(PlanError, match="two models"):
        plan_servers(
            {
                "a": ModelSpec(provider="openai", name="m1", base_url=url),
                "b": ModelSpec(provider="openai", name="m2", base_url=url),
            }
        )


def test_plan_servers_skips_remote_and_anthropic() -> None:
    plans = plan_servers(
        {
            "a": ModelSpec(name="claude-opus-5-5"),
            "b": ModelSpec(provider="openai", name="m", base_url="https://api.example.com/v1"),
        }
    )
    assert plans == []


def test_bundled_ollama_profile(council: list[Persona]) -> None:
    roster = resolve_roster(settings(models=REPO_ROOT / "models" / "ollama.yaml"), council)
    assert roster.profile == "ollama"
    assert not roster.requires_api_key
    # One Ollama server serves every model by name.
    assert {spec.base_url for spec in roster.specs} == {"http://127.0.0.1:11434/v1"}
    assert {spec.name for spec in roster.specs} == {"qwen3:8b", "llama3.1:8b", "gemma3:4b"}
    assert roster.arbiter.temperature == 0.2
