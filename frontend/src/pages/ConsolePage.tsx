import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CouncilLayout, Notice } from '../components/CouncilLayout'
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
import { useVerdictOverlay } from '../lib/useVerdictOverlay'
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
  const verdict = useVerdictOverlay(view.verdict)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

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

  const top = (
    <>
      {runId ? (
        <RunHeader
          view={view}
          elapsedMs={elapsedMs}
          status={<StreamBadge status={stream.status} view={view} />}
          actions={
            view.completed && (
              <>
                {view.verdict && !verdict.open && <ActionButton onClick={verdict.reopen}>Show verdict</ActionButton>}
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
      ) : (
        <div className="border-b border-line lg:hidden">{proposal}</div>
      )}
      {view.fatal && <Notice>The run stopped: {view.fatal.message}</Notice>}
      {stream.status === 'error' && !view.runId && (
        <Notice>This run is not on the server. It may have been started before a restart; check Replays.</Notice>
      )}
    </>
  )

  return (
    <CouncilLayout
      view={view}
      top={top}
      bottom={<PhaseTrack view={view} />}
      aside={
        runId ? (
          <Transcript events={stream.events} view={view} />
        ) : (
          <div className="console-scroll hidden min-h-0 flex-1 overflow-y-auto lg:block">{proposal}</div>
        )
      }
    >
      {verdict.open && view.verdict && (
        <VerdictScreen
          question={view.question ?? ''}
          verdict={view.verdict}
          votes={view.votes}
          agents={view.agents}
          onClose={verdict.close}
        />
      )}
    </CouncilLayout>
  )
}
