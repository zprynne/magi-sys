import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  useStore,
  type EdgeTypes,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo } from 'react'
import type { DeliberationView } from '../../state/deliberation'
import { AGENT_NODE_HEIGHT, AGENT_NODE_WIDTH, AgentNode, type AgentFlowNode } from './AgentNode'
import { ConduitEdge, type ConduitFlowEdge } from './ConduitEdge'
import { CORE_NODE_SIZE, CoreNode, type CoreFlowNode } from './CoreNode'
import { ClassicAgentNode, type ClassicAgentFlowNode } from './classic/ClassicAgentNode'
import { ClassicHubNode, type ClassicHubFlowNode } from './classic/ClassicHubNode'
import { ClassicReadout } from './classic/ClassicReadout'
import { HUB, SLABS, slotFor } from './classic/geometry'
import { SpokeEdge, type SpokeFlowEdge } from './classic/SpokeEdge'
import { useTheme } from '../../lib/theme'

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  core: CoreNode,
  classicAgent: ClassicAgentNode,
  classicHub: ClassicHubNode,
}
const edgeTypes: EdgeTypes = { conduit: ConduitEdge, spoke: SpokeEdge }

type CouncilNode = AgentFlowNode | CoreFlowNode | ClassicAgentFlowNode | ClassicHubFlowNode
type CouncilEdge = ConduitFlowEdge | SpokeFlowEdge

const FIXED = { draggable: false, selectable: false, focusable: false } as const

/** The classic display: slabs around the MAGI hub, joined by spokes. */
function classicGraph(view: DeliberationView): { nodes: CouncilNode[]; edges: CouncilEdge[] } {
  const sealed = view.verdict === null
  const nodes: CouncilNode[] = [
    { id: 'hub', type: 'classicHub', position: { x: HUB.x, y: HUB.y }, data: {}, ...FIXED },
  ]
  const edges: CouncilEdge[] = []
  view.agents.forEach((info, index) => {
    const agent = view.byAgent[info.id]
    if (!agent) return
    const slot = slotFor(index)
    const shape = SLABS[slot]
    nodes.push({
      id: info.id,
      type: 'classicAgent',
      position: { x: shape.x, y: shape.y },
      data: { agent, sealed, slot },
      ...FIXED,
    })
    edges.push({
      id: `hub--${info.id}`,
      source: 'hub',
      target: info.id,
      type: 'spoke',
      ...FIXED,
      data: {
        agentId: info.id,
        replies: view.replies.filter((r) => r.from === info.id || r.to === info.id),
      },
    })
  })
  return { nodes, edges }
}

const RADIUS = 318
const FIT_PADDING = 0.05

/** Agents sit on a circle, the first at the top; three agents form the triangle. */
function agentCenter(index: number, count: number): { x: number; y: number } {
  const angle = ((-90 - (index * 360) / count) * Math.PI) / 180
  return { x: Math.cos(angle) * RADIUS, y: Math.sin(angle) * RADIUS * 0.92 }
}

function FitOnResize({ nodeCount, layoutKey }: { nodeCount: number; layoutKey: string }) {
  const { fitView } = useReactFlow()
  const width = useStore((s) => s.width)
  const height = useStore((s) => s.height)
  // Wait until React Flow has measured the current nodes, or a theme switch
  // would fit the old layout's bounds.
  const measured = useNodesInitialized()
  useEffect(() => {
    if (measured && width > 0 && height > 0 && nodeCount > 0) {
      void fitView({ padding: FIT_PADDING, duration: 0 })
    }
  }, [fitView, measured, width, height, nodeCount, layoutKey])
  return null
}

export function CouncilGraph({ view }: { view: DeliberationView }) {
  const { agents } = view
  const { theme } = useTheme()
  const classic = theme === 'classic' && agents.length === 3

  const consoleNodes = useMemo<(AgentFlowNode | CoreFlowNode)[]>(() => {
    const sealed = view.verdict === null
    const agentNodes: AgentFlowNode[] = agents.flatMap((info, index) => {
      const agent = view.byAgent[info.id]
      if (!agent) return []
      const center = agentCenter(index, agents.length)
      return {
        id: info.id,
        type: 'agent',
        position: { x: center.x - AGENT_NODE_WIDTH / 2, y: center.y - AGENT_NODE_HEIGHT / 2 },
        data: { agent, sealed },
        draggable: false,
        selectable: false,
        focusable: false,
      }
    })
    const core: CoreFlowNode = {
      id: 'core',
      type: 'core',
      position: { x: -CORE_NODE_SIZE / 2, y: -CORE_NODE_SIZE / 2 + 18 },
      data: {
        phase: view.phase,
        round: view.round,
        maxRounds: view.config?.max_rounds ?? 0,
        votesCast: view.votes.length,
        electorate: agents.length,
        outcome: view.verdict?.outcome ?? null,
        halted: view.fatal !== null,
      },
      draggable: false,
      selectable: false,
      focusable: false,
    }
    return [...agentNodes, core]
  }, [agents, view.byAgent, view.phase, view.round, view.config, view.votes, view.verdict, view.fatal])

  const consoleEdges = useMemo<ConduitFlowEdge[]>(() => {
    const colors = Object.fromEntries(agents.map((a) => [a.id, a.color]))
    const result: ConduitFlowEdge[] = []
    agents.forEach((a, i) => {
      agents.slice(i + 1).forEach((b) => {
        result.push({
          id: `${a.id}--${b.id}`,
          source: a.id,
          target: b.id,
          type: 'conduit',
          selectable: false,
          focusable: false,
          data: {
            colors,
            replies: view.replies.filter(
              (r) => (r.from === a.id && r.to === b.id) || (r.from === b.id && r.to === a.id),
            ),
          },
        })
      })
    })
    return result
  }, [agents, view.replies])

  const classicLayout = useMemo(
    () => (classic ? classicGraph(view) : null),
    [classic, view],
  )
  const nodes: CouncilNode[] = classicLayout?.nodes ?? consoleNodes
  const edges: CouncilEdge[] = classicLayout?.edges ?? consoleEdges

  return (
    <ReactFlowProvider>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: FIT_PADDING }}
        minZoom={0.3}
        maxZoom={classic ? 2 : 1.15}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        aria-label="Council graph"
      >
        {classic ? (
          <ClassicReadout view={view} />
        ) : (
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="var(--color-line)" />
        )}
        <FitOnResize nodeCount={nodes.length} layoutKey={classic ? 'classic' : 'console'} />
      </ReactFlow>
    </ReactFlowProvider>
  )
}
