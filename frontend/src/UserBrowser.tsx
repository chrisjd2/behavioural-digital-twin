import { useEffect, useState } from 'react'
import { fetchPredictions, type PrimaryOutcome, type UserPredictions } from './api/report'
import { ArmLabel } from './ReportCharts'
import {
  armClass,
  armName,
  bucketCounts,
  currentUser,
  decimal,
  signed,
  stepBrowse,
  type Browse,
} from './reportModel'

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; user: UserPredictions }

/** Outcome buckets with counts; the median user by default, or step through a bucket's users. */
export default function UserBrowser({
  runId,
  primary,
}: {
  runId: string
  primary: PrimaryOutcome
}) {
  const [browse, setBrowse] = useState<Browse>({ mode: 'median' })
  const counts = bucketCounts(primary)
  const userId = currentUser(browse, primary)

  return (
    <div className="user-browser">
      <div className="bucket-row" role="group" aria-label="Choose whose rankings to show">
        <button
          type="button"
          className="bucket bucket-median"
          aria-pressed={browse.mode === 'median'}
          onClick={() => setBrowse({ mode: 'median' })}
        >
          <span className="bucket-name">Median user</span>{' '}
          <span className="bucket-note">D − A AUC closest to the median</span>
        </button>
        {primary.buckets.map(({ bucket }) => (
          <button
            key={bucket}
            type="button"
            className="bucket"
            aria-pressed={browse.mode === 'bucket' && browse.bucket === bucket}
            onClick={() => setBrowse({ mode: 'bucket', bucket, index: 0 })}
          >
            <span className="bucket-count">{counts[bucket]}</span>{' '}
            <span className="bucket-name">{bucket}</span>{' '}
            <span className="bucket-note">{BUCKET_RULES[bucket]}</span>
          </button>
        ))}
      </div>

      {browse.mode === 'bucket' && (
        <div className="bucket-stepper">
          <button
            type="button"
            className="secondary"
            disabled={counts[browse.bucket] < 2}
            onClick={() => setBrowse(stepBrowse(browse, -1, primary))}
          >
            Previous user
          </button>
          <p aria-live="polite">
            {counts[browse.bucket] === 0
              ? `No users in “${browse.bucket}”.`
              : `${browse.bucket}: user ${browse.index + 1} of ${counts[browse.bucket]}`}
          </p>
          <button
            type="button"
            className="secondary"
            disabled={counts[browse.bucket] < 2}
            onClick={() => setBrowse(stepBrowse(browse, 1, primary))}
          >
            Next user
          </button>
        </div>
      )}

      {userId && <UserRankings key={userId} runId={runId} userId={userId} />}
    </div>
  )
}

const BUCKET_RULES: Record<string, string> = {
  'Twin better': 'D − A AUC above +0.1',
  'About the same': 'D − A AUC within ±0.1',
  'Plain LLM better': 'D − A AUC below −0.1',
}

/** Every arm's ranking of one user's headlines, side by side against the real clicks. */
function UserRankings({ runId, userId }: { runId: string; userId: string }) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })

  useEffect(() => {
    let current = true
    fetchPredictions(runId, userId)
      .then((user) => current && setLoad({ state: 'ready', user }))
      .catch(
        (error: unknown) =>
          current &&
          setLoad({
            state: 'error',
            message: error instanceof Error ? error.message : 'The request failed.',
          }),
      )
    return () => {
      current = false
    }
  }, [runId, userId])

  if (load.state === 'loading') return <p className="muted">Loading user {userId}’s rankings…</p>
  if (load.state === 'error') {
    return (
      <p role="alert" className="result-error">
        Could not load user {userId}’s predictions: {load.message}
      </p>
    )
  }
  const { user } = load
  const clicks = user.candidates.filter((c) => c.clicked).length
  return (
    <section className="rankings" aria-labelledby="rankings-title">
      <h4 id="rankings-title">
        User {user.user_id}
        {user.d_minus_a !== null && (
          <span className="rankings-meta">
            D − A AUC {signed(user.d_minus_a)} · {user.bucket}
          </span>
        )}
      </h4>
      <p className="small muted">
        Rank each arm gave every headline (1 = most likely to click), with its <code>p_click</code>{' '}
        below. {clicks} of {user.candidates.length} headlines were really clicked. Point at a rank
        to read the agent’s reaction.
      </p>
      <div className="rankings-scroll" tabIndex={0} role="region" aria-label="Rankings table">
        <table className="rankings-table">
          <thead>
            <tr>
              <th scope="col">Headline (as shown)</th>
              <th scope="col">Reality</th>
              {user.arms.map((a) => (
                <th key={a.arm} scope="col" className={armClass(a.arm)}>
                  <span className="th-arm">
                    <ArmLabel arm={a.arm} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {user.candidates.map((c, i) => (
              <tr key={c.news_id} className={c.clicked ? 'clicked' : undefined}>
                <th scope="row">
                  <span className="headline-category">{c.category ?? 'unknown category'}</span>
                  {c.title ?? `${c.news_id} (headline missing)`}
                </th>
                <td className="reality">{c.clicked ? 'Clicked' : 'Not clicked'}</td>
                {user.arms.map((a) => {
                  const p = a.predictions[i]
                  return (
                    <td
                      key={a.arm}
                      className={`rank-cell ${armClass(a.arm)}${p.rank === 1 ? ' top-pick' : ''}`}
                      title={p.reaction ?? undefined}
                      aria-label={`${armName(a.arm)}: rank ${p.rank}${
                        p.p_click !== null ? `, p_click ${p.p_click}` : ''
                      }`}
                    >
                      <span className="rank">{p.rank}</span>
                      {p.p_click !== null && <span className="p-click">{p.p_click}</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={2}>
                This user’s AUC
              </th>
              {user.arms.map((a) => (
                <td key={a.arm}>{decimal(a.auc)}</td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  )
}
