import { useEffect, useRef, useState } from 'react'
import { followLiveRun, startLiveRun, type Reaction, type RunEvent } from './api/simulation'
import { ArmProgressBars, ReactionCard } from './ReactionFeed'
import { armProgress } from './replay'

const LIVE_USERS = 10
const SHOWN = 3

type Live =
  | { state: 'idle' }
  | { state: 'starting' }
  | { state: 'running'; events: RunEvent[] }
  | { state: 'error'; message: string; events: RunEvent[] }

/**
 * Developers only: run every arm on a few dev readers and watch it over SSE. Hidden in
 * DEMO_MODE (ADR-0011); the API never runs the test population here. A saved run is replayed.
 */
export default function LiveRunPanel({ onSaved }: { onSaved: (runId: string) => void }) {
  const [live, setLive] = useState<Live>({ state: 'idle' })
  const stop = useRef<() => void>(undefined)
  useEffect(() => () => stop.current?.(), [])

  function begin() {
    setLive({ state: 'starting' })
    startLiveRun({ n_users: LIVE_USERS })
      .then(({ live_id }) => {
        setLive({ state: 'running', events: [] })
        stop.current = followLiveRun(live_id, {
          onEvent: (event) =>
            setLive((l) => (l.state === 'running' ? { ...l, events: [...l.events, event] } : l)),
          onSaved: ({ run_id }) => onSaved(run_id),
          onFailed: (message) =>
            setLive((l) => ({
              state: 'error',
              message,
              events: l.state === 'running' ? l.events : [],
            })),
        })
      })
      .catch((error: unknown) =>
        setLive({
          state: 'error',
          message: error instanceof Error ? error.message : 'The live run did not start.',
          events: [],
        }),
      )
  }

  const events = 'events' in live ? live.events : []
  const arms = [...new Set(events.flatMap((e) => ('arm' in e ? [e.arm] : [])))]
  const reactions = events.filter((e): e is Reaction => e.kind === 'reaction').slice(-SHOWN)

  return (
    <section className="live-run" aria-labelledby="live-title">
      <h3 id="live-title">Live dev run</h3>
      <p className="small muted">
        For developers: runs every arm on {LIVE_USERS} dev readers with the configured model,
        streams the reactions as they arrive, then saves the run and replays it. Never the test set.
      </p>
      {live.state === 'error' && (
        <p role="alert" className="result-error">
          The live run failed: {live.message}
        </p>
      )}
      {(live.state === 'idle' || live.state === 'error') && (
        <button type="button" className="secondary" onClick={begin}>
          Start a live dev run
        </button>
      )}
      {live.state === 'starting' && <p className="muted">Starting the live run…</p>}
      {events.length > 0 && (
        <div className="live-feed">
          <ArmProgressBars progress={armProgress(events, events.length, arms, LIVE_USERS)} />
          <ol className="reaction-feed">
            {reactions.reverse().map((event) => (
              <ReactionCard key={event.seq} event={event} revealed />
            ))}
          </ol>
        </div>
      )}
      {live.state === 'running' && events.length === 0 && (
        <p className="muted">Waiting for the first reaction…</p>
      )}
    </section>
  )
}
