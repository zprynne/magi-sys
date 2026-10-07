import type { Node, NodeProps } from '@xyflow/react'
import { signalColor } from '../../lib/format'
import type { Outcome, Phase } from '../../types/events'

export const CORE_NODE_SIZE = 168

export type CoreNodeData = {
  phase: Phase | null
  round: number | null
  maxRounds: number
  votesCast: number
  electorate: number
  outcome: Outcome | null
  halted: boolean
}
export type CoreFlowNode = Node<CoreNodeData, 'core'>

function readout(data: CoreNodeData): { title: string; detail: string } {
  if (data.halted) return { title: 'HALTED', detail: 'run failed' }
  if (data.outcome) return { title: data.outcome, detail: 'verdict issued' }
  switch (data.phase) {
    case null:
      return { title: 'STANDBY', detail: 'awaiting proposition' }
    case 'opening':
      return { title: 'OPENING', detail: 'independent positions' }
    case 'debate':
      return { title: `ROUND ${data.round ?? 1}`, detail: `of ${data.maxRounds}` }
    case 'vote':
      return { title: 'VOTING', detail: `${data.votesCast} of ${data.electorate} sealed` }
    case 'verdict':
      return { title: 'TALLYING', detail: 'writing synthesis' }
  }
}

const HEX = 'polygon(25% 3%, 75% 3%, 100% 50%, 75% 97%, 25% 97%, 0% 50%)'

export function CoreNode({ data }: NodeProps<CoreFlowNode>) {
  const { title, detail } = readout(data)
  const accent = data.outcome ? signalColor(data.outcome) : data.halted ? 'var(--color-alarm)' : 'var(--color-signal)'

  return (
    <div
      className="relative grid place-items-center"
      style={{ width: CORE_NODE_SIZE, height: CORE_NODE_SIZE }}
      aria-live="polite"
    >
      <div className="absolute inset-0" style={{ clipPath: HEX, background: accent, opacity: 0.85 }} />
      <div className="absolute inset-[2px] bg-void" style={{ clipPath: HEX }} />
      <div className="relative flex flex-col items-center text-center">
        <span className="font-mono text-[10px] tracking-[0.3em] text-faint">MAGI</span>
        <span className="mt-1 font-mono text-[17px] font-[800] tracking-[0.04em]" style={{ color: accent }}>
          {title}
        </span>
        <span className="mt-0.5 max-w-[120px] text-[12px] leading-tight text-dim">{detail}</span>
      </div>
    </div>
  )
}
