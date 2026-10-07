import { clock, signalColor } from '../../lib/format'
import type { MagiEvent } from '../../types/events'

const SPEEDS = [0.5, 1, 2, 4, 8]
const SLIDER_STEP_MS = 50

interface Props {
  events: readonly MagiEvent[]
  /** Offset of each event from the start of the run, in ms. */
  offsets: readonly number[]
  duration: number
  playhead: number
  playing: boolean
  speed: number
  colors: Record<string, string>
  onSeek: (ms: number) => void
  onToggle: () => void
  onStep: (direction: -1 | 1) => void
  onSpeed: (speed: number) => void
}

function phaseLabel(event: Extract<MagiEvent, { type: 'phase_started' }>): string {
  switch (event.phase) {
    case 'opening':
      return 'Opening'
    case 'debate':
      return `R${event.round ?? ''}`
    case 'vote':
      return 'Vote'
    case 'verdict':
      return 'Verdict'
  }
}

/** Scrubbable timeline with a tick for every phase, message, vote and verdict. */
export function Timeline(props: Props) {
  const { events, offsets, duration, playhead, playing, speed, colors } = props
  // Round the slider range up to a whole step so its far end reaches the last
  // event; seeks past the end are clamped to `duration` by the caller.
  const sliderMax = Math.max(Math.ceil(duration / SLIDER_STEP_MS) * SLIDER_STEP_MS, SLIDER_STEP_MS)
  const at = (ms: number) => `${String(duration > 0 ? (ms / duration) * 100 : 0)}%`

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <ControlButton label="Step back" onClick={() => { props.onStep(-1) }}>
          ◀︎
        </ControlButton>
        <button
          type="button"
          onClick={props.onToggle}
          className="min-w-[84px] bg-signal px-3 py-1.5 font-mono text-[12px] font-[800] text-void"
          aria-label={playing ? 'Pause replay' : 'Play replay'}
        >
          {playing ? 'Pause' : playhead >= duration && duration > 0 ? 'Replay' : 'Play'}
        </button>
        <ControlButton label="Step forward" onClick={() => { props.onStep(1) }}>
          ▶︎
        </ControlButton>
        <span className="ml-1 font-mono text-[13px] text-ink tabular-nums">
          {clock(playhead)} <span className="text-faint">/ {clock(duration)}</span>
        </span>
        <div className="ml-auto flex items-center gap-1" role="group" aria-label="Playback speed">
          {SPEEDS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={speed === value}
              onClick={() => {
                props.onSpeed(value)
              }}
              className={`px-1.5 py-0.5 font-mono text-[11px] ${speed === value ? 'bg-raised text-signal' : 'text-dim hover:text-ink'}`}
            >
              {value}×
            </button>
          ))}
        </div>
      </div>

      <div className="relative h-11 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-signal">
        {/* Track */}
        <div className="absolute inset-x-0 top-[14px] h-[3px] bg-line" />
        <div className="absolute top-[14px] left-0 h-[3px] bg-signal/70" style={{ width: at(playhead) }} />

        {/* Ticks */}
        {events.map((event, i) => {
          const left = at(offsets[i] ?? 0)
          switch (event.type) {
            case 'phase_started': {
              const fraction = duration > 0 ? (offsets[i] ?? 0) / duration : 0
              // Keep edge labels inside the track.
              const align = fraction < 0.04 ? 'translate-x-0' : fraction > 0.96 ? '-translate-x-full' : '-translate-x-1/2'
              return (
                <div key={event.seq} className="pointer-events-none absolute top-[4px]" style={{ left }}>
                  <div className="h-[22px] w-px bg-signal/80" />
                  <span className={`absolute top-[24px] ${align} font-mono text-[10px] whitespace-nowrap text-dim`}>
                    {phaseLabel(event)}
                  </span>
                </div>
              )
            }
            case 'agent_message':
            case 'vote_cast':
              return (
                <div
                  key={event.seq}
                  className="pointer-events-none absolute top-[9px] h-[13px] w-[2px] -translate-x-1/2"
                  style={{ left, background: colors[event.agent_id] ?? 'var(--color-dim)', opacity: event.type === 'vote_cast' ? 0.55 : 1 }}
                />
              )
            case 'verdict':
              return (
                <div
                  key={event.seq}
                  className="pointer-events-none absolute top-[6px] size-[19px] -translate-x-1/2 rotate-45 border-2"
                  style={{ left, borderColor: signalColor(event.outcome) }}
                />
              )
            case 'run_error':
              return (
                <div
                  key={event.seq}
                  className="pointer-events-none absolute top-[9px] h-[13px] w-[2px] -translate-x-1/2 bg-alarm"
                  style={{ left }}
                />
              )
            default:
              return null
          }
        })}

        {/* Playhead */}
        <div
          className="pointer-events-none absolute top-0 h-[30px] w-[2px] -translate-x-1/2 bg-ink shadow-[0_0_6px_var(--color-ink)]"
          style={{ left: at(playhead) }}
        />

        <input
          type="range"
          min={0}
          max={sliderMax}
          step={SLIDER_STEP_MS}
          value={playhead}
          onChange={(e) => {
            props.onSeek(Number(e.target.value))
          }}
          aria-label="Replay position"
          aria-valuetext={`${clock(playhead)} of ${clock(duration)}`}
          className="absolute inset-x-0 top-0 h-[30px] w-full cursor-pointer opacity-0"
        />
      </div>
    </div>
  )
}

function ControlButton({ label, onClick, children }: { label: string; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="border border-line px-2 py-1 font-mono text-[11px] text-dim hover:border-signal hover:text-ink"
    >
      {children}
    </button>
  )
}
