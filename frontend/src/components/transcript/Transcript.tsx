import { useEffect, useMemo, useRef, useState } from 'react'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import type { DeliberationView } from '../../state/deliberation'
import type { AgentInfo, MagiEvent } from '../../types/events'
import { entryAnchor } from './anchors'
import { TranscriptEntry } from './TranscriptEntry'

/** Which part of the deliberation to show. */
type RoundFilter = 'all' | 'vote' | number

type Displayed = Extract<
  MagiEvent,
  { type: 'phase_started' | 'agent_message' | 'agent_revised_position' | 'vote_cast' | 'verdict' | 'run_error' }
>

function isDisplayed(event: MagiEvent): event is Displayed {
  return (
    event.type === 'phase_started' ||
    event.type === 'agent_message' ||
    event.type === 'agent_revised_position' ||
    event.type === 'vote_cast' ||
    event.type === 'verdict' ||
    event.type === 'run_error'
  )
}

function roundOf(event: Displayed): RoundFilter {
  switch (event.type) {
    case 'agent_message':
    case 'agent_revised_position':
      return event.round
    case 'vote_cast':
    case 'verdict':
      return 'vote'
    case 'phase_started':
      return event.phase === 'vote' || event.phase === 'verdict' ? 'vote' : (event.round ?? 0)
    case 'run_error':
      return 'all'
  }
}

function agentOf(event: Displayed): string | null {
  return 'agent_id' in event ? event.agent_id : null
}

interface Props {
  events: readonly MagiEvent[]
  view: DeliberationView
}

export function Transcript({ events, view }: Props) {
  const [hiddenAgents, setHiddenAgents] = useState<ReadonlySet<string>>(new Set())
  const [round, setRound] = useState<RoundFilter>('all')
  const [jump, setJump] = useState<{ messageId: string } | null>(null)
  const reducedMotion = usePrefersReducedMotion()
  const scroller = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  const entries = useMemo(() => events.filter(isDisplayed), [events])
  const visible = useMemo(
    () =>
      entries.filter((event) => {
        const agent = agentOf(event)
        if (agent && hiddenAgents.has(agent)) return false
        if (event.type === 'phase_started' && (hiddenAgents.size > 0 || round !== 'all')) return false
        const r = roundOf(event)
        return round === 'all' || r === 'all' || r === round
      }),
    [entries, hiddenAgents, round],
  )

  const counts = useMemo(() => {
    const result: Record<string, number> = {}
    for (const event of entries) {
      if (event.type === 'agent_message') result[event.agent_id] = (result[event.agent_id] ?? 0) + 1
    }
    return result
  }, [entries])

  // Keep the newest entry in view while the reader is at the bottom.
  useEffect(() => {
    const el = scroller.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [visible.length])

  function onScroll() {
    const el = scroller.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  function toggleAgent(id: string) {
    setHiddenAgents((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next.size === view.agents.length ? new Set() : next
    })
  }

  // Scroll to a cited message after the filters have been cleared and rendered.
  useEffect(() => {
    if (!jump) return
    document
      .getElementById(entryAnchor(jump.messageId))
      ?.scrollIntoView({ behavior: reducedMotion || document.hidden ? 'auto' : 'smooth', block: 'center' })
    const timer = window.setTimeout(() => {
      setJump((current) => (current === jump ? null : current))
    }, 2400)
    return () => {
      window.clearTimeout(timer)
    }
  }, [jump, reducedMotion])

  function jumpTo(messageId: string) {
    setHiddenAgents(new Set())
    setRound('all')
    stickToBottom.current = false
    setJump({ messageId })
  }

  const roundsAvailable = view.config?.max_rounds ?? view.roundsRun
  const roundOptions: { value: RoundFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 0, label: 'Opening' },
    ...Array.from({ length: roundsAvailable }, (_, i) => ({ value: i + 1, label: `R${i + 1}` })),
    { value: 'vote', label: 'Vote' },
  ]

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-col gap-3 border-b border-line px-4 py-3 md:px-5">
        <div className="flex items-baseline justify-between">
          <h2 className="font-mono text-[13px] font-[600] text-ink">Transcript</h2>
          <span className="font-mono text-[11px] text-faint">
            {visible.length === entries.length ? `${entries.length} entries` : `${visible.length} of ${entries.length}`}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by agent">
          {view.agents.map((agent) => (
            <AgentChip
              key={agent.id}
              agent={agent}
              active={!hiddenAgents.has(agent.id)}
              count={counts[agent.id] ?? 0}
              onToggle={() => {
                toggleAgent(agent.id)
              }}
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by round">
          {roundOptions.map((option) => (
            <button
              key={String(option.value)}
              type="button"
              aria-pressed={round === option.value}
              onClick={() => {
                setRound(option.value)
              }}
              className={`px-2 py-0.5 font-mono text-[11px] transition-colors ${
                round === option.value ? 'bg-signal text-void' : 'text-dim hover:text-ink'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={scroller}
        onScroll={onScroll}
        className="console-scroll max-h-[70vh] min-h-[240px] flex-1 overflow-y-auto px-4 py-4 md:px-5 lg:max-h-none"
        aria-live="polite"
        aria-relevant="additions"
      >
        {visible.length === 0 ? (
          <p className="text-[14px] text-faint">
            {entries.length === 0
              ? 'Arguments appear here as the council speaks.'
              : 'Nothing matches these filters. Turn an agent back on or pick another round.'}
          </p>
        ) : (
          <ol className="flex flex-col gap-4">
            {visible.map((event) => (
              <li key={event.seq}>
                <TranscriptEntry
                  event={event}
                  view={view}
                  highlighted={event.type === 'agent_message' && event.message_id === jump?.messageId}
                  onCite={jumpTo}
                />
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

function AgentChip({
  agent,
  active,
  count,
  onToggle,
}: {
  agent: AgentInfo
  active: boolean
  count: number
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onToggle}
      className="flex items-center gap-1.5 border px-2 py-0.5 font-mono text-[11px] transition-opacity"
      style={{
        borderColor: active ? agent.color : 'var(--color-line)',
        color: active ? agent.color : 'var(--color-faint)',
      }}
    >
      {agent.name}
      <span className="text-faint">{count}</span>
    </button>
  )
}
