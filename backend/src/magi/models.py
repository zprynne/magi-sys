"""Which model runs each council member.

Personas say *who* an agent is; a model profile says *what runs it*. Without a
profile every agent and the arbiter use ``MAGI_MODEL`` on Anthropic. A profile
(``MAGI_MODELS=models/mlx.yaml``) can give each agent its own model, including
local ones served over an OpenAI-compatible API (mlx_lm.server, LM Studio,
Ollama, vLLM, llama.cpp).

    defaults:            # merged into every entry below
      provider: openai
      max_tokens: 1024
    agents:
      melchior: {name: mlx-community/Qwen3-8B-4bit, base_url: http://127.0.0.1:8091/v1}
    arbiter: {name: ..., base_url: ...}

Agents and the arbiter that a profile does not mention keep the default model.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from magi.personas import Persona
from magi.settings import Settings

Provider = Literal["anthropic", "openai"]


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider = "anthropic"
    name: str = Field(min_length=1, description="Model id sent to the provider.")
    base_url: str | None = Field(
        default=None, description="Required for provider 'openai' (OpenAI-compatible servers)."
    )
    api_key_env: str | None = Field(
        default=None,
        description="Env var holding the key for an OpenAI-compatible server; local "
        "servers usually need none.",
    )
    max_tokens: int | None = Field(default=None, ge=16)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    extra_body: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra request fields, e.g. chat_template_kwargs for mlx_lm.server.",
    )

    @model_validator(mode="after")
    def _openai_needs_base_url(self) -> ModelSpec:
        if self.provider == "openai" and not self.base_url:
            raise ValueError(f"model {self.name!r}: provider 'openai' needs a base_url")
        return self

    @property
    def key(self) -> str:
        """Identity for caching clients (two agents on one server share a client)."""
        return self.model_dump_json()

    @property
    def is_local(self) -> bool:
        if not self.base_url:
            return False
        host = urlparse(self.base_url).hostname or ""
        return host in {"127.0.0.1", "localhost", "::1"} or host.endswith(".local")


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: dict[str, Any] = Field(default_factory=dict)
    agents: dict[str, dict[str, Any]] = Field(default_factory=dict)
    arbiter: dict[str, Any] | None = None


class Roster(BaseModel):
    """The resolved model for every agent and for the arbiter."""

    model_config = ConfigDict(frozen=True)

    profile: str | None
    agents: dict[str, ModelSpec]
    arbiter: ModelSpec

    @property
    def specs(self) -> list[ModelSpec]:
        return [*self.agents.values(), self.arbiter]

    @property
    def requires_api_key(self) -> bool:
        return any(spec.provider == "anthropic" for spec in self.specs)


class ProfileError(ValueError):
    pass


def default_spec(settings: Settings) -> ModelSpec:
    return ModelSpec(provider="anthropic", name=settings.model)


def load_profile(path: Path) -> ModelProfile:
    if not path.is_file():
        raise ProfileError(f"model profile not found: {path}")
    try:
        return ModelProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except ValidationError as exc:
        raise ProfileError(f"invalid model profile {path}: {exc}") from exc


def resolve_roster(settings: Settings, council: Sequence[Persona]) -> Roster:
    fallback = default_spec(settings)
    if settings.models is None:
        return Roster(profile=None, agents={p.id: fallback for p in council}, arbiter=fallback)

    profile = load_profile(settings.models)
    unknown = set(profile.agents) - {p.id for p in council}
    if unknown:
        raise ProfileError(f"{settings.models.name}: no persona with id {sorted(unknown)}")

    def build(entry: dict[str, Any] | None, who: str) -> ModelSpec:
        if entry is None:
            return fallback
        try:
            return ModelSpec.model_validate({**profile.defaults, **entry})
        except ValidationError as exc:
            raise ProfileError(f"{settings.models}: {who}: {exc}") from exc

    return Roster(
        profile=settings.models.stem,
        agents={p.id: build(profile.agents.get(p.id), p.id) for p in council},
        arbiter=build(profile.arbiter, "arbiter"),
    )
