import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { CouncilLayout, Notice } from '../components/CouncilLayout'
import { PhaseTrack } from '../components/PhaseTrack'
import { Timeline } from '../components/replay/Timeline'
import { ActionButton, RunHeader } from '../components/RunHeader'
import { Transcript } from '../components/transcript/Transcript'
import { VerdictScreen } from '../components/verdict/VerdictScreen'
import { api, ApiError } from '../lib/api'
import { usePlayback } from '../lib/usePlayback'
import { useVerdictOverlay } from '../lib/useVerdictOverlay'
import { deriveView } from '../state/deliberation'
import type { MagiEvent } from '../types/events'

/** Trace handed over from the replay index when a local JSONL file is opened. */
export interface LocalTraceState {
  name: string
  events: MagiEvent[]
}

type Loaded = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; events: MagiEvent[] }

function useTrace(traceId: string, local: LocalTraceState | null): Loaded {
  const [remote, setRemote] = useState<{ id: string; result: Loaded } | null>(null)

  useEffect(() => {
    if (local) return
    let cancelled = false
    api
      .trace(traceId)
      .then((trace) => {
        if (!cancelled) setRemote({ id: traceId, result: { status: 'ready', events: trace.events } })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message =
          err instanceof ApiError && err.status === 404
            ? `No saved trace named “${traceId}”.`
            : err instanceof Error
              ? err.message
              : String(err)
        setRemote({ id: traceId, result: { status: 'error', message } })
      })
    return () => {
      cancelled = true
    }
  }, [traceId, local])

  if (local) return { status: 'ready', events: local.events }
  return remote?.id === traceId ? remote.result : { status: 'loading' }
}

export function ReplayPage() {
  const { traceId = '' } = useParams()
  const location = useLocation()
  const local = (location.state as LocalTraceState | null) ?? null
  const trace = useTrace(traceId, local)

  if (trace.status === 'loading') {
    return <p className="px-6 py-8 font-mono text-[12px] text-dim">Loading trace {traceId}</p>
  }
  if (trace.status === 'error') {
    return (
      <div className="flex flex-col items-start gap-4 px-6 py-8">
        <p className="text-[15px] text-alarm">{trace.message}</p>
        <Link to="/replay" className="font-mono text-[12px] text-signal underline underline-offset-4">
          Back to replays
        </Link>
      </div>
    )
  }
  return <Player key={traceId} traceId={local?.name ?? traceId} events={trace.events} />
}

function download(name: string, events: readonly MagiEvent[]) {
  const blob = new Blob([events.map((e) => JSON.stringify(e)).join('\n') + '\n'], { type: 'application/x-ndjson' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name.endsWith('.jsonl') ? name : `${name}.jsonl`
  anchor.click()
  URL.revokeObjectURL(url)
}

function Player({ traceId, events }: { traceId: string; events: MagiEvent[] }) {
  const start = events[0] ? Date.parse(events[0].timestamp) : 0
  const offsets = useMemo(() => events.map((e) => Date.parse(e.timestamp) - start), [events, start])
  const duration = offsets.at(-1) ?? 0
  const playback = usePlayback(duration)

  // Number of events at or before the playhead (at least the run_started event).
  const cursor = useMemo(() => {
    let count = 0
    while (count < offsets.length && (offsets[count] ?? Infinity) <= playback.playhead) count += 1
    return Math.max(count, Math.min(1, events.length))
  }, [offsets, playback.playhead, events.length])

  const visible = useMemo(() => events.slice(0, cursor), [events, cursor])
  const view = useMemo(() => deriveView(visible), [visible])
  const verdict = useVerdictOverlay(view.verdict)
  const colors = useMemo(() => Object.fromEntries(view.agents.map((a) => [a.id, a.color])), [view.agents])

  function step(direction: -1 | 1) {
    playback.pause()
    const target = direction === 1 ? offsets[cursor] : offsets[Math.max(cursor - 2, 0)]
    playback.seek(target ?? (direction === 1 ? duration : 0))
  }

  // Space toggles playback (unless a control has focus).
  const { toggle } = playback
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(target.tagName)) return
      if (event.key === ' ') {
        event.preventDefault()
        toggle()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [toggle])

  const valid = events[0]?.type === 'run_started'

  return (
    <CouncilLayout
      view={view}
      top={
        <>
          <RunHeader
            view={view}
            elapsedMs={playback.playhead}
            status={<span className="font-mono text-[12px] text-signal">Replay</span>}
            actions={
              <>
                {view.verdict && !verdict.open && <ActionButton onClick={verdict.reopen}>Show verdict</ActionButton>}
                <ActionButton
                  onClick={() => {
                    download(traceId, events)
                  }}
                >
                  Download JSONL
                </ActionButton>
              </>
            }
          />
          {!valid && <Notice>This trace does not start with run_started, so the council cannot be drawn.</Notice>}
        </>
      }
      bottom={
        <div className="flex flex-col gap-3">
          <Timeline
            events={events}
            offsets={offsets}
            duration={duration}
            playhead={playback.playhead}
            playing={playback.playing}
            speed={playback.speed}
            colors={colors}
            onSeek={(ms) => {
              playback.pause()
              playback.seek(ms)
            }}
            onToggle={playback.toggle}
            onStep={step}
            onSpeed={playback.setSpeed}
          />
          <PhaseTrack view={view} />
        </div>
      }
      aside={<Transcript events={visible} view={view} />}
    >
      {verdict.open && view.verdict && (
        <VerdictScreen
          question={view.question ?? ''}
          verdict={view.verdict}
          votes={view.votes}
          agents={view.agents}
          onClose={verdict.close}
        />
      )}
    </CouncilLayout>
  )
}
