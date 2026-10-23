import { runKind, type RunList, type RunSummary } from './api/runs'

export type Runs =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; list: RunList }

type Props = {
  runs: Runs
  runId: string | undefined
  onRunChange: (runId: string) => void
  onRefresh: () => void
}

/** Said beside any run that is not a reported result (ADR-0001). */
export const KIND_NOTES: Record<string, string> = {
  MOCK: 'MOCK run: fake LLM output. Not a reported result.',
  'Unfrozen test': 'Test run made without the freeze. Not a reported result.',
  'Synthetic test': 'Test run on the synthetic sample. Not a reported result.',
  Dev: 'Dev run. Not a reported result.',
}

function describe(run: RunSummary): string {
  const created = new Date(run.created).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
  return `${runKind(run)} · ${created} · ${run.n_users} readers · arms ${run.arms.join(' ')}`
}

/** The saved run Steps 2-4 show. Its selection lives in App so every run step shares it. */
export default function RunPicker({ runs, runId, onRunChange, onRefresh }: Props) {
  if (runs.state === 'idle' || runs.state === 'loading') {
    return <p className="muted">Loading saved runs…</p>
  }
  if (runs.state === 'error') {
    return (
      <div role="alert" className="result-error">
        <p>Could not load the saved runs: {runs.message}. Check the API is running.</p>
        <button type="button" className="secondary" onClick={onRefresh}>
          Try again
        </button>
      </div>
    )
  }
  const { runs: list, problems } = runs.list
  const selected = list.find((r) => r.run_id === runId)
  const refresh = (
    <button type="button" className="secondary" onClick={onRefresh}>
      Refresh runs
    </button>
  )
  return (
    <div className="run-picker">
      {list.length === 0 ? (
        <div className="result-empty">
          <p>
            No saved runs yet. Make one with <code>uv run python scripts/run_headless.py</code>.
          </p>
          {refresh}
        </div>
      ) : (
        <div className="run-select">
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
          {refresh}
        </div>
      )}
      {selected && !selected.is_result && (
        <p className="run-kind">
          {KIND_NOTES[runKind(selected)]}
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
