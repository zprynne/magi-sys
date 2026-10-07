import type { AgentInfo, MagiEvent, Outcome, RunStatus, VerdictRule } from '../types/events'

export interface TraceSummary {
  trace_id: string
  question: string
  started_at: string
  verdict_rule: VerdictRule
  outcome: Outcome | null
  status: RunStatus | null
  event_count: number
  example: boolean
}

export interface ServerConfig {
  version: string
  mock: boolean
  model: string
  effort: string
  api_key_configured: boolean
  max_rounds: number
  verdict_rule: VerdictRule
  early_consensus: boolean
  agents: AgentInfo[]
  replayable: TraceSummary[]
}

export interface StartRunBody {
  question: string
  max_rounds?: number
  verdict_rule?: VerdictRule
  trace_id?: string
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json' } })
  } catch {
    throw new ApiError(0, 'Cannot reach the MAGI server. Is the backend running on port 8000?')
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = 'The request was rejected by the server.'
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export const api = {
  config: () => request<ServerConfig>('/api/config'),
  startRun: (body: StartRunBody) =>
    request<{ run_id: string }>('/api/runs', { method: 'POST', body: JSON.stringify(body) }),
  traces: () => request<TraceSummary[]>('/api/traces'),
  trace: (traceId: string) =>
    request<{ trace_id: string; events: MagiEvent[] }>(`/api/traces/${encodeURIComponent(traceId)}`),
  eventsUrl: (runId: string) => `/api/runs/${encodeURIComponent(runId)}/events`,
}
