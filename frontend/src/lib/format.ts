import type { Outcome, Stance, VoteChoice } from '../types/events'

export function elapsed(fromIso: string | null, toIso: string | null): number {
  if (!fromIso || !toIso) return 0
  return Math.max(0, Date.parse(toIso) - Date.parse(fromIso))
}

export function clock(ms: number): string {
  const total = Math.floor(ms / 1000)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

type Signal = Stance | VoteChoice | Outcome

/** Text colour class for a stance, vote or outcome. */
export function signalText(value: Signal | null | undefined): string {
  switch (value) {
    case 'APPROVE':
    case 'APPROVED':
      return 'text-phosphor'
    case 'DENY':
    case 'DENIED':
      return 'text-alarm'
    case 'DEADLOCK':
      return 'text-signal'
    default:
      return 'text-neutral'
  }
}

export function signalColor(value: Signal | null | undefined): string {
  switch (value) {
    case 'APPROVE':
    case 'APPROVED':
      return 'var(--color-phosphor)'
    case 'DENY':
    case 'DENIED':
      return 'var(--color-alarm)'
    case 'DEADLOCK':
      return 'var(--color-signal)'
    default:
      return 'var(--color-neutral)'
  }
}

export function stanceLabel(stance: Stance): string {
  return stance === 'UNDECIDED' ? 'Undecided' : stance === 'APPROVE' ? 'Leaning approve' : 'Leaning deny'
}

export function ruleLabel(rule: string, rounds: number): string {
  const ruleText = rule === 'unanimous' ? 'Unanimous rule' : 'Majority rule'
  const roundText = rounds === 1 ? '1 debate round' : `${rounds} debate rounds`
  return `${ruleText}, up to ${roundText}`
}

/** "mlx-community/Qwen3-8B-4bit" -> "Qwen3-8B-4bit"; "claude-opus-5-5" unchanged. */
export function shortModel(model: string): string {
  return model.split('/').pop() ?? model
}
