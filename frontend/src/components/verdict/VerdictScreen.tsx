import { useEffect, useId, useRef, useState } from 'react'
import { percent, signalColor, signalText } from '../../lib/format'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import type { AgentInfo, Verdict, VoteCast } from '../../types/events'

const REVEAL_MS = 1150
const STAMP_DELAY_MS = 700
const SUMMARY_DELAY_MS = 900

interface Props {
  question: string
  verdict: Verdict
  votes: VoteCast[]
  agents: AgentInfo[]
  onClose: () => void
}

/**
 * Dramatic reveal: each agent's sealed vote opens in council order, then the
 * outcome is stamped, then the arbiter's summary appears.
 */
export function VerdictScreen({ question, verdict, votes, agents, onClose }: Props) {
  const reducedMotion = usePrefersReducedMotion()
  const titleId = useId()
  const dialog = useRef<HTMLDivElement>(null)
  const ordered = agents.map((agent) => ({ agent, vote: votes.find((v) => v.agent_id === agent.id) ?? null }))
  const total = ordered.length + 2 // votes, then stamp, then summary
  const [step, setStep] = useState(0)
  const shown = reducedMotion ? total : step
  const done = shown >= total

  useEffect(() => {
    if (reducedMotion || step >= total) return
    const delay = step < ordered.length ? (step === 0 ? 600 : REVEAL_MS) : step === ordered.length ? STAMP_DELAY_MS : SUMMARY_DELAY_MS
    const timer = window.setTimeout(() => {
      setStep((s) => s + 1)
    }, delay)
    return () => {
      window.clearTimeout(timer)
    }
  }, [step, total, ordered.length, reducedMotion])

  useEffect(() => {
    dialog.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const stamped = shown > ordered.length
  const color = signalColor(verdict.outcome)
  const summary = verdict.summary.replace(/\s*\[[a-z0-9_]+-r\d+\]/g, '')

  return (
    <div
      ref={dialog}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      tabIndex={-1}
      className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-void/95 outline-none backdrop-blur-[2px]"
    >
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col justify-center gap-8 px-4 py-10 md:px-8">
        <header className="flex flex-col gap-2">
          <h2 id={titleId} className="font-mono text-[13px] text-signal">
            Council verdict
          </h2>
          <p className="max-w-[60ch] text-[18px] leading-snug text-ink md:text-[20px]">{question}</p>
        </header>

        <ol className="grid grid-cols-1 gap-3 sm:grid-cols-3" aria-label="Votes">
          {ordered.map(({ agent, vote }, index) => (
            <li key={agent.id}>
              <VoteCard agent={agent} vote={vote} revealed={shown > index} />
            </li>
          ))}
        </ol>

        <div className="flex min-h-[150px] flex-col items-center justify-center gap-3 text-center" aria-live="polite">
          {stamped ? (
            <>
              <p
                className={`animate-stamp border-[3px] px-6 py-2 font-mono text-[40px] font-[800] tracking-[0.12em] sm:text-[64px] md:text-[76px] ${signalText(verdict.outcome)}`}
                style={{ borderColor: color, boxShadow: `0 0 40px color-mix(in oklab, ${color} 30%, transparent)` }}
              >
                {verdict.outcome}
              </p>
              <p className="font-mono text-[12px] text-dim">
                {verdict.tally.approve} approve, {verdict.tally.deny} deny, {verdict.tally.abstain} abstain under the{' '}
                {verdict.rule} rule
                {verdict.confidence > 0 && <>, confidence {percent(verdict.confidence)}</>}
              </p>
            </>
          ) : (
            <p className="font-mono text-[13px] tracking-[0.2em] text-faint">TALLYING</p>
          )}
        </div>

        <div className={`transition-opacity duration-700 ${shown >= total ? 'opacity-100' : 'opacity-0'}`}>
          <p className="mx-auto max-w-[68ch] text-center text-[15.5px] leading-relaxed text-dim">{summary}</p>
        </div>

        <footer className="flex justify-center gap-3">
          {done ? (
            <button
              type="button"
              onClick={onClose}
              className="bg-signal px-5 py-2 font-mono text-[13px] font-[800] text-void"
            >
              Return to console
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setStep(total)
              }}
              className="border border-line px-4 py-2 font-mono text-[12px] text-dim hover:border-signal hover:text-ink"
            >
              Skip reveal
            </button>
          )}
        </footer>
      </div>
    </div>
  )
}

function VoteCard({ agent, vote, revealed }: { agent: AgentInfo; vote: VoteCast | null; revealed: boolean }) {
  const open = revealed && vote !== null
  const color = open ? signalColor(vote.vote) : 'var(--color-line)'
  return (
    <article
      className="chamfer relative h-[188px] transition-[background] duration-500"
      style={{ background: open ? color : `color-mix(in oklab, ${agent.color} 40%, var(--color-void))` }}
      aria-label={`${agent.name}: ${open ? vote.vote : 'sealed'}`}
    >
      <div className="chamfer-fill flex flex-col bg-panel p-4">
        <header className="flex items-baseline justify-between">
          <span className="font-mono text-[14px] font-[800]" style={{ color: agent.color }}>
            {agent.name}
          </span>
          <span className="text-[12px] text-dim">{agent.title}</span>
        </header>
        {open ? (
          <div key="open" className="mt-3 flex flex-1 animate-transmit flex-col">
            <p className={`font-mono text-[30px] font-[800] leading-none tracking-[0.06em] ${signalText(vote.vote)}`}>
              {vote.vote}
            </p>
            <div className="mt-2 flex items-center gap-2">
              <span className="h-1 flex-1 bg-line">
                <span className="block h-full" style={{ width: percent(vote.confidence), background: color }} />
              </span>
              <span className="font-mono text-[11px] text-dim tabular-nums">{percent(vote.confidence)}</span>
            </div>
            <p className="mt-2 line-clamp-3 text-[13px] leading-snug text-dim">{vote.rationale}</p>
          </div>
        ) : (
          <div className="mt-3 flex flex-1 flex-col justify-center gap-2">
            <p className="font-mono text-[22px] font-[800] tracking-[0.2em] text-faint">SEALED</p>
            <span className="h-1 w-full bg-line" />
          </div>
        )}
      </div>
    </article>
  )
}
