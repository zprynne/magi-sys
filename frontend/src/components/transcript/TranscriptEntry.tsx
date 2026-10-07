import { Fragment, type ReactNode } from 'react'
import { clock, elapsed, percent, signalText, stanceLabel } from '../../lib/format'
import type { DeliberationView } from '../../state/deliberation'
import type { AgentMessage, MagiEvent, Verdict } from '../../types/events'
import { entryAnchor } from './anchors'

interface Props {
  event: MagiEvent
  view: DeliberationView
  highlighted: boolean
  onCite: (messageId: string) => void
}

export function TranscriptEntry({ event, view, highlighted, onCite }: Props) {
  const agent = (id: string | null | undefined) => (id ? view.byAgent[id]?.info : undefined)
  const at = clock(elapsed(view.startedAt, event.timestamp))

  switch (event.type) {
    case 'phase_started':
      return (
        <div className="flex items-center gap-3 pt-1" role="separator">
          <span className="font-mono text-[11px] text-signal">{phaseTitle(event.phase, event.round)}</span>
          <span className="h-px flex-1 bg-line" />
          <span className="font-mono text-[10px] text-faint tabular-nums">{at}</span>
        </div>
      )

    case 'agent_message': {
      const speaker = agent(event.agent_id)
      const color = speaker?.color ?? 'var(--color-dim)'
      return (
        <article
          id={entryAnchor(event.message_id)}
          className="border-l-2 py-0.5 pl-3 transition-colors duration-500"
          style={{
            borderColor: color,
            background: highlighted ? `color-mix(in oklab, ${color} 14%, transparent)` : undefined,
          }}
        >
          <header className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-mono text-[12px] font-[800]" style={{ color }}>
              {speaker?.name ?? event.agent_id}
            </span>
            {event.reply_to.length > 0 && (
              <span className="text-[12px] text-dim">
                answering{' '}
                {event.reply_to.map((ref, i) => {
                  const target = agent(ref.agent_id)
                  return (
                    <Fragment key={ref.message_id}>
                      {i > 0 && ', '}
                      <button
                        type="button"
                        onClick={() => {
                          onCite(ref.message_id)
                        }}
                        className="underline decoration-dotted underline-offset-2 hover:text-ink"
                        style={{ color: target?.color }}
                      >
                        {target?.name ?? ref.agent_id}
                      </button>
                    </Fragment>
                  )
                })}
              </span>
            )}
            <span className="ml-auto font-mono text-[10px] text-faint tabular-nums">{at}</span>
          </header>
          <p className={`mt-0.5 font-mono text-[11px] ${signalText(event.stance)}`}>{stanceLabel(event.stance)}</p>
          <p className="mt-1 text-[14.5px] leading-relaxed text-ink">{event.content}</p>
        </article>
      )
    }

    case 'agent_revised_position': {
      const who = agent(event.agent_id)
      return (
        <p className="border-l-2 border-signal pl-3 text-[13px] text-dim">
          <span className="font-mono text-[11px] text-signal">Revised </span>
          <span style={{ color: who?.color }}>{who?.name}</span>{' '}
          <span className={signalText(event.previous_stance)}>{stanceLabel(event.previous_stance)}</span>
          {' to '}
          <span className={signalText(event.new_stance)}>{stanceLabel(event.new_stance)}</span>. {event.reason}
        </p>
      )
    }

    case 'vote_cast': {
      const who = agent(event.agent_id)
      const sealed = view.verdict === null
      return (
        <p className="flex flex-wrap items-baseline gap-x-2 text-[13.5px]">
          <span className="font-mono text-[12px] font-[800]" style={{ color: who?.color }}>
            {who?.name}
          </span>
          {sealed ? (
            <span className="font-mono text-[11px] tracking-[0.12em] text-dim">VOTE SEALED</span>
          ) : (
            <>
              <span className={`font-mono text-[12px] font-[800] ${signalText(event.vote)}`}>{event.vote}</span>
              <span className="font-mono text-[11px] text-dim">{percent(event.confidence)} confidence</span>
              <span className="basis-full text-dim">{event.rationale}</span>
            </>
          )}
        </p>
      )
    }

    case 'verdict':
      return <VerdictEntry verdict={event} view={view} onCite={onCite} />

    case 'run_error':
      return (
        <p className={`border-l-2 border-alarm pl-3 text-[13px] ${event.fatal ? 'text-alarm' : 'text-dim'}`}>
          <span className="font-mono text-[11px] text-alarm">{event.fatal ? 'Run failed ' : 'Agent fault '}</span>
          {event.message}
        </p>
      )

    default:
      return null
  }
}

function phaseTitle(phase: string, round: number | null): string {
  switch (phase) {
    case 'opening':
      return 'Opening statements'
    case 'debate':
      return `Debate round ${round ?? ''}`
    case 'vote':
      return 'Vote'
    default:
      return 'Verdict'
  }
}

const CITATION = /\[([a-z0-9_]+-r\d+)\]/g

/** Render "[melchior-r1]" citations as links to the cited argument. */
function withCitations(text: string, messages: AgentMessage[], view: DeliberationView, onCite: (id: string) => void) {
  const known = new Map(messages.map((m) => [m.message_id, m]))
  const parts: ReactNode[] = []
  let last = 0
  for (const match of text.matchAll(CITATION)) {
    const id = match[1]
    const message = id ? known.get(id) : undefined
    if (!id || !message) continue
    parts.push(text.slice(last, match.index))
    const info = view.byAgent[message.agent_id]?.info
    const label = message.round === 0 ? 'opening' : `R${message.round}`
    parts.push(
      <button
        key={`${id}-${match.index}`}
        type="button"
        onClick={() => {
          onCite(id)
        }}
        className="mx-0.5 border px-1 font-mono text-[10.5px] hover:bg-raised"
        style={{ borderColor: info?.color, color: info?.color }}
        title={`Show ${info?.name ?? id}, ${label}`}
      >
        {info?.name ?? id} {label}
      </button>,
    )
    last = match.index + match[0].length
  }
  parts.push(text.slice(last))
  return parts
}

function VerdictEntry({
  verdict,
  view,
  onCite,
}: {
  verdict: Verdict
  view: DeliberationView
  onCite: (id: string) => void
}) {
  const { tally } = verdict
  return (
    <section className="border border-line bg-panel p-4" aria-label="Verdict">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <span className={`font-mono text-[20px] font-[800] tracking-[0.08em] ${signalText(verdict.outcome)}`}>
          {verdict.outcome}
        </span>
        <span className="font-mono text-[11px] text-dim">
          {tally.approve} approve, {tally.deny} deny, {tally.abstain} abstain
        </span>
      </header>
      <p className="mt-0.5 text-[12px] text-dim">
        {verdict.rule === 'unanimous' ? 'Unanimous rule' : 'Majority rule'}, confidence {percent(verdict.confidence)}
      </p>
      <p className="mt-3 text-[14.5px] leading-relaxed text-ink">
        {withCitations(verdict.summary, view.messages, view, onCite)}
      </p>
      {verdict.decisive_arguments.length > 0 && (
        <div className="mt-4">
          <h3 className="font-mono text-[11px] text-signal">Decisive arguments</h3>
          <ul className="mt-2 flex flex-col gap-2">
            {verdict.decisive_arguments.map((arg) => {
              const info = view.byAgent[arg.agent_id]?.info
              return (
                <li key={`${arg.agent_id}-${arg.message_id ?? arg.reason}`} className="text-[13.5px] text-dim">
                  {arg.message_id ? (
                    <button
                      type="button"
                      onClick={() => {
                        if (arg.message_id) onCite(arg.message_id)
                      }}
                      className="font-mono text-[11.5px] underline decoration-dotted underline-offset-2"
                      style={{ color: info?.color }}
                    >
                      {info?.name ?? arg.agent_id}
                    </button>
                  ) : (
                    <span className="font-mono text-[11.5px]" style={{ color: info?.color }}>
                      {info?.name ?? arg.agent_id}
                    </span>
                  )}{' '}
                  {arg.reason}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </section>
  )
}
