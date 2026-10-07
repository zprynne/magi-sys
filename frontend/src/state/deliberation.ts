/**
 * Pure fold from the event stream to everything the console renders.
 *
 * The live view applies events as they arrive over SSE; the replay view
 * derives the state for any prefix of a saved trace. Both use `deriveView`,
 * so a replayed run looks exactly like it did live.
 */
import type {
  AgentInfo,
  AgentMessage,
  MagiEvent,
  Phase,
  RunCompleted,
  RunConfig,
  RunError,
  Stance,
  Verdict,
  VoteCast,
} from '../types/events'

export type AgentStatus = 'idle' | 'thinking' | 'speaking' | 'voted'

export interface AgentView {
  info: AgentInfo
  status: AgentStatus
  stance: Stance | null
  summary: string | null
  lastMessage: AgentMessage | null
  /** Changed position during the current phase. */
  revised: boolean
  revisionCount: number
  vote: VoteCast | null
  error: string | null
}

/** One agent answering another: drives the lit conduits in the graph. */
export interface Reply {
  key: string
  seq: number
  from: string
  to: string
}

export interface DeliberationView {
  runId: string | null
  question: string | null
  config: RunConfig | null
  agents: AgentInfo[]
  byAgent: Record<string, AgentView>
  phase: Phase | null
  round: number | null
  /** Highest debate round that started. */
  roundsRun: number
  replies: Reply[]
  messages: AgentMessage[]
  votes: VoteCast[]
  verdict: Verdict | null
  errors: RunError[]
  fatal: RunError | null
  completed: RunCompleted | null
  startedAt: string | null
  lastEventAt: string | null
  lastSeq: number
}

function agentView(info: AgentInfo): AgentView {
  return {
    info,
    status: 'idle',
    stance: null,
    summary: null,
    lastMessage: null,
    revised: false,
    revisionCount: 0,
    vote: null,
    error: null,
  }
}

export function initialView(agents: AgentInfo[] = []): DeliberationView {
  return {
    runId: null,
    question: null,
    config: null,
    agents,
    byAgent: Object.fromEntries(agents.map((a) => [a.id, agentView(a)])),
    phase: null,
    round: null,
    roundsRun: 0,
    replies: [],
    messages: [],
    votes: [],
    verdict: null,
    errors: [],
    fatal: null,
    completed: null,
    startedAt: null,
    lastEventAt: null,
    lastSeq: 0,
  }
}

function updateAgent(
  view: DeliberationView,
  agentId: string,
  patch: (agent: AgentView) => Partial<AgentView>,
): Record<string, AgentView> {
  const current = view.byAgent[agentId] as AgentView | undefined
  if (!current) return view.byAgent
  return { ...view.byAgent, [agentId]: { ...current, ...patch(current) } }
}

export function applyEvent(view: DeliberationView, event: MagiEvent): DeliberationView {
  if (event.seq <= view.lastSeq) return view // duplicate (e.g. SSE reconnect)
  const base = { ...view, lastSeq: event.seq, lastEventAt: event.timestamp }

  switch (event.type) {
    case 'run_started':
      return {
        ...initialView(event.agents),
        runId: event.run_id,
        question: event.question,
        config: event.config,
        startedAt: event.timestamp,
        lastEventAt: event.timestamp,
        lastSeq: event.seq,
      }

    case 'phase_started': {
      const byAgent = Object.fromEntries(
        Object.entries(view.byAgent).map(([id, agent]) => [
          id,
          { ...agent, status: agent.status === 'voted' ? 'voted' : 'idle', revised: false },
        ]),
      ) as Record<string, AgentView>
      return {
        ...base,
        byAgent,
        phase: event.phase,
        round: event.round,
        roundsRun: event.phase === 'debate' ? Math.max(view.roundsRun, event.round ?? 0) : view.roundsRun,
        replies: [],
      }
    }

    case 'agent_thinking':
      return { ...base, byAgent: updateAgent(view, event.agent_id, () => ({ status: 'thinking' })) }

    case 'agent_message': {
      const replies = event.reply_to.map((ref) => ({
        key: `${event.seq}:${event.agent_id}>${ref.agent_id}`,
        seq: event.seq,
        from: event.agent_id,
        to: ref.agent_id,
      }))
      return {
        ...base,
        messages: [...view.messages, event],
        replies: [...view.replies, ...replies],
        byAgent: updateAgent(view, event.agent_id, () => ({
          status: 'speaking',
          stance: event.stance,
          summary: event.summary,
          lastMessage: event,
        })),
      }
    }

    case 'agent_revised_position':
      return {
        ...base,
        byAgent: updateAgent(view, event.agent_id, (agent) => ({
          revised: true,
          revisionCount: agent.revisionCount + 1,
          stance: event.new_stance,
          summary: event.new_summary,
        })),
      }

    case 'vote_cast':
      return {
        ...base,
        votes: [...view.votes, event],
        byAgent: updateAgent(view, event.agent_id, () => ({ status: 'voted', vote: event })),
      }

    case 'verdict':
      return { ...base, verdict: event }

    case 'run_error':
      return {
        ...base,
        errors: [...view.errors, event],
        fatal: event.fatal ? event : view.fatal,
        byAgent: event.agent_id
          ? updateAgent(view, event.agent_id, () => ({ error: event.message }))
          : view.byAgent,
      }

    case 'run_completed':
      return {
        ...base,
        completed: event,
        byAgent: Object.fromEntries(
          Object.entries(view.byAgent).map(([id, agent]) => [
            id,
            agent.status === 'thinking' ? { ...agent, status: 'idle' } : agent,
          ]),
        ),
      }
  }
}

export function deriveView(events: readonly MagiEvent[], agents: AgentInfo[] = []): DeliberationView {
  return events.reduce(applyEvent, initialView(agents))
}

export function isRunning(view: DeliberationView): boolean {
  return view.runId !== null && view.completed === null
}

/** Ordered list of phase steps for the phase track, e.g. opening, round 1..N, vote, verdict. */
export interface PhaseStep {
  key: string
  label: string
  phase: Phase
  round: number | null
}

export function phaseSteps(maxRounds: number): PhaseStep[] {
  return [
    { key: 'opening', label: 'Opening', phase: 'opening', round: 0 },
    ...Array.from({ length: maxRounds }, (_, i) => ({
      key: `debate-${i + 1}`,
      label: `Round ${i + 1}`,
      phase: 'debate' as const,
      round: i + 1,
    })),
    { key: 'vote', label: 'Vote', phase: 'vote', round: null },
    { key: 'verdict', label: 'Verdict', phase: 'verdict', round: null },
  ]
}

export function currentStepKey(view: DeliberationView): string | null {
  if (view.phase === null) return null
  if (view.phase === 'debate') return `debate-${view.round ?? 1}`
  return view.phase
}
