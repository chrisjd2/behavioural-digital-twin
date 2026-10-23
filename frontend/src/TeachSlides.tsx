/** Screens 15-17, which close the Teach beat (ADR-0012). */
import { useEffect, useState, type ReactNode } from 'react'
import { fetchReport, type Calibration } from './api/report'
import { runKind, type RunSummary } from './api/runs'
import type { ScreenId, Screen } from './deck'
import InterviewStep from './InterviewStep'
import type { Runs } from './Presenter'
import { percent } from './reportModel'
import { KIND_NOTES } from './RunPicker'
import { Reveal, Slide } from './slides'

export const TEACH_SLIDES = new Set<ScreenId>(['checkin', 'takeaways', 'thanks'])

/** Chris's own reading of the results: static copy, never generated from the data (PRD-03). */
const TAKEAWAYS: ReactNode[] = [
  <>
    <strong>Grounding beats inventing:</strong> behaviour-grounded twins beat a plain LLM; invented
    personas didn’t.
  </>,
  <>
    <strong>It’s personal:</strong> a twin given the wrong person’s history did no better than a
    plain LLM.
  </>,
  <>
    <strong>Don’t trust its probabilities:</strong> rank, don’t forecast; calibrate against real
    rates.
  </>,
  <>
    <strong>So:</strong> use consented first-party data (
    <em>the engagement data in a unified profile, e.g. Data 360</em>), and validate before you
    trust.
  </>,
  <q className="callback">
    A twin built from my clicks would know what I read. It wouldn’t know me.
  </q>,
]

export function TeachSlide({ screen, runs }: { screen: Screen; runs: Runs }) {
  return (
    <Slide kicker={screen.section} title={screen.title}>
      {screen.id === 'takeaways' ? (
        <Reveal label="Takeaways" items={TAKEAWAYS} />
      ) : screen.id === 'checkin' ? (
        <WithRun runs={runs}>{(run) => <CheckIn key={run.run_id} run={run} />}</WithRun>
      ) : (
        <Thanks runs={runs} />
      )}
    </Slide>
  )
}

function WithRun({ runs, children }: { runs: Runs; children: (run: RunSummary) => ReactNode }) {
  if (runs.state === 'loading') return <p className="muted">Loading the saved run…</p>
  if (runs.state === 'error') {
    return (
      <p role="alert" className="error">
        The saved runs could not be loaded: {runs.message}
      </p>
    )
  }
  if (!runs.run) return <p className="muted">No saved run yet. Make one in Explore.</p>
  return children(runs.run)
}

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; calibration: Calibration | null }

/** Screen 15: asked verbally; the numbers are arm D's calibration in the default run. */
function CheckIn({ run }: { run: RunSummary }) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })

  useEffect(() => {
    let current = true
    fetchReport(run.run_id)
      .then((report) => {
        const d = report.arms.find((a) => a.arm === 'D')
        if (current) setLoad({ state: 'ready', calibration: d?.calibration ?? null })
      })
      .catch((error: unknown) => {
        if (current) {
          setLoad({
            state: 'error',
            message: error instanceof Error ? error.message : 'The request failed.',
          })
        }
      })
    return () => {
      current = false
    }
  }, [run.run_id])

  if (load.state === 'loading') return <p className="muted">Loading the run’s calibration…</p>
  if (load.state === 'error') {
    return (
      <p role="alert" className="error">
        The run’s report could not be loaded: {load.message}
      </p>
    )
  }
  if (!load.calibration) return <p className="muted">This run has no arm D calibration.</p>

  const note = KIND_NOTES[runKind(run)]
  const value = (v: number) => (
    <strong className="checkin-number">
      {percent(v)}
      {run.mock && <span className="badge-mock-small">MOCK</span>}
    </strong>
  )
  return (
    <>
      <p className="checkin-question">
        The twins predicted a {value(load.calibration.mean_p_click)} chance of a click. In the real
        feed it was {value(load.calibration.feed_ctr)}. What would you do with that in a campaign?
      </p>
      {note && <p className="run-kind">{note}</p>}
    </>
  )
}

/** Screen 17: the question again, then the Interview as a Q&A bonus (ADR-0008). */
function Thanks({ runs }: { runs: Runs }) {
  const [interview, setInterview] = useState(false)
  return (
    <>
      <p className="thanks-question">Can an AI impersonate a customer?</p>
      <p className="thanks-questions">Questions?</p>
      <WithRun runs={runs}>
        {(run) =>
          interview ? (
            <InterviewStep key={run.run_id} run={run} mockLlm={false} />
          ) : (
            <button type="button" className="primary" onClick={() => setInterview(true)}>
              Interview a twin
            </button>
          )
        }
      </WithRun>
    </>
  )
}
