import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useServerConfig } from '../lib/config'

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
      <path d="M16 9 9 21h14Z" fill="none" stroke="var(--color-signal)" strokeWidth="1.5" />
      <circle cx="16" cy="8" r="3.5" fill="#4cc9f0" />
      <circle cx="8" cy="22" r="3.5" fill="#ffb020" />
      <circle cx="24" cy="22" r="3.5" fill="#c08cff" />
    </svg>
  )
}

function ModeBadge() {
  const { config, error } = useServerConfig()
  if (error) return <span className="font-mono text-[11px] text-alarm">Server offline</span>
  if (!config) return <span className="font-mono text-[11px] text-faint">Connecting</span>
  if (config.mock) {
    return (
      <span className="flex items-center gap-2 font-mono text-[11px] text-signal" title="MAGI_MOCK=1: recorded deliberations, no API calls">
        <span className="size-1.5 rounded-full bg-signal" aria-hidden />
        Mock replay
      </span>
    )
  }
  const models = [...new Set(config.agents.map((a) => a.model).filter(Boolean))].join(', ')
  return (
    <span
      className="flex items-center gap-2 font-mono text-[11px] text-phosphor"
      title={config.profile ? `Profile ${config.profile}: ${models}` : `Effort: ${config.effort}`}
    >
      <span className="size-1.5 rounded-full bg-phosphor shadow-[0_0_6px_var(--color-phosphor)]" aria-hidden />
      {config.profile ? `${config.profile} profile` : config.model}
    </span>
  )
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 font-mono text-[12px] transition-colors ${
    isActive ? 'text-signal' : 'text-dim hover:text-ink'
  }`

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh">
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-line px-4 md:px-6">
        <NavLink to="/" className="flex items-center gap-3" aria-label="MAGI console home">
          <Mark />
          <span className="font-mono text-[17px] font-[800] tracking-[0.18em] text-ink">MAGI</span>
          <span className="hidden text-[13px] text-dim sm:inline">deliberation console</span>
        </NavLink>
        <nav className="ml-auto flex items-center" aria-label="Main">
          <NavLink to="/" end className={navClass}>
            Council
          </NavLink>
          <NavLink to="/replay" className={navClass}>
            Replays
          </NavLink>
        </nav>
        <div className="hidden border-l border-line pl-4 md:block">
          <ModeBadge />
        </div>
      </header>
      <main className="flex min-h-0 flex-1 flex-col">{children}</main>
    </div>
  )
}
