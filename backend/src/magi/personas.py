"""Council personas, loaded from YAML files (one file per agent)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from magi.events import AgentInfo


class Persona(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    title: str
    color: str
    order: int = 0
    priorities: list[str] = Field(default_factory=list)
    system_prompt: str

    def info(self) -> AgentInfo:
        return AgentInfo(
            id=self.id,
            name=self.name,
            title=self.title,
            color=self.color,
            priorities=list(self.priorities),
        )

    @property
    def label(self) -> str:
        return f"{self.name} ({self.title})"


class PersonaError(ValueError):
    pass


def load_personas(directory: Path) -> list[Persona]:
    files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    if not files:
        raise PersonaError(f"no persona files (*.yaml) found in {directory}")
    personas = [Persona.model_validate(yaml.safe_load(path.read_text())) for path in files]
    ids = [p.id for p in personas]
    if len(set(ids)) != len(ids):
        raise PersonaError(f"duplicate persona ids in {directory}: {ids}")
    if len(personas) < 2:
        raise PersonaError("a council needs at least two personas")
    return sorted(personas, key=lambda p: (p.order, p.id))


_NON_ALNUM = re.compile(r"[^a-z0-9]")


def resolve_persona_ref(ref: str, personas: list[Persona]) -> Persona | None:
    """Map a free-text reference from the model ('BALTHASAR-2', 'Balthasar',
    'the Guardian') to a persona, or None if it matches nothing."""
    needle = _NON_ALNUM.sub("", ref.lower())
    if not needle:
        return None
    for persona in personas:
        name = _NON_ALNUM.sub("", persona.name.lower())
        title = _NON_ALNUM.sub("", persona.title.lower())
        if needle in (persona.id, name, title) or persona.id in needle:
            return persona
    return None
