import type { ReactNode } from 'react'
import { clock, ruleLabel } from '../lib/format'
import type { DeliberationView } from '../state/deliberation'

interface Props {
  view: DeliberationView
  elapsedMs: number
  status: ReactNode
  actions?: ReactNode
}

/** The proposition under deliberation, with run status and actions. */
export function RunHeader({ view, elapsedMs, status, actions }: Props) {
  const config = view.config
  return (
    <section className="flex flex-col gap-3 border-b border-line px-4 py-4 md:flex-row md:items-end md:justify-between md:px-6">
      <div className="min-w-0">
        {config && (
          <p className="mb-1 text-[13px] text-dim">
            {ruleLabel(config.verdict_rule, config.max_rounds)}
            {config.mock && <span className="ml-2 font-mono text-[11px] text-signal">recorded</span>}
            {config.profile && (
              <span className="ml-2 font-mono text-[11px] text-phosphor">{config.profile} profile</span>
            )}
          </p>
        )}
        <h1 className="max-w-[68ch] text-[21px] leading-snug font-[500] text-ink md:text-[23px]">
          {view.question ?? 'Connecting to the council'}
        </h1>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2">
        <span className="font-mono text-[20px] font-[600] tabular-nums text-signal" aria-label="Elapsed time">
          {clock(elapsedMs)}
        </span>
        {status}
        {actions}
      </div>
    </section>
  )
}

export function ActionButton({
  children,
  onClick,
  primary = false,
}: {
  children: ReactNode
  onClick: () => void
  primary?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        primary
          ? 'bg-signal px-3 py-1.5 font-mono text-[12px] font-[800] text-void'
          : 'border border-line px-3 py-1.5 font-mono text-[12px] text-ink hover:border-signal'
      }
    >
      {children}
    </button>
  )
}
