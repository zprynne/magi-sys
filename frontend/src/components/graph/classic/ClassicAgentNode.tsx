import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { kanjiFor } from '../../../lib/theme'
import { percent, stanceLabel } from '../../../lib/format'
import type { AgentStatus, AgentView } from '../../../state/deliberation'
import { displayName, SLABS, type Slot } from './geometry'

export type ClassicAgentData = {
  agent: AgentView
  sealed: boolean
  slot: Slot
}
export type ClassicAgentFlowNode = Node<ClassicAgentData, 'classicAgent'>

const STATUS_TEXT: Record<AgentStatus, string> = {
  idle: 'STANDBY',
  thinking: 'DELIBERATING',
  speaking: 'TRANSMITTING',
  voted: 'VOTE SEALED',
}

/** Slab fill: blue while working, then the revealed vote. */
function fillFor(agent: AgentView, sealed: boolean): string {
  if (agent.vote && !sealed) {
    if (agent.vote.vote === 'APPROVE') return 'var(--classic-approve)'
    if (agent.vote.vote === 'DENY') return 'var(--classic-deny)'
    return 'var(--classic-abstain)'
  }
  if (agent.status === 'voted') return 'var(--classic-sealed)'
  if (agent.status === 'speaking') return 'var(--classic-speaking)'
  return 'var(--classic-idle)'
}

const centered = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' } as const

export function ClassicAgentNode({ data }: NodeProps<ClassicAgentFlowNode>) {
  const { agent, sealed, slot } = data
  const shape = SLABS[slot]
  const revealed = agent.vote !== null && !sealed

  return (
    <div
      className="relative font-slab text-[#0a0a0a]"
      style={{ width: shape.width, height: shape.height }}
      data-agent={agent.info.id}
      data-status={agent.status}
    >
      <Handle type="source" position={Position.Top} style={centered} isConnectable={false} />
      <Handle type="target" position={Position.Top} style={centered} isConnectable={false} />

      <svg
        className="absolute inset-0 h-full w-full overflow-visible"
        viewBox={`0 0 ${String(shape.width)} ${String(shape.height)}`}
        aria-hidden
      >
        <polygon
          points={shape.points}
          fill={fillFor(agent, sealed)}
          className={agent.status === 'thinking' ? 'animate-classic-think' : undefined}
          style={{ transition: 'fill 400ms ease' }}
        />
      </svg>

      <div className="relative flex h-full flex-col" style={{ padding: shape.padding }}>
        <h3 className="text-[38px] leading-none font-[700] tracking-[0.01em]">{displayName(agent.info.name)}</h3>
        <p className="mt-1 text-[14px] leading-none font-[600] tracking-[0.12em] opacity-70">
          {revealed ? 'VOTE CAST' : STATUS_TEXT[agent.status]}
          {agent.stance && !revealed && <> · {stanceLabel(agent.stance).toUpperCase()}</>}
        </p>
        {revealed && agent.vote ? (
          <p className="mt-auto flex items-baseline gap-3">
            <span className="font-kanji text-[40px] leading-none font-[700]">
              {kanjiFor(agent.vote.vote)}
            </span>
            <span className="text-[20px] font-[700] tracking-[0.06em]">
              {agent.vote.vote} {percent(agent.vote.confidence)}
            </span>
          </p>
        ) : (
          agent.summary && (
            <p
              key={agent.lastMessage?.message_id ?? agent.summary}
              className="mt-auto line-clamp-3 animate-transmit font-sans text-[13px] leading-snug font-[500]"
            >
              {agent.summary}
            </p>
          )
        )}
      </div>
    </div>
  )
}
