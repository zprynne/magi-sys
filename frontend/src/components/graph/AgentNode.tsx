import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { percent, shortModel, signalText, stanceLabel } from '../../lib/format'
import type { AgentStatus, AgentView } from '../../state/deliberation'

export const AGENT_NODE_WIDTH = 284
export const AGENT_NODE_HEIGHT = 204

export type AgentNodeData = {
  agent: AgentView
  /** Votes stay sealed until the verdict is announced. */
  sealed: boolean
}
export type AgentFlowNode = Node<AgentNodeData, 'agent'>

const STATUS_TEXT: Record<AgentStatus, string> = {
  idle: 'Standing by',
  thinking: 'Deliberating',
  speaking: 'Speaking',
  voted: 'Vote cast',
}

const centered = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' } as const

export function AgentNode({ data }: NodeProps<AgentFlowNode>) {
  const { agent, sealed } = data
  const { info, status } = agent
  const active = status === 'thinking' || status === 'speaking'
  const borderStrength = status === 'idle' ? 38 : status === 'voted' ? 60 : 100

  return (
    <div
      className="relative"
      style={{
        width: AGENT_NODE_WIDTH,
        height: AGENT_NODE_HEIGHT,
        filter: active ? `drop-shadow(0 0 14px color-mix(in oklab, ${info.color} 45%, transparent))` : undefined,
        transition: 'filter 300ms ease',
      }}
      data-agent={info.id}
      data-status={status}
    >
      <Handle type="source" position={Position.Top} style={centered} isConnectable={false} />
      <Handle type="target" position={Position.Top} style={centered} isConnectable={false} />

      <div
        className="chamfer absolute inset-0"
        style={{
          background: `color-mix(in oklab, ${info.color} ${borderStrength}%, var(--color-void))`,
          transition: 'background 300ms ease',
        }}
      >
        <div className="chamfer-fill flex flex-col bg-panel px-4 pt-3 pb-3">
          <header className="flex items-baseline justify-between gap-2">
            <h3 className="font-mono text-[15px] font-[800] tracking-[0.06em]" style={{ color: info.color }}>
              {info.name}
            </h3>
            <StatusLight status={status} color={info.color} />
          </header>
          <p className="flex items-baseline justify-between gap-3 text-[13px] text-dim">
            <span className="shrink-0">{info.title}</span>
            {info.model && (
              <span className="min-w-0 truncate font-mono text-[10px] text-faint" title={info.model}>
                {shortModel(info.model)}
              </span>
            )}
          </p>

          <div className="mt-2 h-px" style={{ background: `color-mix(in oklab, ${info.color} 30%, transparent)` }} />

          <div className="mt-2 flex min-h-0 flex-1 flex-col">
            {agent.stance ? (
              <p className="flex items-center gap-2 text-[12px]">
                <span className={`font-mono font-[600] ${signalText(agent.stance)}`}>{stanceLabel(agent.stance)}</span>
                {agent.revised && (
                  <span className="rounded-sm border border-signal/60 px-1 font-mono text-[10px] text-signal">
                    revised
                  </span>
                )}
              </p>
            ) : (
              <p className="text-[12px] text-faint">No position yet</p>
            )}
            {agent.summary && (
              <p
                key={agent.lastMessage?.message_id ?? agent.summary}
                className="mt-1 line-clamp-3 animate-transmit text-[13.5px] leading-snug text-ink"
              >
                {agent.summary}
              </p>
            )}
            {agent.error && !agent.summary && (
              <p className="mt-1 line-clamp-2 text-[12px] text-alarm">{agent.error}</p>
            )}
          </div>

          {agent.vote && (
            <footer className="mt-auto flex items-baseline justify-between border-t border-line pt-1.5">
              <span className="font-mono text-[11px] text-dim">Vote</span>
              {sealed ? (
                <span className="font-mono text-[12px] tracking-[0.12em] text-dim">SEALED</span>
              ) : (
                <span className={`font-mono text-[13px] font-[800] ${signalText(agent.vote.vote)}`}>
                  {agent.vote.vote} <span className="font-[400] text-dim">{percent(agent.vote.confidence)}</span>
                </span>
              )}
            </footer>
          )}

          {status === 'thinking' && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[3px] overflow-hidden">
              <div className="h-full w-2/5 animate-scan" style={{ background: info.color }} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusLight({ status, color }: { status: AgentStatus; color: string }) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-[10.5px] text-dim">
      <span
        className={`inline-block size-2 rounded-full ${status === 'thinking' ? 'animate-blink' : ''}`}
        style={{
          background: status === 'idle' ? 'var(--color-faint)' : color,
          boxShadow: status === 'speaking' ? `0 0 8px ${color}` : undefined,
        }}
        aria-hidden
      />
      {STATUS_TEXT[status]}
    </span>
  )
}
