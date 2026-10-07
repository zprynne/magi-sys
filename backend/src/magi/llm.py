"""Chat model factory."""

from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from magi.settings import Settings

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ConfigurationError(RuntimeError):
    pass


def build_chat_model(settings: Settings) -> BaseChatModel:
    if settings.anthropic_api_key is None:
        raise ConfigurationError(
            "ANTHROPIC_API_KEY is not set. Add it to .env, or run with MAGI_MOCK=1."
        )
    extra: dict[str, Any] = {}
    if settings.refusal_fallback and settings.model in _FALLBACK_MODELS:
        # If a safety classifier declines, the API retries on a substitute model
        # instead of returning a refusal.
        extra["betas"] = [_FALLBACK_BETA]
        extra["model_kwargs"] = {"fallbacks": "default"}
    return ChatAnthropic(
        model=settings.model,
        api_key=settings.anthropic_api_key,
        max_tokens=settings.max_tokens,
        effort=settings.effort,
        max_retries=3,
        default_request_timeout=300,
        **extra,
    )
