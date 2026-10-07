import { useEffect, useState, type ChangeEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, type TraceSummary } from '../lib/api'
import { shortDate, signalText } from '../lib/format'
import { parseJsonl } from '../types/events'
import type { LocalTraceState } from './ReplayPage'

type State = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; traces: TraceSummary[] }

export function ReplayIndexPage() {
  const navigate = useNavigate()
  const [state, setState] = useState<State>({ status: 'loading' })
  const [fileError, setFileError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .traces()
      .then((traces) => {
        if (!cancelled) setState({ status: 'ready', traces })
      })
      .catch((err: unknown) => {
        if (!cancelled) setState({ status: 'error', message: err instanceof ApiError ? err.message : String(err) })
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function openFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const events = parseJsonl(await file.text())
      if (events.length === 0) throw new Error('the file has no events')
      const state: LocalTraceState = { name: file.name.replace(/\.jsonl$/, ''), events }
      void navigate('/replay/local', { state })
    } catch (err) {
      setFileError(`Could not read ${file.name}: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  return (
    <div className="console-scroll flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 md:px-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-mono text-[18px] font-[800] text-ink">Replays</h1>
            <p className="mt-1 max-w-[60ch] text-[14px] text-dim">
              Every deliberation is saved as a JSONL trace in <code className="font-mono text-[12px]">traces/</code>.
              Open one to scrub through it event by event.
            </p>
          </div>
          <label className="cursor-pointer border border-line px-3 py-1.5 font-mono text-[12px] text-ink hover:border-signal focus-within:outline-2 focus-within:outline-signal">
            Open a JSONL file
            <input type="file" accept=".jsonl,application/x-ndjson,application/json" onChange={(e) => void openFile(e)} className="sr-only" />
          </label>
        </header>
        {fileError && <p className="border-l-2 border-alarm pl-3 text-[13px] text-alarm">{fileError}</p>}

        {state.status === 'loading' && <p className="font-mono text-[12px] text-dim">Loading traces</p>}
        {state.status === 'error' && <p className="text-[14px] text-alarm">{state.message}</p>}
        {state.status === 'ready' &&
          (state.traces.length === 0 ? (
            <p className="text-[14px] text-dim">
              No traces yet. <Link to="/" className="text-signal underline underline-offset-4">Convene the council</Link>{' '}
              and the run will be saved here.
            </p>
          ) : (
            <ul className="flex flex-col border-t border-line">
              {state.traces.map((trace) => (
                <li key={trace.trace_id} className="border-b border-line">
                  <Link
                    to={`/replay/${encodeURIComponent(trace.trace_id)}`}
                    className="grid grid-cols-[1fr_auto] items-baseline gap-x-6 gap-y-1 px-1 py-3.5 transition-colors hover:bg-panel md:grid-cols-[1fr_120px_110px]"
                  >
                    <span className="text-[15.5px] leading-snug text-ink">{trace.question}</span>
                    <span className={`font-mono text-[12px] font-[800] md:text-right ${signalText(trace.outcome)}`}>
                      {trace.outcome ?? (trace.status === 'failed' ? 'FAILED' : 'INCOMPLETE')}
                    </span>
                    <span className="col-span-2 flex gap-3 font-mono text-[11px] text-faint md:col-span-1 md:block md:text-right">
                      {trace.example ? <span className="text-signal">example</span> : shortDate(trace.started_at)}
                      <span className="md:block">{trace.verdict_rule}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </div>
  )
}
