import { useEffect, useState } from 'react'
import { buildPopulation, type ExperimentRequest } from './api/experiment'
import { fetchStatus, type Status } from './api/status'
import SeedStep, { type Build } from './SeedStep'

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
const SEED_STEP = 1

const SIMULATED_LABEL = "Simulated from anonymised research data (MIND). Not a real person's voice."

/** An emptied input is NaN; send the config default for it instead. */
function withDefaults(request: ExperimentRequest, defaults: ExperimentRequest): ExperimentRequest {
  const pick = (key: keyof ExperimentRequest) =>
    Number.isNaN(request[key]) ? defaults[key] : request[key]
  return { n_users: pick('n_users'), seed: pick('seed'), max_candidates: pick('max_candidates') }
}

export default function App() {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [step, setStep] = useState(SEED_STEP)
  const [request, setRequest] = useState<ExperimentRequest | null>(null)
  const [build, setBuild] = useState<Build>({ state: 'idle' })

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

  return (
    <div className="shell">
      <header className="masthead">
        <div className="masthead-row">
          <p className="wordmark">Twin Lab</p>
          {load.state === 'ready' && load.status.mock && (
            <span className="badge-mock" title="Fake LLM output for development, not results">
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
                  onClick={() => setStep(i)}
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
        {step === SEED_STEP ? (
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
        ) : (
          <section className="placeholder" aria-labelledby="step-title">
            <h2 id="step-title">
              <span className="step-kicker">Step {step}</span> {current.name}
            </h2>
            <p>{current.blurb}</p>
            {current.runCentric && (
              <p className="run-note" data-testid="run-note">
                Shows one saved run: the newest result run by default, otherwise the newest run. A
                run picker goes here. The Seed preview does not change it.
              </p>
            )}
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
