import { useEffect, useState } from 'react'
import { fetchRunEvents, type Reaction, type RunEvents } from './api/simulation'
import { SIMULATED_LABEL } from './labels'
import LiveRunPanel from './LiveRunPanel'
import { ArmProgressBars, ReactionCard } from './ReactionFeed'
import {
  SPEEDS,
  armProgress,
  isRevealed,
  nextArmStart,
  playbackSeconds,
  skipTo,
  start,
  tick,
  type Playback,
} from './replay'
import './simulation.css'

const FRAME_MS = 50

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; recording: RunEvents }

type Props = {
  runId: string | undefined // none: there are no saved runs yet
  liveRuns: boolean // false in DEMO_MODE (ADR-0011)
  onLiveRunSaved: (runId: string) => void
}

const minutes = (seconds: number) =>
  seconds < 90 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`

/**
 * Step 3: replay a saved run's reactions. Events are fetched once; playback needs no network
 * (ADR-0008). Render with `key={runId}` so a new run starts from the beginning.
 */
export default function SimulationStep({ runId, liveRuns, onLiveRunSaved }: Props) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })

  useEffect(() => {
    if (!runId) return
    let current = true
    fetchRunEvents(runId)
      .then((recording) => current && setLoad({ state: 'ready', recording }))
      .catch(
        (error: unknown) =>
          current &&
          setLoad({
            state: 'error',
            message: error instanceof Error ? error.message : 'The request failed.',
          }),
      )
    return () => {
      current = false
    }
  }, [runId])

  const live = liveRuns && <LiveRunPanel onSaved={onLiveRunSaved} />
  if (!runId) return live
  if (load.state === 'loading') return <p className="muted">Loading the recorded run…</p>
  if (load.state === 'error') {
    return (
      <>
        <p role="alert" className="result-error">
          Could not load this run’s events: {load.message}
        </p>
        {live}
      </>
    )
  }
  const { recording } = load
  return (
    <>
      {recording.events.length === 0 ? (
        <p className="result-empty">This run has no recorded events to replay.</p>
      ) : (
        <Replay recording={recording} />
      )}
      {live}
    </>
  )
}

function Replay({ recording }: { recording: RunEvents }) {
  const { run, events } = recording
  const [playback, setPlayback] = useState<Playback>(start)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(1)
  const running = playing && !playback.finished

  useEffect(() => {
    if (!running) return
    let last = Date.now()
    const timer = setInterval(() => {
      const now = Date.now()
      const dt = now - last
      last = now
      setPlayback((state) => tick(state, dt, events, speed))
    }, FRAME_MS)
    return () => clearInterval(timer)
  }, [running, events, speed])

  const played = Math.floor(playback.position)
  const left = playbackSeconds(events.length, speed, playback.position)
  const total = playbackSeconds(events.length, speed)

  return (
    <div className="simulation">
      <div className="replay-labels">
        <p className="recorded-label">
          <strong>Recorded run, sped up.</strong> It took {minutes(recording.recorded_seconds)}; it
          plays back in about {minutes(total)} at {speed}×.
        </p>
        {run.mock && (
          <p className="mock-note">
            <span className="badge-mock">MOCK</span> Fake LLM output. Not results.
          </p>
        )}
        {run.data_source === 'synthetic' && (
          <p className="notice">Synthetic sample: these readers are fake.</p>
        )}
      </div>

      <div className="replay-grid">
        <section className="feed" aria-labelledby="feed-title">
          <h3 id="feed-title" className="visually-hidden">
            Reactions
          </h3>
          <p className="simulated-label">{SIMULATED_LABEL}</p>
          {playback.cards.length === 0 ? (
            <p className="muted feed-waiting">The first agent is reading its feed…</p>
          ) : (
            <ol className="reaction-feed" aria-label="Reactions">
              {[...playback.cards].reverse().map((card) => (
                <ReactionCard
                  key={card.index}
                  event={events[card.index] as Reaction}
                  revealed={isRevealed(card, playback.clock)}
                />
              ))}
            </ol>
          )}
        </section>

        <aside className="replay-panel" aria-label="Playback">
          <div className="transport">
            <button
              type="button"
              className="primary"
              disabled={playback.finished}
              onClick={() => setPlaying((p) => !p)}
            >
              {running ? 'Pause' : 'Play'}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={playback.finished}
              onClick={() =>
                setPlayback((s) => skipTo(s, nextArmStart(events, s.position), events))
              }
            >
              Skip to next arm
            </button>
            <button
              type="button"
              className="secondary"
              disabled={playback.finished}
              onClick={() => setPlayback((s) => skipTo(s, events.length, events))}
            >
              Skip to end
            </button>
          </div>

          <fieldset className="speeds">
            <legend className="field-label">Speed</legend>
            {SPEEDS.map((s) => (
              <label key={s} className={s === speed ? 'speed speed-on' : 'speed'}>
                <input
                  type="radio"
                  name="speed"
                  value={s}
                  checked={s === speed}
                  onChange={() => setSpeed(s)}
                />
                {s}×
              </label>
            ))}
          </fieldset>

          <div className="timeline">
            <span
              className="timeline-bar"
              role="progressbar"
              aria-label="Replay"
              aria-valuemin={0}
              aria-valuemax={events.length}
              aria-valuenow={played}
            >
              <span style={{ width: `${(100 * playback.position) / events.length}%` }} />
            </span>
            <p className="small muted">
              {playback.finished
                ? 'Replay finished: every recorded event played.'
                : `${played.toLocaleString()} of ${events.length.toLocaleString()} events, ${minutes(left)} left`}
            </p>
          </div>

          <h3 className="panel-title">Agents done, per arm</h3>
          <ArmProgressBars progress={armProgress(events, played, run.arms, run.n_users)} />
        </aside>
      </div>
    </div>
  )
}
