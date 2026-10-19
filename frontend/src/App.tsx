import { useEffect, useState } from 'react'
import { buildPopulation, type ExperimentRequest } from './api/experiment'
import { defaultRunId, fetchRuns } from './api/runs'
import { fetchStatus, type Status } from './api/status'
import HookStep from './HookStep'
import { SIMULATED_LABEL } from './labels'
import PopulationStep from './PopulationStep'
import ReportStep from './ReportStep'
import RunPicker, { type Runs } from './RunPicker'
import SeedStep, { type Build } from './SeedStep'
import SimulationStep from './SimulationStep'

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; status: Status }

type Placeholder = { name: string; blurb: string; runCentric?: boolean }

const STEPS: Placeholder[] = [
  { name: 'Hook', blurb: 'You be the twin: guess a reader’s click, then see their history.' },
  { name: 'Seed', blurb: 'Choose who is in the experiment.' },
  {
    name: 'Population',
    blurb: 'The run’s readers, linked to the categories they read.',
    runCentric: true,
  },
  {
    name: 'Simulation',
    blurb: 'The recorded run, replayed: every agent reacts to its headlines.',
    runCentric: true,
  },
  { name: 'Report', blurb: 'How each arm did against the real clicks.', runCentric: true },
  { name: 'Interview', blurb: 'Ask one agent about its news habits.' },
]
const HOOK_STEP = 0
const SEED_STEP = 1
const POPULATION_STEP = 2
const SIMULATION_STEP = 3
const REPORT_STEP = 4

/** An emptied input is NaN; send the config default for it instead. */
function withDefaults(request: ExperimentRequest, defaults: ExperimentRequest): ExperimentRequest {
  const pick = (key: keyof ExperimentRequest) =>
    Number.isNaN(request[key]) ? defaults[key] : request[key]
  return { n_users: pick('n_users'), seed: pick('seed'), max_candidates: pick('max_candidates') }
}

export default function App() {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [step, setStep] = useState(HOOK_STEP)
  const [request, setRequest] = useState<ExperimentRequest | null>(null)
  const [build, setBuild] = useState<Build>({ state: 'idle' })
  const [runs, setRuns] = useState<Runs>({ state: 'idle' })
  const [runId, setRunId] = useState<string>()
  const [hookRunMock, setHookRunMock] = useState(false)

  useEffect(() => {
    fetchStatus()
      .then((status) => setLoad({ state: 'ready', status }))
      .catch(() => setLoad({ state: 'error' }))
  }, [])

  function buildPreview(status: Status) {
    const sent = withDefaults(request ?? status.experiment_defaults, status.experiment_defaults)
    setRequest(sent)
    setBuild({ state: 'building' })
    buildPopulation(sent)
      .then((summary) => setBuild({ state: 'ready', summary }))
      .catch((error: unknown) =>
        setBuild({
          state: 'error',
          message: error instanceof Error ? error.message : 'The build failed.',
        }),
      )
  }

  const current = STEPS[step]
  // The MOCK badge describes the run on screen, not the server's LLM (ADR-0001, ADR-0008).
  const selectedRun =
    runs.state === 'ready' ? runs.list.runs.find((r) => r.run_id === runId) : undefined
  const shownRunIsMock =
    step === HOOK_STEP ? hookRunMock : current.runCentric ? selectedRun?.mock === true : false

  function goTo(index: number) {
    setStep(index)
    if (STEPS[index].runCentric && runs.state === 'idle') loadRuns()
  }

  // Steps 2-4 share one run list and one selected run, fetched when first needed.
  function loadRuns() {
    setRuns({ state: 'loading' })
    fetchRuns()
      .then((list) => {
        setRuns({ state: 'ready', list })
        // A refresh keeps the chosen run while it still exists.
        setRunId((chosen) =>
          list.runs.some((r) => r.run_id === chosen) ? chosen : defaultRunId(list.runs),
        )
      })
      .catch((error: unknown) =>
        setRuns({
          state: 'error',
          message: error instanceof Error ? error.message : 'The request failed.',
        }),
      )
  }

  return (
    <div className="shell">
      <header className="masthead">
        <div className="masthead-row">
          <p className="wordmark">Twin Lab</p>
          {shownRunIsMock && (
            <span
              className="badge-mock"
              title="This run is fake LLM output for development, not results"
            >
              MOCK
            </span>
          )}
        </div>
        <h1>Can an AI impersonate a customer?</h1>
        <nav aria-label="Steps" className="stepper">
          <ol>
            {STEPS.map(({ name }, i) => (
              <li key={name}>
                <button
                  type="button"
                  aria-current={i === step ? 'step' : undefined}
                  onClick={() => goTo(i)}
                >
                  <span className="step-number">{i}</span>
                  <span className="step-name">{name}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
      </header>

      <main className="stage">
        {load.state === 'error' && (
          <p role="alert" className="error" data-testid="status-error">
            Cannot reach the Twin Lab API. Check the server is running, then reload.
          </p>
        )}
        {step === HOOK_STEP ? (
          <HookStep onRunMock={setHookRunMock} />
        ) : step === SEED_STEP ? (
          <>
            {load.state === 'loading' && <p className="muted">Checking the data source…</p>}
            {load.state === 'ready' && (
              <SeedStep
                status={load.status}
                request={request ?? load.status.experiment_defaults}
                onRequestChange={setRequest}
                build={build}
                onBuild={() => buildPreview(load.status)}
              />
            )}
          </>
        ) : current.runCentric ? (
          <section className="run-step" aria-labelledby="step-title">
            <div className="run-step-head">
              <div>
                <h2 id="step-title">
                  <span className="step-kicker">Step {step}</span> {current.name}
                </h2>
                <p className="lede">{current.blurb}</p>
              </div>
              <RunPicker runs={runs} runId={runId} onRunChange={setRunId} onRefresh={loadRuns} />
            </div>
            {runId && step === POPULATION_STEP && <PopulationStep key={runId} runId={runId} />}
            {step === SIMULATION_STEP && (
              <SimulationStep
                key={runId ?? 'none'}
                runId={runId}
                liveRuns={load.state === 'ready' && !load.status.demo_mode}
                mockLlm={load.state === 'ready' && load.status.mock}
                onLiveRunSaved={(saved) => {
                  setRunId(saved)
                  loadRuns()
                }}
              />
            )}
            {runId && step === REPORT_STEP && <ReportStep key={runId} runId={runId} />}
            {step !== POPULATION_STEP && step !== SIMULATION_STEP && step !== REPORT_STEP && (
              <p className="muted">This step is not built yet.</p>
            )}
          </section>
        ) : (
          <section className="placeholder" aria-labelledby="step-title">
            <h2 id="step-title">
              <span className="step-kicker">Step {step}</span> {current.name}
            </h2>
            <p>{current.blurb}</p>
            <p className="muted">This step is not built yet.</p>
          </section>
        )}
      </main>

      <footer className="footer">
        <p>{SIMULATED_LABEL}</p>
      </footer>
    </div>
  )
}
