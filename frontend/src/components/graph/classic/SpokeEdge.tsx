import { getStraightPath, type Edge, type EdgeProps } from '@xyflow/react'
import type { Reply } from '../../../state/deliberation'
import { Pulse } from '../ConduitEdge'

export type SpokeData = {
  /** The agent at the outer end of this spoke. */
  agentId: string
  /** Replies this phase that left or reached this agent. */
  replies: Reply[]
}
export type SpokeFlowEdge = Edge<SpokeData, 'spoke'>

const LEG_MS = 650
const PULSE_COLOR = '#ffe6a8'

/**
 * Thick orange bar from the MAGI hub to an agent. A reply travels from the
 * speaker's slab into the hub, then out along the target's spoke.
 */
export function SpokeEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps<SpokeFlowEdge>) {
  const [path] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  const replies = data?.replies ?? []
  const active = replies.length > 0

  return (
    <>
      <path
        d={path}
        fill="none"
        stroke="var(--color-signal)"
        strokeWidth={12}
        strokeOpacity={active ? 1 : 0.85}
        style={{
          filter: active ? 'drop-shadow(0 0 8px var(--color-signal))' : undefined,
          transition: 'stroke-opacity 300ms ease',
        }}
      />
      {replies.map((reply) => {
        const outbound = reply.from === data?.agentId
        return (
          <Pulse
            key={reply.key}
            d={path}
            // The path runs hub -> agent: a speaker's pulse travels it backwards.
            reverse={outbound}
            delayMs={outbound ? 0 : LEG_MS}
            durationMs={LEG_MS}
            color={PULSE_COLOR}
            radius={6}
          />
        )
      })}
    </>
  )
}
