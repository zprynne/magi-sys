"""Build the bundled example traces in ``traces/example-*.jsonl``.

The deliberations below are hand-written. This script only handles the
bookkeeping: it validates every event against the schema, numbers them, and
lays them out on a realistic timeline (parallel agents finish at different
times, debate turns take longer than votes, and so on).

    cd backend && uv run python scripts/build_example_traces.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from magi.events import (
    AgentInfo,
    AgentMessage,
    AgentRevisedPosition,
    AgentThinking,
    DecisiveArgument,
    EventBase,
    Outcome,
    Phase,
    PhaseStarted,
    ReplyRef,
    RunCompleted,
    RunConfig,
    RunStarted,
    RunStatus,
    Stance,
    Verdict,
    VerdictRule,
    VoteCast,
    VoteChoice,
    dump_event,
)
from magi.paths import DEFAULT_PERSONAS_DIR, DEFAULT_TRACES_DIR
from magi.personas import load_personas
from magi.voting import Ballot, decide

M, B, C = "melchior", "balthasar", "caspar"


@dataclass
class Turn:
    agent_id: str
    stance: Stance
    summary: str
    content: str
    reply_to: list[str] = field(default_factory=list)  # agent ids answered
    revision_reason: str | None = None


@dataclass
class Vote:
    agent_id: str
    vote: VoteChoice
    confidence: float
    rationale: str


@dataclass
class Example:
    trace_id: str
    question: str
    rule: VerdictRule
    started: datetime
    rounds: list[list[Turn]]  # rounds[0] is the opening
    votes: list[Vote]
    summary: str
    decisive: list[tuple[str, str]]  # (message_id, reason)


class TraceBuilder:
    def __init__(self, example: Example, agents: list[AgentInfo]) -> None:
        self.ex = example
        self.agents = agents
        self.rng = random.Random(example.trace_id)
        self.t = example.started
        self.events: list[EventBase] = []

    def emit(self, cls: type[EventBase], at: datetime, **fields: Any) -> None:
        self.events.append(
            cls(run_id=self.ex.trace_id, seq=len(self.events) + 1, timestamp=at, **fields)
        )

    def step(self, seconds: float) -> datetime:
        self.t += timedelta(seconds=seconds)
        return self.t

    def parallel(self, phase: Phase, round_: int | None, lo: float, hi: float) -> list[datetime]:
        """Emit agent_thinking for everyone; return when each agent finishes."""
        start = self.t
        for i, agent in enumerate(self.agents):
            at = start + timedelta(milliseconds=40 * (i + 1))
            self.emit(AgentThinking, at, agent_id=agent.id, phase=phase, round=round_)
        return [start + timedelta(seconds=self.rng.uniform(lo, hi)) for _ in self.agents]

    def build(self) -> list[EventBase]:
        ex = self.ex
        max_rounds = len(ex.rounds) - 1
        config = RunConfig(
            max_rounds=max_rounds, verdict_rule=ex.rule, model="claude-opus-5-5", mock=False
        )
        self.emit(RunStarted, self.t, question=ex.question, agents=self.agents, config=config)

        latest: dict[str, Turn] = {}
        for round_, turns in enumerate(ex.rounds):
            phase = Phase.OPENING if round_ == 0 else Phase.DEBATE
            self.emit(PhaseStarted, self.step(0.35), phase=phase, round=round_)
            finish = self.parallel(phase, round_, 6.5, 12.5)
            order = sorted(range(len(turns)), key=lambda i: finish[i])
            for i in order:
                turn = turns[i]
                at = finish[i]
                self.emit(
                    AgentMessage,
                    at,
                    agent_id=turn.agent_id,
                    message_id=f"{turn.agent_id}-r{round_}",
                    phase=phase,
                    round=round_,
                    content=turn.content,
                    stance=turn.stance,
                    summary=turn.summary,
                    reply_to=[
                        ReplyRef(agent_id=a, message_id=f"{a}-r{round_ - 1}") for a in turn.reply_to
                    ],
                )
                previous = latest.get(turn.agent_id)
                if turn.revision_reason is not None:
                    assert previous is not None
                    self.emit(
                        AgentRevisedPosition,
                        at + timedelta(milliseconds=25),
                        agent_id=turn.agent_id,
                        message_id=f"{turn.agent_id}-r{round_}",
                        round=round_,
                        previous_stance=previous.stance,
                        new_stance=turn.stance,
                        previous_summary=previous.summary,
                        new_summary=turn.summary,
                        reason=turn.revision_reason,
                    )
            for turn in turns:
                latest[turn.agent_id] = turn
            self.t = max(finish) + timedelta(milliseconds=60)

        self.emit(PhaseStarted, self.step(0.3), phase=Phase.VOTE, round=None)
        finish = self.parallel(Phase.VOTE, None, 2.8, 5.2)
        for i in sorted(range(len(ex.votes)), key=lambda i: finish[i]):
            v = ex.votes[i]
            self.emit(
                VoteCast,
                finish[i],
                agent_id=v.agent_id,
                vote=v.vote,
                confidence=v.confidence,
                rationale=v.rationale,
            )
        self.t = max(finish)

        decision = decide(
            ex.rule,
            [Ballot(v.agent_id, v.vote, v.confidence, v.rationale) for v in ex.votes],
            electorate=len(self.agents),
        )
        self.emit(PhaseStarted, self.step(0.2), phase=Phase.VERDICT, round=None)
        self.emit(
            Verdict,
            self.step(self.rng.uniform(8.0, 11.0)),
            rule=ex.rule,
            outcome=decision.outcome,
            tally=decision.tally,
            confidence=decision.confidence,
            summary=ex.summary,
            decisive_arguments=[
                DecisiveArgument(agent_id=mid.rsplit("-r", 1)[0], message_id=mid, reason=reason)
                for mid, reason in ex.decisive
            ],
        )
        duration = int((self.t - ex.started).total_seconds() * 1000) + 80
        self.emit(RunCompleted, self.step(0.08), status=RunStatus.COMPLETED, duration_ms=duration)
        return self.events


# --------------------------------------------------------------------------- #
# Example 1: delivery drones (majority rule, approved 2-1)
# --------------------------------------------------------------------------- #

DRONES = Example(
    trace_id="example-delivery-drones",
    question=(
        "Should our city allow autonomous delivery drones to fly over residential "
        "neighborhoods starting next spring?"
    ),
    rule=VerdictRule.MAJORITY,
    started=datetime.fromisoformat("2026-10-06T14:02:11.204+00:00"),
    rounds=[
        [
            Turn(
                M,
                Stance.APPROVE,
                "Pilot data shows drones cut last-mile emissions and delivery times at incident "
                "rates low enough to justify rollout.",
                "The evidence favors approval. Published pilot programs have logged millions of "
                "residential drone deliveries with no fatalities and a reportable-incident rate on "
                "the order of one per 100,000 flights, most of them hardware faults that ended in "
                "controlled landings. A delivery drone uses roughly a tenth of the energy per "
                "parcel of a van on the last mile, and median delivery time drops from hours to "
                "under twenty minutes. The open questions are noise and privacy, and both are "
                "measurable: we can set a decibel ceiling and audit camera retention. I see no "
                "technical reason to block this, and good reasons to instrument it carefully.",
            ),
            Turn(
                B,
                Stance.DENY,
                "Residents would bear crash, noise and surveillance risks they never agreed to, "
                "and the safeguards are promises, not mechanisms.",
                "The people under these flight paths did not choose this risk. A low incident "
                "rate across millions of flights still means falling hardware over backyards, "
                "schoolyards and playgrounds at city scale, and the pilots ran in selected, "
                "low-density areas under heavy supervision. Every drone carries cameras that will "
                "pass over private spaces. The operators promise geofencing, noise limits and data "
                "minimization, but none of it is enforceable today: there is no inspection "
                "regime, no incident reporting requirement, and no way for a resident to opt out. "
                "I would consider approval once those exist. Not before.",
            ),
            Turn(
                C,
                Stance.UNDECIDED,
                "Fast deliveries matter to people with limited mobility, but residents should "
                "decide what flies over their homes.",
                "Think about who this actually serves. For an elderly man who no longer drives, a "
                "twenty-minute prescription delivery is independence, not convenience. For a "
                "parent working nights, it is an hour of sleep. Those are real goods. But a "
                "neighborhood is also a place people chose for its quiet, and a steady whine "
                "overhead changes what home feels like. Nobody has asked the residents. I could "
                "support this if neighborhoods had a genuine say, street by street, rather than "
                "having the sky above them allocated by a council vote.",
            ),
        ],
        [
            Turn(
                M,
                Stance.APPROVE,
                "Even pessimistic incident estimates beat the van traffic drones replace; "
                "surveillance is solvable by technical mandate.",
                "BALTHASAR-2 is right that the pilot zones were selected, so let me adjust the "
                "estimate rather than dismiss the point. Even if urban incident rates ran five "
                "times the pilot figures, expected injuries per million deliveries would stay "
                "below those of the delivery vans the drones replace, which injure pedestrians at "
                "a measurable rate every year. The surveillance concern is real but addressable "
                "with a hardware requirement: downward cameras limited to navigation resolution, "
                "processed on-device, nothing retained. I accept that enforcement must exist "
                "before launch. That is an argument for conditions, not for denial.",
                reply_to=[B],
            ),
            Turn(
                B,
                Stance.DENY,
                "Averages hide who bears the risk; without enforcement, an incident registry and "
                "an opt-out, the answer remains no.",
                "MELCHIOR-1 compares drone injuries with van injuries as if the risks fell on the "
                "same people. They do not. Van risk is concentrated on roads that people knowingly "
                "use; drone risk is spread over gardens and rooftops where people expect to be "
                "safe. A comparison of averages hides who pays. CASPAR-3's instinct is the right "
                "one: consent matters. But consent street by street is not yet a mechanism either. "
                "Until the city can show me an enforcement office, a public incident registry and "
                "a binding opt-out, I stand with the people who would live under the flight paths.",
                reply_to=[M, C],
            ),
            Turn(
                C,
                Stance.APPROVE,
                "Approve a phased, opt-in rollout with enforceable camera limits; the people who "
                "need deliveries deserve a say too.",
                "MELCHIOR-1's point about cameras moved me: if the hardware physically cannot keep "
                "images, my biggest fear about this goes away. And BALTHASAR-2's conditions are "
                "good ones, but notice that they are all things the city can build during a "
                "phased rollout rather than before it. I would rather start with the neighborhoods "
                "that ask for it, with a real opt-out for the rest, than keep the people who need "
                "this waiting for a perfect regime. Autonomy cuts both ways: the man who needs his "
                "prescriptions gets a say too.",
                reply_to=[M, B],
                revision_reason=(
                    "Hardware camera limits and an opt-in rollout answer my consent concern."
                ),
            ),
        ],
        [
            Turn(
                M,
                Stance.APPROVE,
                "A phased opt-in rollout with monthly public incident data is safe enough and the "
                "best way to learn.",
                "CASPAR-3's phased design is also the better experiment. Opt-in neighborhoods give "
                "us a natural comparison group for noise complaints, incident rates and delivery "
                "outcomes, so the city learns from its own evidence instead of operator claims. I "
                "would add one requirement: publish incident data monthly, so that BALTHASAR-2's "
                "registry exists from day one. Under those conditions the expected benefit is "
                "clearly positive and the downside is bounded and observable.",
                reply_to=[C],
            ),
            Turn(
                B,
                Stance.DENY,
                "An opt-in pilot would be acceptable; the broad proposition as written is not.",
                "I acknowledge that the opt-in design is far better than what was proposed. If the "
                "question were a supervised, opt-in pilot with published incident data, I would "
                "lean toward approval. But the proposition as written is to allow drones over "
                "residential neighborhoods next spring, not to pilot them in volunteer districts. "
                "I will not approve the broad version on the strength of conditions that are not "
                "part of it. My position holds.",
                reply_to=[C, M],
            ),
            Turn(
                C,
                Stance.APPROVE,
                "Approve, with the conditions attached; shaping the rollout beats blocking it.",
                "BALTHASAR-2 is right that the wording matters, and I hope our verdict carries the "
                "conditions with it. But a no leaves the people who need this with nothing, while "
                "a yes with clear conditions lets the city build the version all three of us could "
                "live with. I would rather shape this than stop it.",
                reply_to=[B],
            ),
        ],
    ],
    votes=[
        Vote(
            M,
            VoteChoice.APPROVE,
            0.84,
            "Expected benefits are large and measurable, and the risks stay bounded if incident "
            "data is public from launch.",
        ),
        Vote(
            B,
            VoteChoice.DENY,
            0.71,
            "As written, the proposition exposes residents to risk without enforceable safeguards "
            "or a binding opt-out.",
        ),
        Vote(
            C,
            VoteChoice.APPROVE,
            0.66,
            "People who depend on fast deliveries deserve them, provided neighborhoods can opt out "
            "and cameras cannot keep images.",
        ),
    ],
    summary=(
        "The council APPROVED the proposition 2-1 under the majority rule, on narrower terms than "
        "its wording. MELCHIOR-1 established that even pessimistic incident estimates compare "
        "favorably with the van traffic the drones would replace, and proposed hardware limits "
        "that keep cameras from retaining images [melchior-r1]. That proposal moved CASPAR-3 from "
        "undecided to supporting a phased, opt-in rollout [caspar-r1]. BALTHASAR-2 dissented on "
        "the proposition as written [balthasar-r2]: the conditions that made approval acceptable "
        "(an enforcement office, a public incident registry and a binding opt-out) are not part "
        "of it. Read this verdict as approval of the phased, opt-in design with monthly public "
        "incident reporting."
    ),
    decisive=[
        (
            "melchior-r1",
            "Reframed the risk comparison and offered an enforceable fix for surveillance.",
        ),
        ("caspar-r1", "The swing vote: a phased, opt-in rollout resolved the consent problem."),
        ("balthasar-r2", "Defined the conditions any approval has to carry."),
    ],
)

# --------------------------------------------------------------------------- #
# Example 2: AI triage (unanimous rule, denied)
# --------------------------------------------------------------------------- #

TRIAGE = Example(
    trace_id="example-er-triage",
    question=(
        "Should hospitals let an AI system make final triage decisions in emergency rooms "
        "during mass-casualty events?"
    ),
    rule=VerdictRule.UNANIMOUS,
    started=datetime.fromisoformat("2026-10-06T16:47:39.518+00:00"),
    rounds=[
        [
            Turn(
                M,
                Stance.APPROVE,
                "In surge conditions, validated triage models outperform exhausted clinicians on "
                "both accuracy and speed.",
                "Mass-casualty triage is exactly where human performance degrades: under a minute "
                "per patient, with fatigue, noise and incomplete information. Retrospective "
                "studies of triage algorithms report under-triage rates well below those of "
                "clinicians working surge shifts, and a model does not slow down at hour fourteen. "
                "The relevant comparison is not AI against an ideal doctor; it is AI against a "
                "doctor who has been triaging for twelve hours. On that comparison, the evidence "
                "favors letting the validated system decide.",
            ),
            Turn(
                B,
                Stance.DENY,
                "A final, unreviewable machine decision over who gets treated is a single point "
                "of failure at the worst possible moment.",
                "Mass-casualty events are exactly when systems fail in ways nobody tested: power "
                "loss, unfamiliar injury patterns, a chemical exposure the training data never "
                "saw. A model that is right ninety-five percent of the time is wrong for one "
                "patient in twenty, and the word final removes the clinician who might have caught "
                "it. There is also no one to answer to: a family cannot appeal to an algorithm. "
                "Decision support, yes. Final authority, no.",
            ),
            Turn(
                C,
                Stance.DENY,
                "Being sorted for care by a machine, with no human to plead with, strips patients "
                "of dignity when they most need it.",
                "Imagine being the person on the stretcher, or the mother beside it, and learning "
                "that no human being decided your child should wait. Triage is already brutal; "
                "what makes it bearable is that someone looked at you and made a judgment they "
                "will carry. Speed matters, and I don't romanticize exhausted doctors. But final "
                "means no one can be persuaded, and no one is there to notice the thing the chart "
                "missed. Help the doctors decide faster. Don't decide for them.",
            ),
        ],
        [
            Turn(
                M,
                Stance.UNDECIDED,
                "Out-of-distribution risk undercuts the accuracy evidence; I cannot defend final "
                "authority without surge-specific validation.",
                "BALTHASAR-2's distribution-shift point is correct, and I underweighted it. Triage "
                "models are validated on historical cases, and mass-casualty events are by "
                "definition out of distribution: blast injuries, chemical exposures, pediatric "
                "surges. My accuracy figures come from conditions that will not hold. I still "
                "think the model belongs in the loop, but I can no longer defend final authority "
                "on the evidence. What I would need is validation on simulated surge scenarios, "
                "and we do not have it.",
                reply_to=[B],
                revision_reason=(
                    "Mass-casualty events are out of distribution for models validated on routine "
                    "cases."
                ),
            ),
            Turn(
                B,
                Stance.DENY,
                "AI should assist triage, but every final call needs a human who can catch the "
                "model's errors.",
                "MELCHIOR-1's comparison with an exhausted clinician is fair, and it is why I "
                "support AI assistance in triage. But the question is about final decisions, and a "
                "final decision needs a failure mode we can survive. With a clinician confirming, "
                "a model error costs seconds. Without one, it can cost a life, silently. Keep a "
                "human signature on every call.",
                reply_to=[M],
            ),
            Turn(
                C,
                Stance.DENY,
                "Use AI to help exhausted clinicians decide faster, not to decide for them.",
                "I'm glad MELCHIOR-1 named the exhausted doctor at hour fourteen, because that "
                "person deserves help, not replacement. Give them a model that pre-sorts patients "
                "and flags the ones it is unsure about, and they get faster without anyone being "
                "sorted by a machine alone. That is the version patients would choose if anyone "
                "asked them.",
                reply_to=[M],
            ),
        ],
        [
            Turn(
                M,
                Stance.UNDECIDED,
                "Model-assisted triage with uncertainty flags is supported; final authority is "
                "unproven, not disproven.",
                "CASPAR-3's flagging design is what the evidence actually supports: let the model "
                "rank patients and surface its own uncertainty, and route those cases to a "
                "clinician first. That keeps most of the speed benefit while putting a human check "
                "on exactly the out-of-distribution cases where I expect the model to fail. On the "
                "proposition as stated, final machine authority, I do not have the data to say "
                "yes, and I do not think the data rules it out forever.",
                reply_to=[C],
            ),
            Turn(
                B,
                Stance.DENY,
                "Final authority is unproven, and with lives at stake the burden of proof has not "
                "been met.",
                "Then we agree on the design and differ only on the word final. Unproven is enough "
                "for me. When the cost of being wrong is a preventable death, the burden of proof "
                "is on the system, and it has not met it.",
                reply_to=[M],
            ),
            Turn(
                C,
                Stance.DENY,
                "All three of us support AI assistance; none of us can support AI having the "
                "final word.",
                "We have found something all three of us could support: a model that helps "
                "clinicians see faster and admits when it is unsure. That is worth building. It "
                "just isn't what we were asked.",
                reply_to=[B, M],
            ),
        ],
    ],
    votes=[
        Vote(
            M,
            VoteChoice.ABSTAIN,
            0.52,
            "Final machine triage is unproven in surge conditions but not ruled out; the evidence "
            "supports neither yes nor no.",
        ),
        Vote(
            B,
            VoteChoice.DENY,
            0.9,
            "No system should hold final, unreviewable authority over who receives care while its "
            "failure modes are untested.",
        ),
        Vote(
            C,
            VoteChoice.DENY,
            0.86,
            "Patients deserve a human being who can be reached and persuaded at the moment of "
            "triage.",
        ),
    ],
    summary=(
        "The council DENIED the proposition. Under the unanimous rule it needed three approvals "
        "and received none: two votes to deny and one abstention. The turning point was "
        "BALTHASAR-2's argument that mass-casualty events are where untested failure modes "
        "appear [balthasar-r0], which led MELCHIOR-1 to withdraw support because the accuracy "
        "evidence comes from routine cases, not surges [melchior-r1]. CASPAR-3 then described "
        "the design all three members endorsed in debate [caspar-r1]: AI that pre-sorts patients "
        "and flags its own uncertainty, with a clinician making the final call. The council "
        "rejects final machine authority, not AI in triage."
    ),
    decisive=[
        ("balthasar-r0", "Named the failure mode: surges are exactly where models go untested."),
        ("melchior-r1", "The strongest advocate withdrew support on the evidence."),
        ("caspar-r1", "Offered the assistive design the whole council could endorse."),
    ],
)


def main() -> None:
    agents = [p.info(model="claude-opus-5-5") for p in load_personas(DEFAULT_PERSONAS_DIR)]
    DEFAULT_TRACES_DIR.mkdir(parents=True, exist_ok=True)
    for example in (DRONES, TRIAGE):
        events = TraceBuilder(example, agents).build()
        path = DEFAULT_TRACES_DIR / f"{example.trace_id}.jsonl"
        path.write_text(
            "".join(dump_event(e) + "\n" for e in events), encoding="utf-8", newline="\n"
        )
        verdict = next(e for e in events if isinstance(e, Verdict))
        assert verdict.outcome in (Outcome.APPROVED, Outcome.DENIED)
        print(f"wrote {path.name}: {len(events)} events, {verdict.outcome.value}")


if __name__ == "__main__":
    main()
