/** The Report's charts and tables, built from the stored report. Numbers only, no narrative. */
import {
  type ArmReport,
  type Estimate,
  type MetricName,
  type PairedDifference,
  type RunReport,
} from './api/report'
import { ArmLabel, BarChart, type Reference, type Row } from './ReportCharts'
import { armClass, armName, decimal, niceMax, percent, signed } from './reportModel'

const interval = (low: number, high: number, format: (v: number) => string) =>
  `[${format(low)}, ${format(high)}]`

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
export function DifferenceChart({
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

export function CalibrationChart({ arms }: { arms: ArmReport[] }) {
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

export function Diagnostics({ report }: { report: RunReport }) {
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

/** One metric: a bar per LLM arm with its CI, baselines as dashed reference lines. */
export function MetricPanel({
  metric,
  title,
  note,
  arms,
  baselines,
}: {
  metric: MetricName
  title: string
  note: string
  arms: ArmReport[]
  baselines: ArmReport[]
}) {
  return (
    <figure className="metric-panel">
      <figcaption>
        <h4>{title}</h4>
        <p className="small muted">{note}</p>
      </figcaption>
      <BarChart
        title={title}
        rows={arms.map((a) => metricRow(a, metric))}
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
  )
}
