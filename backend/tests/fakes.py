"""Scripted stand-ins for the chat model, used by the graph and API tests."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

_SPEAKER = re.compile(r"You are ([A-Z]+-\d)")
_ROUND = re.compile(r"DEBATE ROUND (\d+)")


def classify(messages: list[BaseMessage]) -> tuple[str, str]:
    """Return (speaker, phase_key) for a prompt, e.g. ("MELCHIOR-1", "debate1")."""
    system, user = str(messages[0].content), str(messages[-1].content)
    match = _SPEAKER.search(system)
    speaker = match.group(1) if match else "ARBITER"
    if "OPENING STATEMENT" in user:
        return speaker, "opening"
    if round_match := _ROUND.search(user):
        return speaker, f"debate{round_match.group(1)}"
    if "FINAL VOTE" in user:
        return speaker, "vote"
    return speaker, "synthesis"


class ScriptedChatModel(BaseChatModel):
    """Answers each prompt from ``script[(speaker, phase_key)]``.

    A value may be a dict (sent as JSON), a raw string, or a list of those for
    successive attempts (to exercise the repair retry). ``delay`` simulates
    latency so parallel fan-out is observable.
    """

    script: dict[tuple[str, str], Any]
    delay: float = 0.0
    calls: list[tuple[str, str]] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _reply(self, messages: list[BaseMessage]) -> ChatResult:
        key = classify(messages)
        attempt = sum(1 for call in self.calls if call == key)
        self.calls.append(key)
        self.prompts.append(str(messages[-1].content))
        entry = self.script[key]
        if isinstance(entry, list):
            entry = entry[min(attempt, len(entry) - 1)]
        if isinstance(entry, BaseException):
            raise entry
        text = entry if isinstance(entry, str) else json.dumps(entry)
        metadata = {"stop_reason": "refusal"} if text == "<refusal>" else {}
        message = AIMessage(content=text, response_metadata=metadata)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._reply(messages)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.delay:
            await asyncio.sleep(self.delay)
        return self._reply(messages)


MELCHIOR, BALTHASAR, CASPAR = "MELCHIOR-1", "BALTHASAR-2", "CASPAR-3"


def opening(stance: str, summary: str = "position") -> dict[str, Any]:
    return {"stance": stance, "summary": summary, "argument": f"Opening argument: {summary}."}


def rebuttal(
    stance: str, *responding_to: str, revised: bool = False, reason: str = ""
) -> dict[str, Any]:
    return {
        "responding_to": list(responding_to),
        "argument": f"Rebuttal leaning {stance}.",
        "stance": stance,
        "summary": f"Now {stance}.",
        "revised": revised,
        "revision_reason": reason,
    }


def ballot(vote: str, confidence: float = 0.8) -> dict[str, Any]:
    return {"vote": vote, "confidence": confidence, "rationale": f"I vote {vote}."}


def standard_script() -> dict[tuple[str, str], Any]:
    """Two debate rounds; CASPAR moves from UNDECIDED to APPROVE; votes 2-1."""
    return {
        (MELCHIOR, "opening"): opening("APPROVE", "The data supports it."),
        (BALTHASAR, "opening"): opening("DENY", "The risks are unmanaged."),
        (CASPAR, "opening"): opening("UNDECIDED", "It depends who chooses."),
        (MELCHIOR, "debate1"): rebuttal("APPROVE", BALTHASAR),
        (BALTHASAR, "debate1"): rebuttal("DENY", "Melchior", "caspar"),
        (CASPAR, "debate1"): rebuttal(
            "APPROVE", MELCHIOR, revised=True, reason="Opt-in solves it."
        ),
        (MELCHIOR, "debate2"): rebuttal("APPROVE", CASPAR),
        (BALTHASAR, "debate2"): rebuttal("DENY", CASPAR),
        (CASPAR, "debate2"): rebuttal("APPROVE", BALTHASAR),
        (MELCHIOR, "vote"): ballot("APPROVE", 0.9),
        (BALTHASAR, "vote"): ballot("DENY", 0.7),
        (CASPAR, "vote"): ballot("APPROVE", 0.6),
        ("ARBITER", "synthesis"): {
            "summary": "Approved 2-1. [caspar-r1] tipped the balance.",
            "decisive_arguments": [
                {"message_id": "[caspar-r1]", "reason": "Opt-in addressed consent."},
                {"message_id": "bogus-r9", "reason": "Not a real message."},
            ],
        },
    }
