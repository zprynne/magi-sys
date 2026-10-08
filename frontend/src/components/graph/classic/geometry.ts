/**
 * Layout of the classic display: three slabs around a central "MAGI" hub.
 * One slab at the top, two below, each with a corner cut away toward the hub
 * so the three interlock. Coordinates are React Flow units; (0, 0) is near the hub.
 */

export type Slot = 'top' | 'left' | 'right'

export interface SlabShape {
  width: number
  height: number
  /** Top-left corner in flow coordinates. */
  x: number
  y: number
  /** SVG polygon points within the slab's own box. */
  points: string
  /** Padding that keeps text clear of the cut corners. */
  padding: string
}

// The cut edges run at 45° with a 36-unit channel between neighbouring slabs,
// forming the Y-shaped black gap the spokes cross.
export const SLABS: Record<Slot, SlabShape> = {
  top: {
    width: 300,
    height: 290,
    x: -150,
    y: -330,
    points: '0,0 300,0 300,220 220,290 80,290 0,220',
    padding: '24px 26px 76px',
  },
  left: {
    width: 430,
    height: 290,
    x: -470,
    y: -110,
    points: '0,0 269,0 430,161 430,290 0,290',
    padding: '22px 170px 22px 26px',
  },
  right: {
    width: 430,
    height: 290,
    x: 40,
    y: -110,
    points: '161,0 430,0 430,290 0,290 0,161',
    padding: '22px 26px 22px 170px',
  },
}

export const HUB = { width: 96, height: 40, x: -48, y: -20 }

/**
 * Which agent sits in which slot. With the default council (MELCHIOR,
 * BALTHASAR, CASPAR) this gives the show's arrangement: BALTHASAR on top,
 * CASPAR left, MELCHIOR right.
 */
export function slotFor(index: number): Slot {
  return (['right', 'top', 'left'] as const)[index] ?? 'top'
}

/** "BALTHASAR-2" -> "BALTHASAR·2", as lettered on the display. */
export function displayName(name: string): string {
  return name.replace(/-(\d+)$/, '·$1')
}

/** Small stable number for the readout's CODE field, derived from the run id. */
export function runCode(runId: string | null): string {
  if (!runId) return '---'
  let hash = 0
  for (const char of runId) hash = (hash * 31 + char.charCodeAt(0)) % 1000
  return String(hash).padStart(3, '0')
}
