"""Runtime configuration, read from the environment and ``<repo>/.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from magi.events import VerdictRule
from magi.paths import DEFAULT_PERSONAS_DIR, DEFAULT_TRACES_DIR, ENV_FILE

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_prefix="MAGI_",
        env_ignore_empty=True,
        extra="ignore",
    )

    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    model: str = "claude-opus-5-5"
    effort: Effort = "medium"
    max_tokens: int = Field(default=8000, ge=1024)
    refusal_fallback: bool = True

    max_rounds: int = Field(default=2, ge=0, le=6)
    verdict_rule: VerdictRule = VerdictRule.MAJORITY
    early_consensus: bool = True

    mock: bool = False
    mock_speed: float = Field(default=1.0, gt=0)

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"
    traces_dir: Path = DEFAULT_TRACES_DIR
    personas_dir: Path = DEFAULT_PERSONAS_DIR

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
