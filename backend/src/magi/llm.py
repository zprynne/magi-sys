"""Chat model factory: one LangChain chat model per ModelSpec."""

from __future__ import annotations

import os
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from magi.models import ModelSpec
from magi.settings import Settings

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_LOCAL_MAX_TOKENS = 1024


class ConfigurationError(RuntimeError):
    pass


def build_chat_model(spec: ModelSpec, settings: Settings) -> BaseChatModel:
    if spec.provider == "anthropic":
        return _anthropic(spec, settings)
    return _openai_compatible(spec)


def _anthropic(spec: ModelSpec, settings: Settings) -> BaseChatModel:
    if settings.anthropic_api_key is None:
        raise ConfigurationError(
            "ANTHROPIC_API_KEY is not set. Add it to .env, run with MAGI_MOCK=1, "
            "or use an all-local model profile (MAGI_MODELS=models/mlx.yaml)."
        )
    extra: dict[str, Any] = {}
    if settings.refusal_fallback and spec.name in _FALLBACK_MODELS:
        # If a safety classifier declines, the API retries on a substitute model
        # instead of returning a refusal.
        extra["betas"] = [_FALLBACK_BETA]
        extra["model_kwargs"] = {"fallbacks": "default"}
    return ChatAnthropic(
        model=spec.name,
        api_key=settings.anthropic_api_key,
        max_tokens=spec.max_tokens or settings.max_tokens,
        effort=settings.effort,
        max_retries=3,
        default_request_timeout=300,
        **extra,
    )


def _openai_compatible(spec: ModelSpec) -> BaseChatModel:
    api_key = os.environ.get(spec.api_key_env, "") if spec.api_key_env else ""
    if spec.api_key_env and not api_key:
        raise ConfigurationError(f"{spec.api_key_env} is not set (needed for {spec.name})")
    return ChatOpenAI(
        model=spec.name,
        base_url=spec.base_url,
        # Local servers ignore the key, but the client requires a value.
        api_key=api_key or "not-needed",
        max_tokens=spec.max_tokens or _LOCAL_MAX_TOKENS,
        temperature=spec.temperature,
        extra_body=spec.extra_body or None,
        # Local generation is slow and usually serialised per server.
        timeout=600,
        max_retries=1,
        use_responses_api=False,
    )
