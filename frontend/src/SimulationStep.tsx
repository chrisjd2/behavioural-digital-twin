import { useEffect, useState, type ReactNode } from 'react'
import { fetchRunEvents, type Reaction, type RunEvents } from './api/simulation'
import ByReaderReplay from './ByReaderReplay'
import { SIMULATED_LABEL } from './labels'
import LiveRunPanel from './LiveRunPanel'
import { ArmProgressBars, ReactionCard } from './ReactionFeed'
import {
  ORDER_OPTIONS,
  SPEED_OPTIONS,
  armProgress,
  duration,
  isRevealed,
  nextArmStart,
  playbackSeconds,
  skipTo,
  start,
  tick,
  type Order,
  type Playback,
} from './replay'
import { Choice, Timeline, Transport } from './ReplayControls'
import './simulation.css'
import { useTicker } from './useTicker'

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; recording: RunEvents }

type Props = {
  runId: string | undefined // none: there are no saved runs yet
  liveRuns: boolean // false in DEMO_MODE (ADR-0011)
  mockLlm: boolean // the server's MOCK_LLM, for the live-run note
  onLiveRunSaved: (runId: string) => void
}

/**
 * Step 3: replay a saved run's reactions. Events are fetched once; playback needs no network
 * (ADR-0008). Render with `key={runId}` so a new run starts from the beginning.
 */
export default function SimulationStep({ runId, liveRuns, mockLlm, onLiveRunSaved }: Props) {
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

  const live = liveRuns && <LiveRunPanel onSaved={onLiveRunSaved} mockLlm={mockLlm} />
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
  const { run } = recording
  const [order, setOrder] = useState<Order>('reader')
  const [speed, setSpeed] = useState(1)
  const choices = (
    <>
      <Choice
        legend="Order"
        name="order"
        options={ORDER_OPTIONS}
        value={order}
        onChange={setOrder}
      />
      <Choice
        legend="Speed"
        name="speed"
        options={SPEED_OPTIONS}
        value={speed}
        onChange={setSpeed}
      />
    </>
  )
  return (
    <div className="simulation">
      <div className="replay-labels">
        {order === 'reader' ? (
          <p className="recorded-label">
            <strong>Recorded run, sped up and reordered by reader</strong> (seeded order, not
            cherry-picked).
          </p>
        ) : (
          <p className="recorded-label">
            <strong>Recorded run, sped up.</strong> It took {duration(recording.recorded_seconds)};
            it plays back in about {duration(playbackSeconds(recording.events.length, speed))} at{' '}
            {speed}×.
          </p>
        )}
        {run.mock && (
          <p className="mock-note">
            <span className="badge-mock">MOCK</span> Fake LLM output. Not results.
          </p>
        )}
        {run.data_source === 'synthetic' && (
          <p className="notice">Synthetic sample: these readers are fake.</p>
        )}
      </div>
      {order === 'reader' ? (
        <ByReaderReplay recording={recording} speed={speed} choices={choices} />
      ) : (
        <ByArmReplay recording={recording} speed={speed} choices={choices} />
      )}
    </div>
  )
}

type ModeProps = { recording: RunEvents; speed: number; choices: ReactNode }

/** The recorded order: arm A for every reader, then B, and so on. */
function ByArmReplay({ recording, speed, choices }: ModeProps) {
  const { run, events } = recording
  const [playback, setPlayback] = useState<Playback>(start)
  const [playing, setPlaying] = useState(true)
  const running = playing && !playback.finished
  useTicker(running, (dt) => setPlayback((state) => tick(state, dt, events, speed)))

  const played = Math.floor(playback.position)
  const left = playbackSeconds(events.length, speed, playback.position)

  return (
    <div className="replay-grid">
      <section className="feed" aria-label="Reactions feed">
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
        <Transport
          running={running}
          finished={playback.finished}
          onToggle={() => setPlaying((p) => !p)}
          nextLabel="Skip to next arm"
          onNext={() => setPlayback((s) => skipTo(s, nextArmStart(events, s.position), events))}
          onEnd={() => setPlayback((s) => skipTo(s, events.length, events))}
        />
        {choices}
        <Timeline
          value={playback.position}
          max={events.length}
          label={
            playback.finished
              ? 'Replay finished: every recorded event played.'
              : `${played.toLocaleString()} of ${events.length.toLocaleString()} events, ${duration(left)} left`
          }
        />
        <h3 className="panel-title">Agents done, per arm</h3>
        <ArmProgressBars progress={armProgress(events, played, run.arms, run.n_users)} />
      </aside>
    </div>
  )
}
