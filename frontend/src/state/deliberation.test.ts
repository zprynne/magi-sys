import { describe, expect, it } from 'vitest'
import drones from '../../../traces/example-delivery-drones.jsonl?raw'
import triage from '../../../traces/example-er-triage.jsonl?raw'
import { parseJsonl, type MagiEvent } from '../types/events'
import { applyEvent, deriveView, initialView, phaseSteps } from './deliberation'

const dronesEvents = parseJsonl(drones)
const triageEvents = parseJsonl(triage)

function upTo(events: MagiEvent[], predicate: (e: MagiEvent) => boolean): MagiEvent[] {
  const index = events.findIndex(predicate)
  if (index < 0) throw new Error('event not found')
  return events.slice(0, index + 1)
}

describe('deriveView on a full trace', () => {
  const view = deriveView(dronesEvents)

  it('ends with the verdict and every agent voted', () => {
    expect(view.verdict?.outcome).toBe('APPROVED')
    expect(view.completed?.status).toBe('completed')
    expect(Object.values(view.byAgent).map((a) => a.status)).toEqual(['voted', 'voted', 'voted'])
    expect(view.votes).toHaveLength(3)
  })

  it('tracks messages, rounds and revisions', () => {
    expect(view.messages).toHaveLength(9)
    expect(view.roundsRun).toBe(2)
    expect(view.byAgent.caspar?.revisionCount).toBe(1)
    expect(view.byAgent.caspar?.stance).toBe('APPROVE')
  })

  it('handles an abstention under the unanimous rule', () => {
    const t = deriveView(triageEvents)
    expect(t.config?.verdict_rule).toBe('unanimous')
    expect(t.verdict?.outcome).toBe('DENIED')
    expect(t.byAgent.melchior?.vote?.vote).toBe('ABSTAIN')
  })
})

describe('agent status transitions', () => {
  it('goes idle -> thinking -> speaking -> idle at the next phase', () => {
    const thinking = deriveView(upTo(dronesEvents, (e) => e.type === 'agent_thinking'))
    expect(thinking.byAgent.melchior?.status).toBe('thinking')

    const firstMessage = dronesEvents.find((e) => e.type === 'agent_message')
    if (firstMessage?.type !== 'agent_message') throw new Error('no message')
    const speaking = deriveView(upTo(dronesEvents, (e) => e.seq === firstMessage.seq))
    expect(speaking.byAgent[firstMessage.agent_id]?.status).toBe('speaking')
    expect(speaking.byAgent[firstMessage.agent_id]?.summary).toBe(firstMessage.summary)

    const nextPhase = deriveView(
      upTo(dronesEvents, (e) => e.type === 'phase_started' && e.phase === 'debate'),
    )
    expect(Object.values(nextPhase.byAgent).every((a) => a.status === 'idle')).toBe(true)
  })

  it('lights replies for the current phase only', () => {
    const roundOne = deriveView(
      upTo(dronesEvents, (e) => e.type === 'agent_message' && e.message_id === 'balthasar-r1'),
    )
    expect(roundOne.replies.map((r) => `${r.from}>${r.to}`)).toContain('balthasar>melchior')

    const roundTwoStart = deriveView(
      upTo(dronesEvents, (e) => e.type === 'phase_started' && e.round === 2),
    )
    expect(roundTwoStart.replies).toEqual([])
  })

  it('marks a revision on the agent until the next phase', () => {
    const revised = deriveView(upTo(dronesEvents, (e) => e.type === 'agent_revised_position'))
    expect(revised.byAgent.caspar?.revised).toBe(true)
  })
})

describe('applyEvent', () => {
  it('ignores events it has already applied (SSE reconnects)', () => {
    const view = deriveView(dronesEvents.slice(0, 10))
    const again = applyEvent(view, dronesEvents[5] as MagiEvent)
    expect(again).toBe(view)
  })

  it('records fatal errors and agent faults', () => {
    const base = deriveView(dronesEvents.slice(0, 1))
    const fault = applyEvent(base, {
      type: 'run_error',
      run_id: base.runId ?? '',
      seq: 2,
      timestamp: '2026-10-06T14:02:12Z',
      message: 'CASPAR-3: declined',
      agent_id: 'caspar',
      fatal: false,
    })
    expect(fault.byAgent.caspar?.error).toBe('CASPAR-3: declined')
    expect(fault.fatal).toBeNull()

    const fatal = applyEvent(fault, {
      type: 'run_error',
      run_id: base.runId ?? '',
      seq: 3,
      timestamp: '2026-10-06T14:02:13Z',
      message: 'AuthenticationError',
      agent_id: null,
      fatal: true,
    })
    expect(fatal.fatal?.message).toBe('AuthenticationError')
    expect(fatal.errors).toHaveLength(2)
  })

  it('starts from the configured council before run_started arrives', () => {
    const agents = deriveView(dronesEvents).agents
    const idle = initialView(agents)
    expect(Object.keys(idle.byAgent)).toEqual(['melchior', 'balthasar', 'caspar'])
    expect(idle.phase).toBeNull()
  })
})

describe('phaseSteps', () => {
  it('lists opening, each round, vote and verdict', () => {
    expect(phaseSteps(2).map((s) => s.label)).toEqual(['Opening', 'Round 1', 'Round 2', 'Vote', 'Verdict'])
    expect(phaseSteps(0).map((s) => s.key)).toEqual(['opening', 'vote', 'verdict'])
  })
})

describe('parseJsonl', () => {
  it('rejects lines that are not MAGI events', () => {
    expect(() => parseJsonl('{"hello": "world"}\n')).toThrow(/line 1/)
  })

  it('sorts by sequence number', () => {
    const shuffled = [...drones.trim().split('\n')].reverse().join('\n')
    expect(parseJsonl(shuffled).map((e) => e.seq)).toEqual(dronesEvents.map((e) => e.seq))
  })
})
