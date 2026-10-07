"""LLM calls for each deliberation phase, with JSON validation.

The brain works with any LangChain ``BaseChatModel``: ``ChatAnthropic`` in
production, scripted fakes in tests. Replies are parsed as JSON and validated
with pydantic; one repair attempt is made before giving up with
``AgentOutputError`` (which the graph treats as a recoverable, per-agent
failure).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError, field_validator

from magi import prompts
from magi.events import Stance, VerdictRule, VoteChoice
from magi.personas import Persona
from magi.prompts import TranscriptEntry, VoteEntry

log = logging.getLogger(__name__)


class AgentOutputError(RuntimeError):
    """The model declined or kept producing unusable output."""


# --------------------------------------------------------------------------- #
# Structured outputs (lenient on input, strict on what they produce)
# --------------------------------------------------------------------------- #


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


class OpeningOutput(BaseModel):
    stance: Stance
    summary: str = Field(min_length=1)
    argument: str = Field(min_length=1)

    _norm_stance = field_validator("stance", mode="before")(_upper)


class DebateOutput(BaseModel):
    responding_to: list[str] = Field(default_factory=list)
    argument: str = Field(min_length=1)
    stance: Stance
    summary: str = Field(min_length=1)
    revised: bool = False
    revision_reason: str = ""

    _norm_stance = field_validator("stance", mode="before")(_upper)


class VoteOutput(BaseModel):
    vote: VoteChoice
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)

    _norm_vote = field_validator("vote", mode="before")(_upper)

    @field_validator("confidence", mode="before")
    @classmethod
    def _percent_to_unit(cls, value: Any) -> Any:
        # Models occasionally answer 85 instead of 0.85.
        if isinstance(value, int | float) and 1.0 < value <= 100.0:
            return value / 100.0
        return value


class CitedArgument(BaseModel):
    message_id: str
    reason: str


class SynthesisOutput(BaseModel):
    summary: str = Field(min_length=1)
    decisive_arguments: list[CitedArgument] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# JSON extraction
# --------------------------------------------------------------------------- #

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply (tolerates code fences and
    surrounding prose)."""
    fenced = _FENCE.search(text)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in reply")
    data = json.loads(candidate[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("reply JSON is not an object")
    return data


def parse_reply[T: BaseModel](text: str, schema: type[T]) -> T:
    return schema.model_validate(extract_json_object(text))


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"]) or "reply"
        return f"{loc}: {first['msg']}"
    return str(exc)[:200]


# --------------------------------------------------------------------------- #
# Brain
# --------------------------------------------------------------------------- #


class CouncilBrain:
    def __init__(self, model: BaseChatModel, council: Sequence[Persona], max_attempts: int = 2):
        self.model = model
        self.council = list(council)
        self.max_attempts = max_attempts

    async def opening(self, persona: Persona, question: str) -> OpeningOutput:
        return await self._ask(
            self._system(persona), prompts.opening_prompt(question), OpeningOutput
        )

    async def debate(
        self,
        persona: Persona,
        question: str,
        round_number: int,
        max_rounds: int,
        own: TranscriptEntry,
        others: Sequence[TranscriptEntry],
    ) -> DebateOutput:
        user = prompts.debate_prompt(question, round_number, max_rounds, own, others)
        return await self._ask(self._system(persona), user, DebateOutput)

    async def vote(
        self,
        persona: Persona,
        question: str,
        own: TranscriptEntry,
        others: Sequence[TranscriptEntry],
    ) -> VoteOutput:
        user = prompts.vote_prompt(question, own, others)
        return await self._ask(self._system(persona), user, VoteOutput)

    async def synthesize(
        self,
        question: str,
        rule: VerdictRule,
        outcome: str,
        tally_text: str,
        transcript: Sequence[TranscriptEntry],
        votes: Sequence[VoteEntry],
    ) -> SynthesisOutput:
        user = prompts.synthesis_prompt(question, rule, outcome, tally_text, transcript, votes)
        return await self._ask(prompts.ARBITER_SYSTEM_PROMPT, user, SynthesisOutput)

    def _system(self, persona: Persona) -> str:
        return prompts.council_system_prompt(persona, self.council)

    async def _ask[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T:
        last_error = "unknown error"
        for attempt in range(1, self.max_attempts + 1):
            content = user if attempt == 1 else user + prompts.repair_suffix(last_error)
            reply = await self.model.ainvoke([SystemMessage(system), HumanMessage(content)])
            if not isinstance(reply, AIMessage):  # pragma: no cover - defensive
                raise AgentOutputError(f"unexpected reply type {type(reply).__name__}")
            if reply.response_metadata.get("stop_reason") == "refusal":
                raise AgentOutputError("the model declined to answer")
            try:
                return parse_reply(reply.text, schema)
            except (ValueError, ValidationError) as exc:
                last_error = _short_error(exc)
                log.warning(
                    "unparseable %s reply (attempt %d/%d): %s",
                    schema.__name__,
                    attempt,
                    self.max_attempts,
                    last_error,
                )
        raise AgentOutputError(f"no valid {schema.__name__} after retry: {last_error}")
