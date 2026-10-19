import { ARMS, BASELINES, CONTROL } from './arms'
import type { Reaction } from './api/simulation'
import type { Progress } from './replay'

const ARM_NAMES = new Map(
  [...ARMS, CONTROL, ...BASELINES].map((a) => [a.id, a.name] as [string, string]),
)

const armName = (arm: string) => ARM_NAMES.get(arm.toLowerCase()) ?? arm
const armClass = (arm: string) => (arm.length === 1 ? `arm-${arm.toLowerCase()}` : 'baseline')

/** One agent's reaction to one headline; the real click shows once `revealed`. */
export function ReactionCard({ event, revealed }: { event: Reaction; revealed: boolean }) {
  const pct = Math.round(event.p_click)
  return (
    <li className={`reaction-card ${armClass(event.arm)}`}>
      <p className="reaction-who">
        <span className="arm-letter" aria-hidden="true">
          {event.arm}
        </span>
        <span>
          {armName(event.arm)} <span className="muted">as reader {event.user_id}</span>
        </span>
      </p>
      <h4 className="reaction-headline">{event.headline}</h4>
      <p className="reaction-text">“{event.reaction}”</p>
      <div className="reaction-foot">
        <p className="p-click">
          <span className="p-click-label">p_click</span>
          <span className="p-click-value">{pct}%</span>
          <span className="p-click-bar" aria-hidden="true">
            <span style={{ width: `${pct}%` }} />
          </span>
        </p>
        {revealed ? (
          <p className={event.clicked ? 'reveal reveal-clicked' : 'reveal reveal-skipped'}>
            {event.clicked ? 'Real reader clicked' : 'Real reader did not click'}
          </p>
        ) : (
          <p className="reveal reveal-pending">Did the real reader click?</p>
        )}
      </div>
    </li>
  )
}

export function ArmProgressBars({ progress }: { progress: Progress[] }) {
  return (
    <ul className="arm-progress" aria-label="Progress per arm">
      {progress.map(({ arm, done, total }) => (
        <li key={arm} className={armClass(arm)}>
          <span className="arm-progress-name">
            <strong>{arm.length === 1 ? arm : ''}</strong> {armName(arm)}
          </span>
          <span
            className="arm-progress-bar"
            role="progressbar"
            aria-label={`Arm ${arm}`}
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={done}
          >
            <span style={{ width: total ? `${(100 * done) / total}%` : '0%' }} />
          </span>
          <span className="arm-progress-count">
            {done}/{total}
          </span>
        </li>
      ))}
    </ul>
  )
}
