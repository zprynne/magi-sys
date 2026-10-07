import type { MagiEvent } from './events.generated'

export type * from './events.generated'

export type EventType = MagiEvent['type']
export type EventOf<T extends EventType> = Extract<MagiEvent, { type: T }>

const EVENT_TYPES: ReadonlySet<string> = new Set<EventType>([
  'run_started',
  'phase_started',
  'agent_thinking',
  'agent_message',
  'agent_revised_position',
  'vote_cast',
  'verdict',
  'run_error',
  'run_completed',
])

/** Minimal runtime guard for events arriving over the wire or from a file. */
export function isMagiEvent(value: unknown): value is MagiEvent {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.type === 'string' &&
    EVENT_TYPES.has(v.type) &&
    typeof v.run_id === 'string' &&
    typeof v.seq === 'number' &&
    typeof v.timestamp === 'string'
  )
}

export function parseJsonl(text: string): MagiEvent[] {
  const events: MagiEvent[] = []
  text.split('\n').forEach((line, index) => {
    if (!line.trim()) return
    const parsed: unknown = JSON.parse(line)
    if (!isMagiEvent(parsed)) throw new Error(`line ${index + 1} is not a MAGI event`)
    events.push(parsed)
  })
  return events.sort((a, b) => a.seq - b.seq)
}
