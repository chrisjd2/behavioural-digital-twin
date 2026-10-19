import { useEffect, useState } from 'react'
import { fetchStatus, type Status } from './api/status'
import SeedStep from './SeedStep'

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; status: Status }

const STEPS = [
  { name: 'Hook', blurb: 'You be the twin: guess a reader’s click, then see their history.' },
  { name: 'Seed', blurb: '' },
  { name: 'Population', blurb: 'The sampled readers, linked to the categories they read.' },
  { name: 'Simulation', blurb: 'The recorded run, replayed: every agent reacts to its headlines.' },
  { name: 'Report', blurb: 'How each arm did against the real clicks.' },
  { name: 'Interview', blurb: 'Ask one agent about its news habits.' },
]
const SEED = 1

const SIMULATED_LABEL = "Simulated from anonymised research data (MIND). Not a real person's voice."

export default function App() {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [step, setStep] = useState(SEED)

  useEffect(() => {
    fetchStatus()
      .then((status) => setLoad({ state: 'ready', status }))
      .catch(() => setLoad({ state: 'error' }))
  }, [])

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
        {step === SEED ? (
          <>
            {load.state === 'loading' && <p className="muted">Checking the data source…</p>}
            {load.state === 'ready' && <SeedStep status={load.status} />}
          </>
        ) : (
          <section className="placeholder" aria-labelledby="step-title">
            <h2 id="step-title">
              <span className="step-kicker">Step {step}</span> {STEPS[step].name}
            </h2>
            <p>{STEPS[step].blurb}</p>
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
