import { currentStepKey, phaseSteps, type DeliberationView } from '../state/deliberation'

type StepState = 'done' | 'current' | 'upcoming' | 'skipped'

export function PhaseTrack({ view }: { view: DeliberationView }) {
  const maxRounds = view.config?.max_rounds ?? 2
  const steps = phaseSteps(maxRounds)
  const currentKey = currentStepKey(view)
  const currentIndex = steps.findIndex((s) => s.key === currentKey)
  const finished = view.completed !== null && view.fatal === null

  function stateOf(index: number): StepState {
    const step = steps[index]
    if (!step) return 'upcoming'
    const pastDebate = view.phase === 'vote' || view.phase === 'verdict'
    if (step.phase === 'debate' && pastDebate && (step.round ?? 0) > view.roundsRun) return 'skipped'
    if (finished && index <= currentIndex) return 'done'
    if (index < currentIndex) return 'done'
    if (index === currentIndex) return 'current'
    return 'upcoming'
  }

  return (
    <ol className="flex w-full items-stretch gap-1" aria-label="Deliberation phases">
      {steps.map((step, index) => {
        const state = stateOf(index)
        return (
          <li
            key={step.key}
            className="flex min-w-0 flex-1 flex-col gap-1.5"
            aria-current={state === 'current' ? 'step' : undefined}
            title={state === 'skipped' ? 'Skipped: the council reached consensus early' : undefined}
          >
            <span
              className={`h-[3px] ${
                state === 'current'
                  ? 'bg-signal shadow-[0_0_8px_var(--color-signal)]'
                  : state === 'done'
                    ? 'bg-phosphor/50'
                    : 'bg-line'
              }`}
            />
            <span
              className={`truncate font-mono text-[11px] ${
                state === 'current'
                  ? 'text-signal'
                  : state === 'done'
                    ? 'text-dim'
                    : state === 'skipped'
                      ? 'text-faint line-through'
                      : 'text-faint'
              }`}
            >
              {step.label}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
