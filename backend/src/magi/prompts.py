"""Prompt templates for each deliberation phase.

Every phase asks for a single JSON object; ``brain.py`` validates the reply
against the matching pydantic model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from magi.events import Stance, VerdictRule, VoteChoice
from magi.personas import Persona


@dataclass(frozen=True)
class TranscriptEntry:
    message_id: str
    persona: Persona
    phase_label: str
    stance: Stance
    summary: str
    content: str


@dataclass(frozen=True)
class VoteEntry:
    persona: Persona
    vote: VoteChoice
    confidence: float
    rationale: str


def council_system_prompt(persona: Persona, council: Sequence[Persona]) -> str:
    roster = ", ".join(p.label for p in council)
    return f"""{persona.system_prompt.strip()}

## The council
You are one of {len(council)} members of the MAGI council: {roster}.
The council deliberates on a proposition, then each member votes APPROVE, DENY or ABSTAIN.

## How to deliberate
- Argue from your own priorities. Do not try to be balanced on behalf of the other members;
  they cover the other perspectives.
- Be concrete and brief. Plain prose only: no markdown, headings or bullet lists.
- Refer to other members by name when you answer them.
- Change your position when an argument genuinely persuades you, and say so plainly.
- Reply with a single JSON object and nothing else."""


ARBITER_SYSTEM_PROMPT = """You are the MAGI arbiter. You do not argue or vote. You record, \
neutrally and precisely, what the council decided and which arguments decided it.
Reply with a single JSON object and nothing else."""


def opening_prompt(question: str) -> str:
    return f"""PROPOSITION: {question}

OPENING STATEMENT. Give your initial position independently; you have not heard from the \
other members yet. If the proposition is phrased as a question, treat APPROVE as "yes".

Reply with JSON of exactly this shape:
{{
  "stance": "APPROVE" | "DENY" | "UNDECIDED",
  "summary": "<your position in one sentence, at most 25 words>",
  "argument": "<your opening argument, 60-140 words>"
}}"""


def debate_prompt(
    question: str,
    round_number: int,
    max_rounds: int,
    own: TranscriptEntry,
    others: Sequence[TranscriptEntry],
) -> str:
    other_blocks = "\n\n".join(
        f"[{entry.message_id}] {entry.persona.label}, stance {entry.stance.value}:\n{entry.content}"
        for entry in others
    )
    names = " | ".join(f'"{entry.persona.name}"' for entry in others)
    return f"""PROPOSITION: {question}

DEBATE ROUND {round_number} of {max_rounds}.

Your current position ({own.stance.value}): {own.summary}
Your previous argument:
{own.content}

Latest arguments from the other members:

{other_blocks}

Rebut, concede or sharpen. Engage directly with at least one other member's argument.

Reply with JSON of exactly this shape:
{{
  "responding_to": [{names}],
  "argument": "<your argument for this round, 60-140 words>",
  "stance": "APPROVE" | "DENY" | "UNDECIDED",
  "summary": "<your position now, in one sentence, at most 25 words>",
  "revised": true | false,
  "revision_reason": "<if your position materially changed this round, what changed it, in \
one sentence; otherwise an empty string>"
}}
"responding_to" lists only the members you actually answer."""


def vote_prompt(question: str, own: TranscriptEntry, others: Sequence[TranscriptEntry]) -> str:
    positions = "\n".join(
        f"- {entry.persona.label} ({entry.stance.value}): {entry.summary}" for entry in others
    )
    return f"""PROPOSITION: {question}

FINAL VOTE. The debate is over.

Your final position ({own.stance.value}): {own.summary}
Final positions of the other members:
{positions}

Vote APPROVE to accept the proposition or DENY to reject it. ABSTAIN only if you genuinely \
cannot decide.

Reply with JSON of exactly this shape:
{{
  "vote": "APPROVE" | "DENY" | "ABSTAIN",
  "confidence": <number from 0.0 to 1.0>,
  "rationale": "<one sentence>"
}}"""


_RULE_TEXT = {
    VerdictRule.MAJORITY: "majority: an outcome needs more than half of the whole council",
    VerdictRule.UNANIMOUS: "unanimous: the proposition passes only if every member approves",
}


def synthesis_prompt(
    question: str,
    rule: VerdictRule,
    outcome: str,
    tally_text: str,
    transcript: Sequence[TranscriptEntry],
    votes: Sequence[VoteEntry],
) -> str:
    transcript_text = "\n\n".join(
        f"[{entry.message_id}] {entry.persona.name}, {entry.phase_label}, "
        f"stance {entry.stance.value}:\n{entry.content}"
        for entry in transcript
    )
    vote_text = "\n".join(
        f"- {v.persona.name}: {v.vote.value} (confidence {v.confidence:.2f}) - {v.rationale}"
        for v in votes
    )
    return f"""PROPOSITION: {question}
DECISION RULE: {_RULE_TEXT[rule]}
OUTCOME: {outcome} ({tally_text})

TRANSCRIPT:
{transcript_text}

VOTES:
{vote_text}

Write the council's final summary: what was decided, and which arguments decided it. Cite \
arguments by their [message_id] in brackets.

Reply with JSON of exactly this shape:
{{
  "summary": "<80-160 words>",
  "decisive_arguments": [
    {{"message_id": "<an id from the transcript>", "reason": "<why it mattered, one sentence>"}}
  ]
}}
List 1-3 decisive arguments."""


def repair_suffix(error: str) -> str:
    return (
        "\n\nIMPORTANT: your previous reply could not be used "
        f"({error}). Reply with only the JSON object, exactly in the shape above."
    )
