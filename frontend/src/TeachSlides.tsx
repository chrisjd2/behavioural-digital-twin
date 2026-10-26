/** Screens 15-16, which close the Teach beat (ADR-0012). */
import { useState, type ReactNode } from 'react'
import type { RunSummary } from './api/runs'
import type { ScreenId, Screen } from './deck'
import InterviewStep from './InterviewStep'
import type { Runs } from './Presenter'
import { Reveal, Slide } from './slides'

export const TEACH_SLIDES = new Set<ScreenId>(['takeaways', 'thanks'])

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
    <strong>Don’t trust its probabilities:</strong> the model knows which content a person prefers,
    but not how likely they really are to act on it. Rank, don’t forecast; calibrate against real
    rates.
  </>,
  <>
    <strong>So:</strong> use consented first-party data (
    <em>the engagement data in a unified profile, e.g. Data 360</em>), and validate before you
    trust.
  </>,
]

export function TeachSlide({
  screen,
  runs,
  mockLlm,
}: {
  screen: Screen
  runs: Runs
  mockLlm: boolean // the server's MOCK_LLM, for the Interview's note
}) {
  return (
    <Slide kicker={screen.section} title={screen.title}>
      {screen.id === 'takeaways' ? (
        <Reveal label="Takeaways" items={TAKEAWAYS} />
      ) : (
        <Thanks runs={runs} mockLlm={mockLlm} />
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

/** Screen 16: the question again, then the Interview as a Q&A bonus (ADR-0008). */
function Thanks({ runs, mockLlm }: { runs: Runs; mockLlm: boolean }) {
  const [interview, setInterview] = useState(false)
  return (
    <>
      <p className="thanks-question">What makes an AI better at predicting what you’ll click?</p>
      <p className="thanks-questions">Questions?</p>
      <WithRun runs={runs}>
        {(run) =>
          interview ? (
            <InterviewStep key={run.run_id} run={run} mockLlm={mockLlm} />
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
