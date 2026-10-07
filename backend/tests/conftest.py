from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from magi.brain import CouncilBrain
from magi.emitter import EventEmitter
from magi.events import EventBase, RunConfig, VerdictRule
from magi.graph import DeliberationContext
from magi.paths import DEFAULT_PERSONAS_DIR
from magi.personas import Persona, load_personas
from tests.fakes import ScriptedChatModel, standard_script


@pytest.fixture
def council() -> list[Persona]:
    return load_personas(DEFAULT_PERSONAS_DIR)


@pytest.fixture
def script() -> dict[tuple[str, str], Any]:
    return standard_script()


ContextFactory = Callable[..., tuple[DeliberationContext, list[EventBase], ScriptedChatModel]]


@pytest.fixture
def make_context(council: list[Persona], script: dict[tuple[str, str], Any]) -> ContextFactory:
    """Build a deliberation context around a scripted model; returns the context,
    the list that collects emitted events, and the model (to inspect calls)."""

    def factory(
        *,
        max_rounds: int = 2,
        rule: VerdictRule = VerdictRule.MAJORITY,
        early_consensus: bool = True,
        overrides: dict[tuple[str, str], Any] | None = None,
        delay: float = 0.0,
    ) -> tuple[DeliberationContext, list[EventBase], ScriptedChatModel]:
        model = ScriptedChatModel(script={**script, **(overrides or {})}, delay=delay)
        events: list[EventBase] = []
        ctx = DeliberationContext(
            brain=CouncilBrain(model, council),
            emitter=EventEmitter("test-run", [events.append]),
            council=council,
            config=RunConfig(
                max_rounds=max_rounds,
                verdict_rule=rule,
                model="scripted",
                early_consensus=early_consensus,
            ),
        )
        return ctx, events, model

    return factory


@pytest.fixture
def traces_dir(tmp_path: Path) -> Path:
    path = tmp_path / "traces"
    path.mkdir()
    return path
