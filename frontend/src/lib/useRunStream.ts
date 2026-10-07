import { useEffect, useReducer } from 'react'
import { isMagiEvent, type MagiEvent } from '../types/events'
import { api } from './api'

export type StreamStatus = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'closed' | 'error'

interface StreamState {
  runId: string | null
  events: MagiEvent[]
  status: StreamStatus
}

type Action =
  | { kind: 'reset'; runId: string | null }
  | { kind: 'status'; status: StreamStatus }
  | { kind: 'event'; event: MagiEvent }

function reducer(state: StreamState, action: Action): StreamState {
  switch (action.kind) {
    case 'reset':
      return { runId: action.runId, events: [], status: action.runId ? 'connecting' : 'idle' }
    case 'status':
      return { ...state, status: action.status }
    case 'event': {
      const last = state.events.at(-1)
      if (last && action.event.seq <= last.seq) return state // replayed after reconnect
      const done = action.event.type === 'run_completed'
      return { ...state, events: [...state.events, action.event], status: done ? 'closed' : 'live' }
    }
  }
}

/**
 * Follow a run's event stream over SSE. The server buffers every event, so
 * opening this for a run that is already underway (or finished) replays it
 * from the start; EventSource resumes with Last-Event-ID after a drop.
 */
export function useRunStream(runId: string | null): StreamState {
  const [state, dispatch] = useReducer(reducer, {
    runId,
    events: [],
    status: runId ? 'connecting' : 'idle',
  })

  useEffect(() => {
    dispatch({ kind: 'reset', runId })
    if (!runId) return

    const source = new EventSource(api.eventsUrl(runId))
    let finished = false

    source.onopen = () => {
      dispatch({ kind: 'status', status: 'live' })
    }
    source.onmessage = (message: MessageEvent<string>) => {
      const parsed: unknown = JSON.parse(message.data)
      if (!isMagiEvent(parsed)) return
      dispatch({ kind: 'event', event: parsed })
      if (parsed.type === 'run_completed') {
        finished = true
        source.close()
      }
    }
    source.onerror = () => {
      if (finished) return
      // CONNECTING means the browser is retrying; CLOSED means it gave up (e.g. 404).
      const status = source.readyState === EventSource.CLOSED ? 'error' : 'reconnecting'
      dispatch({ kind: 'status', status })
    }

    return () => {
      source.close()
    }
  }, [runId])

  return state.runId === runId ? state : { runId, events: [], status: runId ? 'connecting' : 'idle' }
}
