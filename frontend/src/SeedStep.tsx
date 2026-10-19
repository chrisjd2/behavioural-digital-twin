import type { FormEvent, ReactNode } from 'react'
import type { ExperimentRequest, PopulationSummary } from './api/experiment'
import type { DataSource, Status } from './api/status'
import { ARMS, BASELINES, CONTROL, type ArmCard } from './arms'

export type Build =
  | { state: 'idle' }
  | { state: 'building' }
  | { state: 'error'; message: string }
  | { state: 'ready'; summary: PopulationSummary }

const SOURCES: Record<DataSource, { title: string; detail: string }> = {
  mind: {
    title: 'Real MIND data',
    detail: 'Microsoft News Dataset: anonymised readers and their real clicks.',
  },
  synthetic: {
    title: 'Synthetic sample',
    detail: 'Fake data for testing. Never read anything from it as a result.',
  },
  none: {
    title: 'No data found',
    detail: 'Run scripts/download_mind.py or scripts/make_sample.py, then reload.',
  },
}

const FIELDS: { key: keyof ExperimentRequest; label: string; hint: string; min?: number }[] = [
  { key: 'n_users', label: 'Users', hint: 'one feed each', min: 1 },
  { key: 'max_candidates', label: 'Candidates per agent', hint: 'headlines shown', min: 2 },
  { key: 'seed', label: 'Seed', hint: 'same seed, same readers' },
]

const percent = (x: number) => `${(x * 100).toFixed(1)}%`

type Props = {
  status: Status
  request: ExperimentRequest
  onRequestChange: (request: ExperimentRequest) => void
  build: Build
  onBuild: () => void
}

/** Step 1. Its state lives in App so a built preview survives step navigation. */
export default function SeedStep({ status, request, onRequestChange, build, onBuild }: Props) {
  const source = SOURCES[status.data_source]

  function submit(event: FormEvent) {
    event.preventDefault()
    onBuild()
  }

  return (
    <section className="seed" aria-labelledby="step-title">
      <h2 id="step-title">
        <span className="step-kicker">Step 1</span> Seed
      </h2>
      <p className="lede">
        Real readers, real feeds. Each agent sees headlines from one moment in a reader’s feed and
        guesses which they clicked.
      </p>

      <div className="seed-grid">
        <div className={`source source-${status.data_source}`}>
          <h3>Data source</h3>
          <p className="source-title">{source.title}</p>
          <p>{source.detail}</p>
        </div>

        <form className="settings" onSubmit={submit}>
          <h3>Dev-set preview</h3>
          {status.demo_mode ? (
            <p className="muted">
              Read-only demo. The replayed runs were built before the talk; each run shows its own
              settings.
            </p>
          ) : (
            <>
              <div className="fields">
                {FIELDS.map(({ key, label, hint, min }) => (
                  <label key={key}>
                    <span className="field-label">{label}</span>
                    <input
                      type="number"
                      min={min}
                      value={Number.isNaN(request[key]) ? '' : request[key]}
                      onChange={(e) =>
                        onRequestChange({ ...request, [key]: e.target.valueAsNumber })
                      }
                    />
                    <span className="field-hint">{hint}</span>
                  </label>
                ))}
              </div>
              <button
                type="submit"
                className="primary"
                disabled={status.data_source === 'none' || build.state === 'building'}
              >
                {build.state === 'building' ? 'Building population…' : 'Build population'}
              </button>
            </>
          )}
        </form>
      </div>

      <PopulationResult build={build} />

      <h3 className="section-title">What each agent knows</h3>
      <ul aria-label="Arms" className="cards">
        {ARMS.map((arm) => (
          <Card key={arm.id} arm={arm} letter={arm.id.toUpperCase()}>
            {arm.id === 'd' && (
              <p className="control">
                <span className="control-tag">control</span>
                <span>
                  <strong>Arm E, {CONTROL.name.toLowerCase()}:</strong> {CONTROL.description}
                </span>
              </p>
            )}
          </Card>
        ))}
      </ul>

      <h3 className="section-title">Baselines, no AI</h3>
      <ul aria-label="Baselines" className="cards cards-baseline">
        {BASELINES.map((arm) => (
          <Card key={arm.id} arm={arm} />
        ))}
      </ul>
    </section>
  )
}

function Card({ arm, letter, children }: { arm: ArmCard; letter?: string; children?: ReactNode }) {
  return (
    <li className={`card arm-${arm.id}`}>
      {letter && (
        <span className="arm-letter" aria-hidden="true">
          {letter}
        </span>
      )}
      <h4>{arm.name}</h4>
      <p className="knows">{arm.knows}</p>
      <p>{arm.description}</p>
      {children}
    </li>
  )
}

function PopulationResult({ build }: { build: Build }) {
  if (build.state === 'idle') {
    return (
      <p className="result result-empty" data-testid="population-empty">
        No population built yet. Build one to preview who a dev-set run would include.
      </p>
    )
  }
  if (build.state === 'building') {
    return <p className="result muted">Sampling readers…</p>
  }
  if (build.state === 'error') {
    return (
      <p role="alert" className="result result-error" data-testid="population-error">
        Could not build the population: {build.message}
      </p>
    )
  }
  const { summary } = build
  const top = summary.categories[0]?.users ?? 1
  return (
    <div className="result result-summary" data-testid="population-summary">
      <dl className="stats">
        <Stat label="readers sampled" value={summary.n_users.toLocaleString('en-GB')} />
        <Stat
          label="eligible readers outside the test set"
          value={summary.eligible_users.toLocaleString('en-GB')}
        />
        <Stat label="headlines to judge" value={summary.n_candidates.toLocaleString('en-GB')} />
        <Stat label="feed click rate" value={percent(summary.mean_feed_ctr)} />
        <Stat label="click rate in candidates" value={percent(summary.mean_sample_ctr)} />
      </dl>
      <div className="categories">
        <h4>What they read</h4>
        <ul>
          {summary.categories.map(({ category, users }) => (
            <li key={category}>
              <span className="category-name">{category}</span>
              <span className="category-bar" style={{ width: `${(users / top) * 100}%` }} />
              <span className="category-count">{users}</span>
            </li>
          ))}
        </ul>
      </div>
      {summary.data_source === 'synthetic' && (
        <p className="muted">Synthetic sample: these readers are fake.</p>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}
