import type { ReactNode } from 'react'
import type { DeliberationView } from '../state/deliberation'
import { CouncilGraph } from './graph/CouncilGraph'

interface Props {
  view: DeliberationView
  /** Proposition header and notices above the graph. */
  top?: ReactNode
  /** Phase track, playback controls, ... below the graph. */
  bottom: ReactNode
  /** Right rail on desktop, below the graph on tablet. */
  aside: ReactNode
  /** Overlays such as the verdict screen. */
  children?: ReactNode
}

/** Shared frame for the live console and the replay player. */
export function CouncilLayout({ view, top, bottom, aside, children }: Props) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(360px,30%)]">
      <div className="flex min-h-0 flex-col">
        {top}
        <div className="relative h-[600px] min-h-0 lg:h-auto lg:flex-1">
          {view.agents.length > 0 && <CouncilGraph view={view} />}
        </div>
        <div className="border-t border-line px-4 py-3 md:px-6">{bottom}</div>
      </div>
      <aside className="flex min-h-0 flex-col border-t border-line lg:border-t-0 lg:border-l">{aside}</aside>
      {children}
    </div>
  )
}

export function Notice({ children, tone = 'alarm' }: { children: ReactNode; tone?: 'alarm' | 'signal' }) {
  const cls = tone === 'alarm' ? 'border-alarm/50 bg-alarm/10 text-alarm' : 'border-signal/50 bg-signal/10 text-signal'
  return <p className={`border-b px-4 py-2 text-[14px] md:px-6 ${cls}`}>{children}</p>
}
