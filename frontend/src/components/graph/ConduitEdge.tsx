import { BaseEdge, getStraightPath, type Edge, type EdgeProps } from '@xyflow/react'
import { useEffect, useRef } from 'react'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import type { Reply } from '../../state/deliberation'

export type ConduitData = {
  /** Replies exchanged along this conduit in the current phase. */
  replies: Reply[]
  colors: Record<string, string>
}
export type ConduitFlowEdge = Edge<ConduitData, 'conduit'>

const PULSE_MS = 1500

/** A dot that travels the conduit once, from the speaker to the agent answered. */
function Pulse({ d, reverse, color }: { d: string; reverse: boolean; color: string }) {
  const pathRef = useRef<SVGPathElement>(null)
  const dotRef = useRef<SVGCircleElement>(null)
  const reducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    const path = pathRef.current
    const dot = dotRef.current
    if (!path || !dot || reducedMotion) return
    const length = path.getTotalLength()
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const t = Math.min((now - start) / PULSE_MS, 1)
      const eased = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2
      const point = path.getPointAtLength((reverse ? 1 - eased : eased) * length)
      dot.setAttribute('cx', String(point.x))
      dot.setAttribute('cy', String(point.y))
      dot.style.opacity = String(t < 0.85 ? 1 : (1 - t) / 0.15)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frame)
    }
  }, [d, reverse, reducedMotion])

  return (
    <g>
      <path ref={pathRef} d={d} fill="none" stroke="none" />
      <circle ref={dotRef} r={5} fill={color} style={{ opacity: 0, filter: `drop-shadow(0 0 6px ${color})` }} />
    </g>
  )
}

export function ConduitEdge({ id, source, sourceX, sourceY, targetX, targetY, data }: EdgeProps<ConduitFlowEdge>) {
  const [path] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  const replies = data?.replies ?? []
  const last = replies.at(-1)
  const litColor = last ? (data?.colors[last.from] ?? 'var(--color-signal)') : null

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{ stroke: 'var(--color-line-bright)', strokeWidth: 1.5, strokeDasharray: '2 7' }}
      />
      {litColor && (
        <path
          d={path}
          fill="none"
          stroke={litColor}
          strokeWidth={2.5}
          strokeOpacity={0.85}
          style={{ filter: `drop-shadow(0 0 5px ${litColor})`, transition: 'stroke 300ms ease' }}
        />
      )}
      {replies.map((reply) => (
        <Pulse
          key={reply.key}
          d={path}
          reverse={reply.from !== source}
          color={data?.colors[reply.from] ?? 'var(--color-signal)'}
        />
      ))}
    </>
  )
}
