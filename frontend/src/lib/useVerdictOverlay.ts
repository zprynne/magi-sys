import { useCallback, useState } from 'react'
import type { Verdict } from '../types/events'

/**
 * Open the verdict screen whenever a verdict appears, until dismissed. If the
 * verdict disappears again (scrubbing a replay backwards), the dismissal is
 * forgotten so the reveal plays again on the way forward.
 */
export function useVerdictOverlay(verdict: Verdict | null) {
  const key = verdict ? `${verdict.run_id}:${String(verdict.seq)}` : null
  const [dismissed, setDismissed] = useState<string | null>(null)
  if (key === null && dismissed !== null) setDismissed(null)

  const close = useCallback(() => {
    setDismissed(key)
  }, [key])
  const reopen = useCallback(() => {
    setDismissed(null)
  }, [])

  return { open: key !== null && dismissed !== key, close, reopen }
}
