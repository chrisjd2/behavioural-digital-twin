import type { RunList, RunSummary } from './api/runs'

export type Runs =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; list: RunList }

type Props = {
  runs: Runs
  runId: string | undefined
  onRunChange: (runId: string) => void
}

function describe(run: RunSummary): string {
  const kind = run.mock ? 'MOCK' : run.is_result ? 'Result' : 'Dev run, not a result'
  const created = new Date(run.created).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
  return `${created}, ${run.population}, arms ${run.arms.join(' ')}, ${run.n_users} readers (${kind})`
}

/** The saved run Steps 2-4 show. Its selection lives in App so every run step shares it. */
export default function RunPicker({ runs, runId, onRunChange }: Props) {
  if (runs.state === 'idle' || runs.state === 'loading') {
    return <p className="muted">Loading saved runs…</p>
  }
  if (runs.state === 'error') {
    return (
      <p role="alert" className="result-error">
        Could not load the saved runs: {runs.message}
      </p>
    )
  }
  const { runs: list, problems } = runs.list
  const selected = list.find((r) => r.run_id === runId)
  return (
    <div className="run-picker">
      {list.length === 0 ? (
        <p className="result-empty">
          No saved runs yet. Make one with <code>uv run python scripts/run_headless.py</code>, then
          reload.
        </p>
      ) : (
        <label>
          <span className="field-label">Run</span>
          <select value={runId} onChange={(e) => onRunChange(e.target.value)}>
            {list.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {describe(r)}
              </option>
            ))}
          </select>
        </label>
      )}
      {selected && !selected.is_result && (
        <p className="run-kind">
          {selected.mock ? 'MOCK run: fake LLM output.' : 'Dev run.'} Not a reported result.
          {selected.data_source === 'synthetic' && ' Synthetic sample: fake readers.'}
        </p>
      )}
      {problems.length > 0 && (
        <details className="notice">
          <summary>
            {problems.length} saved {problems.length === 1 ? 'run' : 'runs'} could not be opened
          </summary>
          <ul>
            {problems.map((p) => (
              <li key={p.run_id}>
                {p.run_id}:{' '}
                {p.problem === 'incompatible' ? 'saved by an older version' : 'unreadable'} (
                {p.detail})
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
