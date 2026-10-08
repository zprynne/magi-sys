import { Handle, Position, type Node } from '@xyflow/react'
import { HUB } from './geometry'

export type ClassicHubFlowNode = Node<Record<string, never>, 'classicHub'>

const centered = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' } as const

/** The "MAGI" label where the three spokes meet. */
export function ClassicHubNode() {
  return (
    <div
      className="grid place-items-center bg-black"
      style={{ width: HUB.width, height: HUB.height }}
    >
      <Handle type="source" position={Position.Top} style={centered} isConnectable={false} />
      <span className="font-hub text-[26px] font-[700] tracking-[0.04em] text-signal">
        MAGI
      </span>
    </div>
  )
}
