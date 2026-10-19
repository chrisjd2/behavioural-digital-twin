import { useMemo, useState, type ReactNode } from 'react'
import type { RunEvents } from './api/simulation'
import { armClass, armName } from './arms'
import {
  COMPARISONS,
  buildComparisons,
  frameAt,
  nextReaderStart,
  startTimes,
  type Comparison,
} from './byReader'
import { SIMULATED_LABEL } from './labels'
import { duration } from './replay'
import { Timeline, Transport } from './ReplayControls'
import { useTicker } from './useTicker'

const EARLIER = 3

function Reveal({ clicked, revealed }: { clicked: boolean; revealed: boolean }) {
  if (!revealed) return <p className="reveal reveal-pending">Did the real reader click?</p>
  return (
    <p className={clicked ? 'reveal reveal-clicked' : 'reveal reveal-skipped'}>
      {clicked ? 'Real reader clicked' : 'Real reader did not click'}
    </p>
  )
}

function CurrentComparison({
  c,
  shown,
  revealed,
}: {
  c: Comparison
  shown: number
  revealed: boolean
}) {
  return (
    <article className="comparison" aria-label={`Reader ${c.user_id}`}>
      <p className="comparison-reader">Reader {c.user_id} saw this headline in their feed</p>
      <h4 className="comparison-headline">{c.headline}</h4>
      <ol className="comparison-arms" aria-label="Each arm's prediction">
        {c.reactions.slice(0, shown).map((r) => {
          const pct = Math.round(r.p_click)
          return (
            <li key={r.arm} className={`comparison-arm ${armClass(r.arm)}`}>
              <span className="arm-letter" aria-hidden="true">
                {r.arm}
              </span>
              <span className="comparison-arm-name">{armName(r.arm)}</span>
              <span className="comparison-reaction">“{r.reaction}”</span>
              <span className="p-click-value">{pct}%</span>
              <span className="p-click-bar" aria-hidden="true">
                <span style={{ width: `${pct}%` }} />
              </span>
            </li>
          )
        })}
      </ol>
      <Reveal clicked={c.clicked} revealed={revealed} />
    </article>
  )
}

function EarlierComparison({ c }: { c: Comparison }) {
  return (
    <li className="earlier">
      <p className="earlier-headline">{c.headline}</p>
      <p className="earlier-arms">
        {c.reactions.map((r) => (
          <span key={r.arm} className={armClass(r.arm)}>
            <strong>{r.arm}</strong> {Math.round(r.p_click)}%
          </span>
        ))}
      </p>
      <Reveal clicked={c.clicked} revealed />
    </li>
  )
}

type Props = { recording: RunEvents; speed: number; choices: ReactNode }

/** One reader's headline through every LLM arm, then the real click (see `byReader.ts`). */
export default function ByReaderReplay({ recording, speed, choices }: Props) {
  const { run, events, readers } = recording
  const comparisons = useMemo(
    () => buildComparisons(events, readers, run.arms),
    [events, readers, run.arms],
  )
  const starts = useMemo(() => startTimes(comparisons), [comparisons])
  const total = starts.at(-1)!
  const [elapsed, setElapsed] = useState(0)
  const [playing, setPlaying] = useState(true)
  const frame = frameAt(comparisons, starts, elapsed)
  const running = playing && !frame.finished
  useTicker(running, (dt) => setElapsed((e) => Math.min(total, e + dt * speed)))

  if (comparisons.length === 0) {
    return <p className="result-empty">This run has no LLM reactions to compare by reader.</p>
  }
  const current = comparisons[frame.index]
  const earlier = comparisons.slice(Math.max(0, frame.index - EARLIER), frame.index).reverse()

  return (
    <div className="replay-grid">
      <section className="feed" aria-label="Reactions by reader">
        <p className="simulated-label">{SIMULATED_LABEL}</p>
        <CurrentComparison c={current} shown={frame.shown} revealed={frame.revealed} />
        {earlier.length > 0 && (
          <ol className="earlier-list" aria-label="Earlier readers">
            {earlier.map((c) => (
              <EarlierComparison key={c.user_id} c={c} />
            ))}
          </ol>
        )}
      </section>

      <aside className="replay-panel" aria-label="Playback">
        <Transport
          running={running}
          finished={frame.finished}
          onToggle={() => setPlaying((p) => !p)}
          nextLabel="Next reader"
          onNext={() => setElapsed((e) => nextReaderStart(starts, e))}
          onEnd={() => setElapsed(total)}
        />
        {choices}
        <Timeline
          value={elapsed}
          max={total}
          label={
            frame.finished
              ? `Replay finished: ${comparisons.length} readers compared.`
              : `Reader ${frame.index + 1} of ${comparisons.length}, ${duration((total - elapsed) / 1000 / speed)} left`
          }
        />
        <p className="small muted order-rule">
          The first {COMPARISONS} readers in the run’s seeded sampling order. For each, alternately
          their first clicked and first unclicked headline in feed order. Chosen before looking at
          any prediction.
        </p>
      </aside>
    </div>
  )
}
