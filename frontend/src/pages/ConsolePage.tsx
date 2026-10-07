import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CouncilGraph } from '../components/graph/CouncilGraph'
import { PhaseTrack } from '../components/PhaseTrack'
import { ProposalForm, type Proposal } from '../components/ProposalForm'
import { ActionButton, RunHeader } from '../components/RunHeader'
import { Transcript } from '../components/transcript/Transcript'
import { VerdictScreen } from '../components/verdict/VerdictScreen'
import { api, ApiError } from '../lib/api'
import { useServerConfig } from '../lib/config'
import { elapsed } from '../lib/format'
import { useNow } from '../lib/useNow'
import { useRunStream, type StreamStatus } from '../lib/useRunStream'
import { deriveView, isRunning, type DeliberationView } from '../state/deliberation'

function StreamBadge({ status, view }: { status: StreamStatus; view: DeliberationView }) {
  if (view.fatal) return <span className="font-mono text-[12px] text-alarm">Failed</span>
  if (view.completed) return <span className="font-mono text-[12px] text-phosphor">Complete</span>
  const text: Record<StreamStatus, string> = {
    idle: '',
    connecting: 'Connecting',
    live: 'Live',
    reconnecting: 'Reconnecting',
    closed: 'Complete',
    error: 'Run not found',
  }
  const tone = status === 'error' ? 'text-alarm' : status === 'live' ? 'text-phosphor' : 'text-signal'
  return (
    <span className={`flex items-center gap-1.5 font-mono text-[12px] ${tone}`}>
      {status === 'live' && <span className="size-1.5 animate-blink rounded-full bg-phosphor" aria-hidden />}
      {text[status]}
    </span>
  )
}

export function ConsolePage() {
  const { runId = null } = useParams()
  const navigate = useNavigate()
  const { config, error: configError, reload } = useServerConfig()
  const stream = useRunStream(runId)
  const view = useMemo(() => deriveView(stream.events, config?.agents ?? []), [stream.events, config])
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  const [dismissedVerdict, setDismissedVerdict] = useState<string | null>(null)
  const verdictOpen = view.verdict !== null && dismissedVerdict !== view.runId
  const closeVerdict = useCallback(() => {
    setDismissedVerdict(view.runId)
  }, [view.runId])

  const running = isRunning(view)
  const now = useNow(running)
  const elapsedMs = elapsed(view.startedAt, running ? new Date(now).toISOString() : view.lastEventAt)

  async function convene(proposal: Proposal) {
    setStarting(true)
    setStartError(null)
    try {
      const { run_id } = await api.startRun({
        question: proposal.question,
        max_rounds: proposal.maxRounds,
        verdict_rule: proposal.rule,
        trace_id: proposal.traceId,
      })
      void navigate(`/run/${run_id}`)
    } catch (err) {
      setStartError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setStarting(false)
    }
  }

  const proposal = (
    <section className="px-4 py-5 md:px-6">
      {config ? (
        <ProposalForm config={config} busy={starting} error={startError} onSubmit={(p) => void convene(p)} />
      ) : configError ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-[14px] text-alarm">{configError}</p>
          <ActionButton onClick={reload}>Retry</ActionButton>
        </div>
      ) : (
        <p className="font-mono text-[12px] text-dim">Connecting to the MAGI server</p>
      )}
    </section>
  )

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(360px,30%)]">
      <div className="flex min-h-0 flex-col">
        {runId && (
          <RunHeader
            view={view}
            elapsedMs={elapsedMs}
            status={<StreamBadge status={stream.status} view={view} />}
            actions={
              view.completed && (
                <>
                  {view.verdict && !verdictOpen && (
                    <ActionButton
                      onClick={() => {
                        setDismissedVerdict(null)
                      }}
                    >
                      Show verdict
                    </ActionButton>
                  )}
                  {!view.config?.mock && (
                    <ActionButton onClick={() => void navigate(`/replay/${runId}`)}>Open in replays</ActionButton>
                  )}
                  <ActionButton primary onClick={() => void navigate('/')}>
                    New deliberation
                  </ActionButton>
                </>
              )
            }
          />
        )}
        {!runId && <div className="border-b border-line lg:hidden">{proposal}</div>}

        {view.fatal && (
          <p className="border-b border-alarm/50 bg-alarm/10 px-4 py-2 text-[14px] text-alarm md:px-6">
            The run stopped: {view.fatal.message}
          </p>
        )}
        {stream.status === 'error' && !view.runId && (
          <p className="border-b border-alarm/50 bg-alarm/10 px-4 py-2 text-[14px] text-alarm md:px-6">
            This run is not on the server. It may have been started before a restart; check Replays.
          </p>
        )}

        <div className="relative h-[600px] min-h-0 lg:h-auto lg:flex-1">
          {view.agents.length > 0 && <CouncilGraph view={view} />}
        </div>
        <div className="border-t border-line px-4 py-3 md:px-6">
          <PhaseTrack view={view} />
        </div>
      </div>

      {verdictOpen && view.verdict && (
        <VerdictScreen
          question={view.question ?? ''}
          verdict={view.verdict}
          votes={view.votes}
          agents={view.agents}
          onClose={closeVerdict}
        />
      )}

      <aside className="flex min-h-0 flex-col border-t border-line lg:border-t-0 lg:border-l">
        {runId ? (
          <Transcript events={stream.events} view={view} />
        ) : (
          <div className="console-scroll hidden min-h-0 flex-1 overflow-y-auto lg:block">{proposal}</div>
        )}
      </aside>
    </div>
  )
}
