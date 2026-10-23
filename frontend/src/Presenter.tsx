import { useEffect, useState } from 'react'
import AboutMeSlide, { isAboutMe, useDeckStart } from './AboutMeSlides'
import { defaultRunId, fetchRuns, runKind, type RunSummary } from './api/runs'
import { deckCommand, move, SCREENS, SECTIONS, type Screen, type ScreenId } from './deck'
import HookStep from './HookStep'
import { SIMULATED_LABEL } from './labels'
import PopulationStep from './PopulationStep'
import ReportStep from './ReportStep'
import { KIND_NOTES } from './RunPicker'
import SimulationStep from './SimulationStep'
import { Slide } from './slides'

type Runs =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; run: RunSummary | undefined }

const RUN_SCREENS = new Set<ScreenId>(['population', 'simulation', 'report'])

/** The talk (ADR-0012): one running order, the default run, no developer controls. */
export default function Presenter({
  index,
  onIndex,
  onExplore,
}: {
  index: number
  onIndex: (update: (index: number) => number) => void
  onExplore: () => void
}) {
  const [runs, setRuns] = useState<Runs>({ state: 'loading' })
  const [hookRunMock, setHookRunMock] = useState(false)
  const start = useDeckStart()
  const first = start.state === 'ready' ? start.first : 0
  const at = Math.max(index, first)
  const screen = SCREENS[at]
  const sections = SECTIONS.filter((s) => SCREENS.findIndex((x) => x.section === s) >= first)

  useEffect(() => {
    fetchRuns()
      .then((list) => {
        const id = defaultRunId(list.runs)
        setRuns({ state: 'ready', run: list.runs.find((r) => r.run_id === id) })
      })
      .catch((error: unknown) =>
        setRuns({
          state: 'error',
          message: error instanceof Error ? error.message : 'The request failed.',
        }),
      )
  }, [])

  useEffect(() => {
    // On window, after the screen's own document listener (Hook, reveals) has had the key.
    function onKey(event: KeyboardEvent) {
      const command = deckCommand(event)
      if (!command) return
      event.preventDefault()
      onIndex((i) => Math.max(move(Math.max(i, first), command, SCREENS.length), first))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onIndex, first])

  const isStep = RUN_SCREENS.has(screen.id) || screen.id === 'hook'
  const shownRunIsMock =
    screen.id === 'hook'
      ? hookRunMock
      : RUN_SCREENS.has(screen.id) && runs.state === 'ready' && runs.run?.mock === true

  return (
    <div className="deck">
      <header className="deck-bar">
        <p className="wordmark">Twin Lab</p>
        <nav aria-label="Sections" className="deck-sections">
          <ol>
            {sections.map((section) => (
              <li key={section}>
                <button
                  type="button"
                  aria-current={section === screen.section ? 'step' : undefined}
                  onClick={() => onIndex(() => SCREENS.findIndex((s) => s.section === section))}
                >
                  {section}
                </button>
              </li>
            ))}
          </ol>
        </nav>
        {shownRunIsMock && (
          <span
            className="badge-mock"
            title="This run is fake LLM output for development, not results"
          >
            MOCK
          </span>
        )}
        <p className="deck-counter" data-testid="deck-counter">
          {at + 1} / {SCREENS.length}
        </p>
        <button type="button" className="mode-switch" onClick={onExplore}>
          Explore
        </button>
      </header>

      <main className="deck-stage" key={screen.id}>
        {start.state === 'loading' ? (
          <p className="muted">Loading…</p>
        ) : start.state === 'error' ? (
          <p role="alert" className="error">
            The status could not be loaded: {start.message}
          </p>
        ) : isAboutMe(screen.id) ? (
          <AboutMeSlide id={screen.id} />
        ) : screen.id === 'hook' ? (
          <HookStep onRunMock={setHookRunMock} />
        ) : RUN_SCREENS.has(screen.id) ? (
          <section className="run-step" aria-labelledby="step-title">
            <h2 id="step-title">{screen.title}</h2>
            <RunScreen screen={screen} runs={runs} />
          </section>
        ) : (
          <Slide kicker={screen.section} title={screen.title} />
        )}
      </main>

      {/* ADR-0007: on every agent view; the slides are about Chris and the research, not agents. */}
      {isStep && (
        <footer className="footer">
          <p>{SIMULATED_LABEL}</p>
        </footer>
      )}
    </div>
  )
}

function RunScreen({ screen, runs }: { screen: Screen; runs: Runs }) {
  if (runs.state === 'loading') return <p className="muted">Loading the saved run…</p>
  if (runs.state === 'error') {
    return (
      <p role="alert" className="error">
        The saved runs could not be loaded: {runs.message}
      </p>
    )
  }
  if (!runs.run) return <p className="muted">No saved run yet. Make one in Explore.</p>
  const runId = runs.run.run_id
  const note = KIND_NOTES[runKind(runs.run)]
  return (
    <>
      {/* The deck has no run picker, so it says here what Explore says beside it. */}
      {note && <p className="run-kind">{note}</p>}
      {screen.id === 'population' ? (
        <PopulationStep runId={runId} />
      ) : screen.id === 'simulation' ? (
        <SimulationStep runId={runId} liveRuns={false} mockLlm={false} onLiveRunSaved={() => {}} />
      ) : (
        <ReportStep runId={runId} />
      )}
    </>
  )
}
