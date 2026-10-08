import { useState, type SyntheticEvent } from 'react'
import type { ServerConfig } from '../lib/api'
import type { VerdictRule } from '../types/events'

export interface Proposal {
  question: string
  maxRounds: number
  rule: VerdictRule
  traceId?: string
}

interface Props {
  config: ServerConfig
  busy: boolean
  error: string | null
  onSubmit: (proposal: Proposal) => void
}

export function ProposalForm({ config, busy, error, onSubmit }: Props) {
  const [question, setQuestion] = useState('')
  const [maxRounds, setMaxRounds] = useState(config.max_rounds)
  const [rule, setRule] = useState<VerdictRule>(config.verdict_rule)
  const missingKey = !config.mock && config.requires_api_key && !config.api_key_configured
  const tooShort = question.trim().length < 3

  function submit(event: SyntheticEvent) {
    event.preventDefault()
    if (tooShort || busy) return
    onSubmit({ question: question.trim(), maxRounds, rule })
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label htmlFor="proposition" className="font-mono text-[12px] text-dim">
        Proposition for the council
      </label>
      <textarea
        id="proposition"
        value={question}
        onChange={(e) => {
          setQuestion(e.target.value)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e)
        }}
        rows={3}
        maxLength={2000}
        placeholder="Ask a yes-or-no question, or state a proposal to approve or deny."
        className="w-full resize-none border border-line bg-panel px-3 py-2.5 text-[17px] leading-snug text-ink placeholder:text-faint focus:border-signal focus:outline-none"
      />

      {config.mock ? (
        <p className="text-[13px] text-dim">
          Mock mode replays recorded deliberations, so the council answers with the recording closest to your
          question. No API calls are made.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <label className="flex items-center gap-2 text-[13px] text-dim">
            Debate rounds
            <select
              value={maxRounds}
              onChange={(e) => {
                setMaxRounds(Number(e.target.value))
              }}
              className="border border-line bg-panel px-2 py-1 font-mono text-[12px] text-ink focus:border-signal focus:outline-none"
            >
              {[0, 1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="flex items-center gap-2 text-[13px] text-dim">
            <legend className="sr-only">Verdict rule</legend>
            <span aria-hidden>Verdict rule</span>
            {(['majority', 'unanimous'] as const).map((value) => (
              <label
                key={value}
                className={`border px-2 py-1 font-mono text-[12px] ${
                  rule === value ? 'border-signal text-signal' : 'border-line text-dim hover:text-ink'
                }`}
              >
                <input
                  type="radio"
                  name="rule"
                  value={value}
                  checked={rule === value}
                  onChange={() => {
                    setRule(value)
                  }}
                  className="sr-only"
                />
                {value === 'majority' ? 'Majority' : 'Unanimous'}
              </label>
            ))}
          </fieldset>
        </div>
      )}

      {missingKey && (
        <p className="border-l-2 border-alarm pl-3 text-[13px] text-alarm">
          The server has no ANTHROPIC_API_KEY. Add it to .env and restart, run with MAGI_MOCK=1, or use
          the local MLX council (make mlx, then make local).
        </p>
      )}
      {error && <p className="border-l-2 border-alarm pl-3 text-[13px] text-alarm">{error}</p>}

      <div className="flex items-center gap-4">
        <button
          type="submit"
          disabled={tooShort || busy || missingKey}
          className="bg-signal px-5 py-2.5 font-mono text-[13px] font-[800] tracking-[0.06em] text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
        >
          {busy ? 'Convening' : 'Convene council'}
        </button>
        <span className="hidden text-[12px] text-faint sm:inline">Ctrl/⌘ + Enter</span>
      </div>

      {config.mock && config.replayable.length > 0 && (
        <div className="mt-2 flex flex-col gap-2">
          <p className="font-mono text-[12px] text-dim">Recorded deliberations</p>
          <ul className="flex flex-col gap-1.5">
            {config.replayable.map((trace) => (
              <li key={trace.trace_id}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    onSubmit({ question: trace.question, maxRounds, rule, traceId: trace.trace_id })
                  }}
                  className="w-full border border-line px-3 py-2 text-left text-[14px] text-ink transition-colors hover:border-signal disabled:opacity-40"
                >
                  {trace.question}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </form>
  )
}
