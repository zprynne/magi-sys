import { useCallback, useEffect, useRef, useState } from 'react'

const TICK_MS = 50

/** A playhead in milliseconds that advances in real time × speed while playing. */
export function usePlayback(duration: number) {
  const [playhead, setPlayhead] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(2)
  const position = useRef(0)

  const seek = useCallback(
    (ms: number) => {
      const clamped = Math.min(Math.max(ms, 0), duration)
      position.current = clamped
      setPlayhead(clamped)
    },
    [duration],
  )

  useEffect(() => {
    if (!playing) return
    let last = performance.now()
    const id = window.setInterval(() => {
      const now = performance.now()
      const next = Math.min(position.current + (now - last) * speed, duration)
      last = now
      position.current = next
      setPlayhead(next)
      if (next >= duration) setPlaying(false)
    }, TICK_MS)
    return () => {
      window.clearInterval(id)
    }
  }, [playing, speed, duration])

  const toggle = useCallback(() => {
    if (!playing && position.current >= duration) seek(0)
    setPlaying(!playing)
  }, [playing, duration, seek])

  const pause = useCallback(() => {
    setPlaying(false)
  }, [])

  return { playhead, playing, speed, setSpeed, seek, toggle, pause }
}
