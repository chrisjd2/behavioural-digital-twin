import { useEffect, useState } from 'react'
import {
  fetchReport,
  type ArmReport,
  type Estimate,
  type MetricName,
  type PairedDifference,
  type RunReport,
} from './api/report'
import { ArmLabel, BarChart, ReliabilityDiagrams, type Reference, type Row } from './ReportCharts'
import {
  armClass,
  armName,
  decimal,
  niceMax,
  notResultText,
  outcomeLine,
  percent,
  signed,
} from './reportModel'
import UserBrowser from './UserBrowser'
import './report.css'

type Load =
  { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; report: RunReport }

const METRICS: { metric: MetricName; title: string; note: string }[] = [
  { metric: 'auc', title: 'AUC', note: 'Chance a clicked headline outranks a non-clicked one' },
  { metric: 'mrr', title: 'MRR', note: '1 ÷ rank of the first clicked headline' },
  { metric: 'ndcg5', title: 'nDCG@5', note: 'Clicked headlines near the top of the top five' },
  { metric: 'hit1', title: 'Hit@1', note: 'Top pick was clicked' },
]

const RULE =
  'Pre-registered rule (ADR-0001): twins beat plain LLM only if the 95% CI on the mean per-user D − A AUC difference excludes 0 and is positive. Entirely negative: plain LLM better. Otherwise: no detectable difference.'

const interval = (low: number, high: number, format: (v: number) => string) =>
  `[${format(low)}, ${format(high)}]`

/**
 * Step 4: the selected run's pre-registered report. Numbers and the rule's outcome only; no
 * generated interpretation (PRD-03). Render with `key={runId}`.
 */
export default function ReportStep({ runId }: { runId: string }) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })

  useEffect(() => {
    let current = true
    fetchReport(runId)
      .then((report) => current && setLoad({ state: 'ready', report }))
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
  }, [runId])

  if (load.state === 'loading') return <p className="muted">Loading the run’s report…</p>
  if (load.state === 'error') {
    return (
      <p role="alert" className="result-error">
        Could not load this run’s report: {load.message}
      </p>
    )
  }
  const { report } = load
  if (report.arms.length === 0) {
    return <p className="result-empty">This run’s report has no arms to show.</p>
  }

  const llm = report.arms.filter((a) => a.kind === 'llm')
  const baselines = report.arms.filter((a) => a.kind === 'baseline')

  return (
    <div className="report">
      {!report.is_result && (
        <div className="not-result" role="note">
          <p className="not-result-title">{notResultText(report.not_result_reasons)}</p>
          <p>
            Only the frozen test run on real MIND data is a result (ADR-0001). These numbers show
            how the screen works.
            {report.data_source === 'synthetic' && ' Synthetic sample: fake readers.'}
          </p>
        </div>
      )}

      <section className="report-section primary-outcome" aria-labelledby="primary-title">
        <h3 id="primary-title">Primary outcome</h3>
        {report.primary ? (
          <>
            <p className="rule">{RULE}</p>
            <p className="outcome" data-testid="outcome">
              {outcomeLine(report.primary)}
            </p>
            <DifferenceChart
              title="D − A AUC difference"
              differences={[{ arm: 'D', reference: 'A', auc: report.primary.difference }]}
            />
            <p className="small muted">
              N = {report.n_users} users, bootstrap 95% CI (10,000 resamples of users).
            </p>
          </>
        ) : (
          <p className="result-empty">
            This run did not include both arm D and arm A, so it has no primary outcome.
          </p>
        )}
      </section>

      <section className="report-section" aria-labelledby="metrics-title">
        <h3 id="metrics-title">Every metric, per arm</h3>
        <p className="section-note">
          Bars: mean over users, whiskers: 95% CI. Dashed grey lines: the popularity and random
          baselines.
        </p>
        <div className="metric-grid">
          {METRICS.map(({ metric, title, note }) => (
            <figure key={metric} className="metric-panel">
              <figcaption>
                <h4>{title}</h4>
                <p className="small muted">{note}</p>
              </figcaption>
              <BarChart
                title={title}
                rows={llm.map((a) => metricRow(a, metric))}
                domain={[0, 1]}
                ticks={[0, 0.25, 0.5, 0.75, 1]}
                tick={(v) => String(v)}
                references={baselines.map((b) => ({
                  key: b.arm,
                  label: `${armName(b.arm)} ${decimal(b.metrics[metric].mean)}`,
                  value: b.metrics[metric].mean,
                  kind: 'baseline',
                }))}
              />
            </figure>
          ))}
        </div>
      </section>

      <section className="report-section" aria-labelledby="differences-title">
        <h3 id="differences-title">Paired differences</h3>
        <p className="section-note">
          Mean per-user AUC difference with its 95% CI. Only D − A decides the outcome; the rest are
          secondary.
        </p>
        <DifferenceChart title="Paired AUC differences" differences={report.differences} />
      </section>

      {llm.some((a) => a.calibration) && (
        <section className="report-section" aria-labelledby="calibration-title">
          <h3 id="calibration-title">Calibration</h3>
          <p className="section-note">
            Mean <code>p_click</code> per arm against how often readers really clicked.
          </p>
          <CalibrationChart arms={llm} />
          <details className="reliability-details">
            <summary>Reliability diagram</summary>
            <p className="small muted">
              Predictions grouped by <code>p_click</code> in steps of 10, against the share really
              clicked within our candidate sets. On the dashed diagonal, predictions match clicks.
            </p>
            <ReliabilityDiagrams reliability={report.reliability} />
          </details>
        </section>
      )}

      {report.primary && (
        <section className="report-section" aria-labelledby="users-title">
          <h3 id="users-title">Users by outcome</h3>
          <p className="section-note">Users grouped by their own D − A AUC difference.</p>
          <UserBrowser runId={report.run_id} primary={report.primary} />
        </section>
      )}

      <section className="report-section" aria-labelledby="diagnostics-title">
        <h3 id="diagnostics-title">Diagnostics</h3>
        <Diagnostics report={report} />
      </section>
    </div>
  )
}

function metricRow(arm: ArmReport, metric: MetricName): Row {
  const e = arm.metrics[metric]
  return {
    key: arm.arm,
    label: <ArmLabel arm={arm.arm} />,
    className: armClass(arm.arm),
    estimate: e,
    value: decimal(e.mean),
    tooltip: `${armName(arm.arm)}: ${decimal(e.mean)}, 95% CI ${interval(e.low, e.high, decimal)}`,
  }
}

function differenceRow(arm: string, reference: string, e: Estimate): Row {
  const short = (a: string) => (a.length === 1 ? a : armName(a))
  const name = `${short(arm)} − ${short(reference)}`
  return {
    key: name,
    label: (
      <span className="difference-label">
        <span className="difference-arms">{name}</span>
        <span className="arm-name">
          {armName(arm)} − {armName(reference)}
        </span>
      </span>
    ),
    className: armClass(arm),
    estimate: e,
    value: `${signed(e.mean)} ${interval(e.low, e.high, signed)}`,
    tooltip: `${name} AUC: ${signed(e.mean)}, 95% CI ${interval(e.low, e.high, signed)}`,
  }
}

/** Differences around a zero line, on a symmetric axis wide enough for every CI. */
function DifferenceChart({
  title,
  differences,
}: {
  title: string
  differences: PairedDifference[]
}) {
  const extent = Math.max(0.1, ...differences.flatMap((d) => [-d.auc.low, d.auc.high]))
  const max = niceMax(extent, 0.1)
  return (
    <BarChart
      title={title}
      mark="dot"
      zeroLine
      rows={differences.map((d) => differenceRow(d.arm, d.reference, d.auc))}
      domain={[-max, max]}
      ticks={[-max, -max / 2, 0, max / 2, max]}
      tick={(v) => (Math.abs(v) < 1e-9 ? '0' : signed(v).slice(0, -1))}
    />
  )
}

function CalibrationChart({ arms }: { arms: ArmReport[] }) {
  const calibrated = arms.flatMap((a) => (a.calibration ? [{ arm: a.arm, ...a.calibration }] : []))
  // Every arm scores the same users, so the CTRs are the same in each.
  const { feed_ctr, sample_ctr } = calibrated[0]
  const top = Math.max(sample_ctr, ...calibrated.map((a) => a.mean_p_click))
  const max = niceMax(top * 1.05, 0.1)
  const ticks = Array.from({ length: Math.round(max / 0.1) + 1 }, (_, i) => i / 10)
  const references: Reference[] = [
    { key: 'feed', label: `Feed CTR ${percent(feed_ctr)}`, value: feed_ctr, kind: 'feed' },
    {
      key: 'sample',
      label: `Sample CTR ${percent(sample_ctr)} (inflated by design)`,
      value: sample_ctr,
      kind: 'sample',
    },
  ]
  return (
    <>
      <BarChart
        title="Mean p_click per arm"
        rows={calibrated.map(({ arm, mean_p_click: mean }) => {
          return {
            key: arm,
            label: <ArmLabel arm={arm} />,
            className: armClass(arm),
            estimate: { mean, low: mean, high: mean },
            value: percent(mean),
            tooltip: `${armName(arm)}: mean p_click ${percent(mean)}`,
          }
        })}
        domain={[0, max]}
        ticks={ticks}
        tick={(v) => percent(v, 0)}
        references={references}
      />
      <ul className="calibration-key small">
        <li>
          <span className="key-feed" aria-hidden="true" /> Feed CTR: clicks across each user’s whole
          real feed. The primary reference.
        </li>
        <li>
          <span className="key-sample" aria-hidden="true" /> Sample CTR: clicks within our candidate
          sets, inflated by design (up to 2 clicked of 8).
        </li>
      </ul>
    </>
  )
}

function Diagnostics({ report }: { report: RunReport }) {
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Diagnostics table">
      <table className="diagnostics">
        <thead>
          <tr>
            <th scope="col">Arm</th>
            <th scope="col">Parse failures</th>
            <th scope="col">Tie share</th>
            <th scope="col">Identity screen</th>
          </tr>
        </thead>
        <tbody>
          {report.arms.map((a) => {
            const screen = report.identity_screen[a.arm]
            return (
              <tr key={a.arm} className={armClass(a.arm)}>
                <th scope="row">
                  <span className="th-arm">
                    <ArmLabel arm={a.arm} />
                  </span>
                </th>
                <td>{a.kind === 'llm' ? percent(a.parse_failure_rate) : 'n/a'}</td>
                <td>{percent(a.tie_share)}</td>
                <td>
                  {screen
                    ? `${screen.flagged_profiles} of ${screen.profiles} ${screen.profiles === 1 ? 'profile' : 'profiles'} flagged (${screen.hits} ${screen.hits === 1 ? 'hit' : 'hits'}, ${screen.unusable_profiles} unusable)`
                    : 'No profiles'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="small muted">
        Each distinct profile is screened once: arm E reuses other users’ D profiles, so it counts
        only profiles D did not already show. A person reviews every flag (ADR-0007).
      </p>
    </div>
  )
}
