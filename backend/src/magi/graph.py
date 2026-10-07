"""The deliberation graph (LangGraph).

    START -> begin --Send x N--> opening --> debate_gate --Send x N--> debate --+
                                                 ^  |                           |
                                                 |  +--Send x N--> vote         |
                                                 +-----------------------------+
    vote -> tally -> synthesize -> END

* ``opening``, ``debate`` and ``vote`` run once per council member in parallel
  (fan-out with ``Send``); each emits ``agent_thinking`` before its LLM call
  and its result event afterwards.
* ``debate_gate`` decides whether to run another debate round (up to
  ``max_rounds``, stopping early on consensus) or move to the vote.
* ``tally`` applies the verdict rule; ``synthesize`` writes the final summary
  and emits ``verdict``.

Agent-level failures (refusals, unparseable output) are recoverable: the
agent's turn is replaced with a placeholder, a non-fatal ``run_error`` is
emitted and the run continues. Anything else propagates and fails the run.
"""

from __future__ import annotations

import operator
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from magi.brain import AgentOutputError, CouncilBrain, OpeningOutput
from magi.emitter import EventEmitter
from magi.events import (
    AgentMessage,
    AgentRevisedPosition,
    AgentThinking,
    DecisiveArgument,
    Phase,
    PhaseStarted,
    ReplyRef,
    RunConfig,
    RunError,
    Stance,
    Verdict,
    VoteCast,
    VoteChoice,
)
from magi.personas import Persona, resolve_persona_ref
from magi.prompts import TranscriptEntry, VoteEntry
from magi.voting import Ballot, Decision, decide

# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MessageRecord:
    message_id: str
    agent_id: str
    phase: Phase
    round: int
    content: str
    stance: Stance
    summary: str
    reply_to: tuple[ReplyRef, ...] = ()


class DeliberationState(TypedDict):
    question: str
    round: int
    next_phase: Literal["debate", "vote"]
    messages: Annotated[list[MessageRecord], operator.add]
    ballots: Annotated[list[Ballot], operator.add]
    revision_rounds: Annotated[list[int], operator.add]
    decision: Decision | None


class AgentTask(TypedDict):
    """Payload sent to one agent's node invocation."""

    agent_id: str
    question: str
    round: int
    messages: list[MessageRecord]


@dataclass
class DeliberationContext:
    brain: CouncilBrain
    emitter: EventEmitter
    council: list[Persona]
    config: RunConfig
    by_id: dict[str, Persona] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {p.id: p for p in self.council}


Rt = Runtime[DeliberationContext]


def message_id(agent_id: str, round_number: int) -> str:
    return f"{agent_id}-r{round_number}"


def latest_by_agent(messages: Sequence[MessageRecord]) -> dict[str, MessageRecord]:
    latest: dict[str, MessageRecord] = {}
    for msg in messages:
        if msg.agent_id not in latest or msg.round >= latest[msg.agent_id].round:
            latest[msg.agent_id] = msg
    return latest


def _entry(msg: MessageRecord, ctx: DeliberationContext) -> TranscriptEntry:
    label = "opening" if msg.phase is Phase.OPENING else f"round {msg.round}"
    return TranscriptEntry(
        message_id=msg.message_id,
        persona=ctx.by_id[msg.agent_id],
        phase_label=label,
        stance=msg.stance,
        summary=msg.summary,
        content=msg.content,
    )


def _emit_message(ctx: DeliberationContext, msg: MessageRecord) -> None:
    ctx.emitter.emit(
        AgentMessage,
        agent_id=msg.agent_id,
        message_id=msg.message_id,
        phase=msg.phase,
        round=msg.round,
        content=msg.content,
        stance=msg.stance,
        summary=msg.summary,
        reply_to=list(msg.reply_to),
    )


def _agent_failed(ctx: DeliberationContext, persona: Persona, exc: Exception) -> None:
    ctx.emitter.emit(RunError, message=f"{persona.name}: {exc}", agent_id=persona.id, fatal=False)


def _tasks(state: DeliberationState, ctx: DeliberationContext) -> list[AgentTask]:
    return [
        AgentTask(
            agent_id=p.id,
            question=state["question"],
            round=state["round"],
            messages=list(state["messages"]),
        )
        for p in ctx.council
    ]


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #


async def begin(state: DeliberationState, *, runtime: Rt) -> dict[str, Any]:
    runtime.context.emitter.emit(PhaseStarted, phase=Phase.OPENING, round=0)
    return {"round": 0}


def fan_out_opening(state: DeliberationState, runtime: Rt) -> list[Send]:
    return [Send("opening", task) for task in _tasks(state, runtime.context)]


async def opening(state: AgentTask, *, runtime: Rt) -> dict[str, Any]:
    ctx = runtime.context
    persona = ctx.by_id[state["agent_id"]]
    ctx.emitter.emit(AgentThinking, agent_id=persona.id, phase=Phase.OPENING, round=0)
    try:
        out = await ctx.brain.opening(persona, state["question"])
    except AgentOutputError as exc:
        _agent_failed(ctx, persona, exc)
        out = OpeningOutput(
            stance=Stance.UNDECIDED,
            summary="No position: this unit failed to respond.",
            argument=f"[{persona.name} produced no usable statement.]",
        )
    msg = MessageRecord(
        message_id=message_id(persona.id, 0),
        agent_id=persona.id,
        phase=Phase.OPENING,
        round=0,
        content=out.argument,
        stance=out.stance,
        summary=out.summary,
    )
    _emit_message(ctx, msg)
    return {"messages": [msg]}


def _consensus_reached(state: DeliberationState) -> bool:
    latest = latest_by_agent(state["messages"]).values()
    stances = {m.stance for m in latest}
    no_revisions = state["round"] not in state["revision_rounds"]
    return len(stances) == 1 and Stance.UNDECIDED not in stances and no_revisions


async def debate_gate(state: DeliberationState, *, runtime: Rt) -> dict[str, Any]:
    ctx = runtime.context
    completed = state["round"]
    more_rounds = completed < ctx.config.max_rounds
    early_stop = ctx.config.early_consensus and completed >= 1 and _consensus_reached(state)
    if more_rounds and not early_stop:
        ctx.emitter.emit(PhaseStarted, phase=Phase.DEBATE, round=completed + 1)
        return {"round": completed + 1, "next_phase": "debate"}
    ctx.emitter.emit(PhaseStarted, phase=Phase.VOTE, round=None)
    return {"next_phase": "vote"}


def route_from_gate(state: DeliberationState, runtime: Rt) -> list[Send]:
    node = "debate" if state["next_phase"] == "debate" else "vote"
    return [Send(node, task) for task in _tasks(state, runtime.context)]


async def debate(state: AgentTask, *, runtime: Rt) -> dict[str, Any]:
    ctx = runtime.context
    persona = ctx.by_id[state["agent_id"]]
    round_number = state["round"]
    latest = latest_by_agent(state["messages"])
    own = latest[persona.id]
    others = [latest[p.id] for p in ctx.council if p.id != persona.id and p.id in latest]

    ctx.emitter.emit(AgentThinking, agent_id=persona.id, phase=Phase.DEBATE, round=round_number)
    try:
        out = await ctx.brain.debate(
            persona,
            state["question"],
            round_number,
            ctx.config.max_rounds,
            _entry(own, ctx),
            [_entry(m, ctx) for m in others],
        )
    except AgentOutputError as exc:
        _agent_failed(ctx, persona, exc)
        # Hold the previous position unchanged.
        msg = MessageRecord(
            message_id=message_id(persona.id, round_number),
            agent_id=persona.id,
            phase=Phase.DEBATE,
            round=round_number,
            content=f"[{persona.name} produced no usable argument; position unchanged.]",
            stance=own.stance,
            summary=own.summary,
        )
        _emit_message(ctx, msg)
        return {"messages": [msg]}

    reply_to: list[ReplyRef] = []
    for ref in out.responding_to:
        target = resolve_persona_ref(ref, ctx.council)
        if target is None or target.id == persona.id or target.id not in latest:
            continue
        reply = ReplyRef(agent_id=target.id, message_id=latest[target.id].message_id)
        if reply not in reply_to:
            reply_to.append(reply)

    msg = MessageRecord(
        message_id=message_id(persona.id, round_number),
        agent_id=persona.id,
        phase=Phase.DEBATE,
        round=round_number,
        content=out.argument,
        stance=out.stance,
        summary=out.summary,
        reply_to=tuple(reply_to),
    )
    _emit_message(ctx, msg)

    revised = out.stance is not own.stance or out.revised
    if revised:
        ctx.emitter.emit(
            AgentRevisedPosition,
            agent_id=persona.id,
            message_id=msg.message_id,
            round=round_number,
            previous_stance=own.stance,
            new_stance=out.stance,
            previous_summary=own.summary,
            new_summary=out.summary,
            reason=out.revision_reason.strip() or "Position shifted during debate.",
        )
    return {"messages": [msg], "revision_rounds": [round_number] if revised else []}


async def cast_vote(state: AgentTask, *, runtime: Rt) -> dict[str, Any]:
    ctx = runtime.context
    persona = ctx.by_id[state["agent_id"]]
    latest = latest_by_agent(state["messages"])
    own = latest[persona.id]
    others = [latest[p.id] for p in ctx.council if p.id != persona.id and p.id in latest]

    ctx.emitter.emit(AgentThinking, agent_id=persona.id, phase=Phase.VOTE, round=None)
    try:
        out = await ctx.brain.vote(
            persona, state["question"], _entry(own, ctx), [_entry(m, ctx) for m in others]
        )
        ballot = Ballot(persona.id, out.vote, out.confidence, out.rationale)
    except AgentOutputError as exc:
        _agent_failed(ctx, persona, exc)
        ballot = Ballot(persona.id, VoteChoice.ABSTAIN, 0.0, "No valid vote; recorded as abstain.")

    ctx.emitter.emit(
        VoteCast,
        agent_id=persona.id,
        vote=ballot.vote,
        confidence=ballot.confidence,
        rationale=ballot.rationale,
    )
    return {"ballots": [ballot]}


async def tally(state: DeliberationState, *, runtime: Rt) -> dict[str, Any]:
    ctx = runtime.context
    decision = decide(ctx.config.verdict_rule, state["ballots"], electorate=len(ctx.council))
    ctx.emitter.emit(PhaseStarted, phase=Phase.VERDICT, round=None)
    return {"decision": decision}


async def synthesize(state: DeliberationState, *, runtime: Rt) -> dict[str, Any]:
    ctx = runtime.context
    decision = state["decision"]
    assert decision is not None, "tally must run before synthesize"
    t = decision.tally
    tally_text = f"{t.approve} approve, {t.deny} deny, {t.abstain} abstain"
    order = {p.id: i for i, p in enumerate(ctx.council)}
    ballots = sorted(state["ballots"], key=lambda b: order[b.agent_id])
    records = {m.message_id: m for m in state["messages"]}

    try:
        out = await ctx.brain.synthesize(
            state["question"],
            ctx.config.verdict_rule,
            decision.outcome.value,
            tally_text,
            [_entry(m, ctx) for m in state["messages"]],
            [VoteEntry(ctx.by_id[b.agent_id], b.vote, b.confidence, b.rationale) for b in ballots],
        )
        summary = out.summary
        decisive: list[DecisiveArgument] = []
        for cited in out.decisive_arguments:
            record = records.get(cited.message_id.strip().strip("[]"))
            if record is not None and all(d.message_id != record.message_id for d in decisive):
                decisive.append(
                    DecisiveArgument(
                        agent_id=record.agent_id,
                        message_id=record.message_id,
                        reason=cited.reason,
                    )
                )
    except AgentOutputError as exc:
        ctx.emitter.emit(RunError, message=f"Arbiter: {exc}", agent_id=None, fatal=False)
        summary = (
            f"The council reached {decision.outcome.value} ({tally_text}) under the "
            f"{ctx.config.verdict_rule.value} rule. No written synthesis is available."
        )
        decisive = [
            DecisiveArgument(agent_id=b.agent_id, message_id=None, reason=b.rationale)
            for b in ballots
        ]

    ctx.emitter.emit(
        Verdict,
        rule=ctx.config.verdict_rule,
        outcome=decision.outcome,
        tally=decision.tally,
        confidence=decision.confidence,
        summary=summary,
        decisive_arguments=decisive[:3],
    )
    return {}


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #


def build_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(DeliberationState, context_schema=DeliberationContext)
    graph.add_node("begin", begin)
    graph.add_node("opening", opening, input_schema=AgentTask)
    graph.add_node("debate_gate", debate_gate)
    graph.add_node("debate", debate, input_schema=AgentTask)
    graph.add_node("vote", cast_vote, input_schema=AgentTask)
    graph.add_node("tally", tally)
    graph.add_node("synthesize", synthesize)

    graph.add_edge(START, "begin")
    graph.add_conditional_edges("begin", fan_out_opening, ["opening"])
    graph.add_edge("opening", "debate_gate")
    graph.add_conditional_edges("debate_gate", route_from_gate, ["debate", "vote"])
    graph.add_edge("debate", "debate_gate")
    graph.add_edge("vote", "tally")
    graph.add_edge("tally", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile(name="magi-deliberation")


_GRAPH: CompiledStateGraph[Any, Any, Any, Any] | None = None


def get_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


async def run_deliberation(question: str, ctx: DeliberationContext) -> DeliberationState:
    initial: DeliberationState = {
        "question": question,
        "round": 0,
        "next_phase": "debate",
        "messages": [],
        "ballots": [],
        "revision_rounds": [],
        "decision": None,
    }
    result = await get_graph().ainvoke(initial, context=ctx, config={"recursion_limit": 100})
    return cast(DeliberationState, result)
