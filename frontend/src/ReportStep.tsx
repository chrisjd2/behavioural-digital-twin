import { useEffect, useRef, useState, type ReactNode } from 'react'
import { fetchReport, type MetricName, type RunReport } from './api/report'
import { deckCommand, move } from './deck'
import { ReliabilityDiagrams } from './ReportCharts'
import { notResultText, outcomeLine } from './reportModel'
import { CalibrationChart, DifferenceChart, Diagnostics, MetricPanel } from './ReportSections'
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

/**
 * Step 4: the selected run's pre-registered report. Numbers and the rule's outcome only; no
 * generated interpretation (PRD-03). Render with `key={runId}`. `paged` (presenter mode) shows
 * one section at a time, so the report fits a shared 1920×1080 screen.
 */
export default function ReportStep({ runId, paged = false }: { runId: string; paged?: boolean }) {
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

  const banner = !report.is_result && (
    <div className="not-result" role="note">
      <p className="not-result-title">{notResultText(report.not_result_reasons)}</p>
      <p>
        Only the frozen test run on real MIND data is a result (ADR-0001). These numbers show how
        the screen works.
        {report.data_source === 'synthetic' && ' Synthetic sample: fake readers.'}
      </p>
    </div>
  )

  const primary = (
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
          <p className="small muted">N = {report.n_users} users, bootstrap 95% CI over users.</p>
        </>
      ) : (
        <p className="result-empty">
          This run did not include both arm D and arm A, so it has no primary outcome.
        </p>
      )}
    </section>
  )

  const metrics = (shown: typeof METRICS) => (
    <section className="report-section" aria-labelledby="metrics-title">
      <h3 id="metrics-title">Every metric, per arm</h3>
      <p className="section-note">
        Bars: mean over users, whiskers: 95% CI. Dashed grey lines: the popularity and random
        baselines.
      </p>
      <div className="metric-grid">
        {shown.map(({ metric, title, note }) => (
          <MetricPanel
            key={metric}
            metric={metric}
            title={title}
            note={note}
            arms={llm}
            baselines={baselines}
          />
        ))}
      </div>
    </section>
  )

  const differences = (
    <section className="report-section" aria-labelledby="differences-title">
      <h3 id="differences-title">Paired differences</h3>
      <p className="section-note">
        Mean per-user AUC difference with its 95% CI. Only D − A decides the outcome; the rest are
        secondary.
      </p>
      <DifferenceChart title="Paired AUC differences" differences={report.differences} />
    </section>
  )

  const calibrated = llm.some((a) => a.calibration)
  const reliability = (
    <>
      <p className="small muted">
        Predictions grouped by <code>p_click</code> in steps of 10, against the share really clicked
        within our candidate sets, a share inflated by design like sample CTR. On the dashed
        diagonal, predictions match that share.
      </p>
      <ReliabilityDiagrams reliability={report.reliability} />
    </>
  )
  // `withReliability`: the diagram behind a disclosure; paged mode gives it a page of its own.
  const calibration = (withReliability: boolean) => (
    <section className="report-section" aria-labelledby="calibration-title">
      <h3 id="calibration-title">Calibration</h3>
      <p className="section-note">
        Mean <code>p_click</code> per arm against how often readers really clicked.
      </p>
      <CalibrationChart arms={llm} />
      {withReliability && (
        <details className="reliability-details">
          <summary>Reliability diagram</summary>
          {reliability}
        </details>
      )}
    </section>
  )

  const users = report.primary && (
    <section className="report-section" aria-labelledby="users-title">
      <h3 id="users-title">Users by outcome</h3>
      <p className="section-note">Users grouped by their own D − A AUC difference.</p>
      <UserBrowser runId={report.run_id} primary={report.primary} />
    </section>
  )

  const diagnostics = (
    <section className="report-section" aria-labelledby="diagnostics-title">
      <h3 id="diagnostics-title">Diagnostics</h3>
      <Diagnostics report={report} />
    </section>
  )

  if (paged) {
    // The four metrics take two pages: four panels of five arms do not fit one shared screen.
    const pages: Page[] = [
      { tab: 'Primary outcome', content: primary },
      { tab: 'AUC and MRR', content: metrics(METRICS.slice(0, 2)) },
      { tab: 'nDCG@5 and Hit@1', content: metrics(METRICS.slice(2)) },
      { tab: 'Paired differences', content: differences },
      ...(calibrated
        ? [
            { tab: 'Calibration', content: calibration(false) },
            {
              tab: 'Reliability diagram',
              content: (
                <section className="report-section" aria-labelledby="reliability-title">
                  <h3 id="reliability-title">Reliability diagram</h3>
                  {reliability}
                </section>
              ),
            },
          ]
        : []),
      ...(users ? [{ tab: 'Users by outcome', content: users }] : []),
      { tab: 'Diagnostics', content: diagnostics },
    ]
    return <PagedReport banner={banner} pages={pages} />
  }

  return (
    <div className="report">
      {banner}
      {primary}
      {metrics(METRICS)}
      {differences}
      {calibrated && calibration(true)}
      {users}
      {diagnostics}
    </div>
  )
}

type Page = { tab: string; content: ReactNode }

/** One page on screen; the next and previous keys turn pages before the deck moves (ADR-0012). */
function PagedReport({ banner, pages }: { banner: ReactNode; pages: Page[] }) {
  const [page, setPage] = useState(0)
  const pageRef = useRef(page)
  pageRef.current = page

  useEffect(() => {
    // On document, so it runs before the presenter deck's window listener.
    function onKey(event: KeyboardEvent) {
      const command = deckCommand(event)
      if (!command) return
      const next = move(pageRef.current, command, pages.length)
      // On the first or last page the key is left for the deck: the screen before or after.
      if (next === pageRef.current) return
      event.preventDefault()
      setPage(next)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [pages.length])

  return (
    <div className="report report-paged">
      {banner}
      <div role="tablist" aria-label="Report pages" className="report-tabs">
        {pages.map(({ tab }, i) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`report-tab-${i}`}
            aria-selected={i === page}
            aria-controls="report-page"
            onClick={() => setPage(i)}
          >
            {tab}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="report-page" aria-labelledby={`report-tab-${page}`}>
        {pages[page].content}
      </div>
    </div>
  )
}
