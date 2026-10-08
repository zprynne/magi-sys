import { kanjiFor } from '../../../lib/theme'
import type { DeliberationView } from '../../../state/deliberation'
import { runCode } from './geometry'

function phaseText(view: DeliberationView): string {
  switch (view.phase) {
    case null:
      return 'STANDBY'
    case 'opening':
      return 'OPENING'
    case 'debate':
      return `DEBATE ${String(view.round ?? 1)}/${String(view.config?.max_rounds ?? 0)}`
    case 'vote':
      return 'VOTE'
    case 'verdict':
      return view.verdict ? 'CLOSED' : 'TALLY'
  }
}

const KANJI_FONT = "font-kanji"

/** Orange status text in the corners of the classic display. */
export function ClassicReadout({ view }: { view: DeliberationView }) {
  const rule = (view.config?.verdict_rule ?? 'majority').toUpperCase()
  const outcome = view.verdict?.outcome

  return (
    <>
      <div className="pointer-events-none absolute top-4 left-4 z-10 font-mono text-signal md:left-6">
        <div className="flex items-end gap-3 border-b-2 border-double border-signal/70 pb-1">
          <span className={`${KANJI_FONT} text-[34px] leading-none font-[700]`} lang="ja">
            提訴
          </span>
          <span className="text-[22px] leading-none font-[800]">CODE:{runCode(view.runId)}</span>
        </div>
        <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-1 text-[11px] leading-snug font-[600] tracking-[0.06em]">
          <dt>FILE:</dt>
          <dd>MAGI_SYS</dd>
          <dt>PHASE:</dt>
          <dd>{phaseText(view)}</dd>
          <dt>RULE:</dt>
          <dd>{rule}</dd>
          <dt>PRIORITY:</dt>
          <dd>AAA</dd>
        </dl>
      </div>

      <div className="pointer-events-none absolute top-4 right-4 z-10 text-right text-signal md:right-6">
        <div className="border-b-2 border-double border-signal/70 pb-1">
          <span className={`${KANJI_FONT} text-[34px] leading-none font-[700]`} lang="ja">
            決議
          </span>
        </div>
        <p className="mt-1.5 font-mono text-[13px] font-[800] tracking-[0.08em]">
          {outcome ? (
            <>
              <span className={`${KANJI_FONT} mr-2 text-[18px]`} lang="ja">
                {kanjiFor(outcome)}
              </span>
              {outcome}
            </>
          ) : view.runId ? (
            'IN SESSION'
          ) : (
            'AWAITING PROPOSAL'
          )}
        </p>
      </div>
    </>
  )
}
