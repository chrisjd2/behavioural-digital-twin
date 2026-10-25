import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { fetchReport, type MetricName, type RunReport } from './api/report'
import { deckCommand, move } from './deck'
import { largestFit } from './fit'
import { ReliabilityDiagrams } from './ReportCharts'
import {
  armName,
  decimal,
  differenceLine,
  notResultText,
  outcomeHeadline,
  percent,
} from './reportModel'
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
  'Rule set before the test run (ADR-0001): the twin wins only if the whole 95% CI is above 0. All below 0: the plain LLM wins. Otherwise: no detectable difference.'

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

  // The two arms the pre-registered outcome compares, by their mean AUC.
  const compared = ['A', 'D'].flatMap((id) => {
    const arm = report.arms.find((a) => a.arm.toUpperCase() === id)
    return arm ? [{ id, auc: arm.metrics.auc.mean }] : []
  })
  const primary = (
    <section className="report-section primary-outcome" aria-labelledby="primary-title">
      <h3 id="primary-title">Primary outcome</h3>
      {report.primary ? (
        <>
          <p className="outcome" data-testid="outcome">
            {outcomeHeadline(report.primary)}
          </p>
          {paged ? (
            <PlainOutcome report={report} />
          ) : (
            <>
              {compared.length === 2 && (
                <dl className="primary-compare">
                  {compared.map(({ id, auc }) => (
                    <div key={id} className={`arm-${id.toLowerCase()}`}>
                      <dt>
                        <span className="arm-letter">{id}</span> {armName(id)}
                      </dt>
                      <dd>AUC {decimal(auc)}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <p className="small muted">
                AUC: the chance a clicked headline is ranked above a skipped one. 0.5 is a coin
                flip.
              </p>
              <p className="primary-difference">
                Twin minus plain LLM, per reader: <strong>{differenceLine(report.primary)}</strong>
              </p>
              <DifferenceChart
                title="D − A AUC difference"
                differences={[{ arm: 'D', reference: 'A', auc: report.primary.difference }]}
              />
              <p className="rule">{RULE}</p>
              <p className="small muted">
                N = {report.n_users} users, bootstrap 95% CI over users.
              </p>
            </>
          )}
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
    // A page per metric: one chart alone can be enlarged to fill a shared screen.
    const pages: Page[] = [
      { tab: 'Primary outcome', content: primary },
      ...METRICS.map((m) => ({ tab: m.title, content: metrics([m]) })),
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
      ...(users ? [{ tab: 'Users by outcome', content: users, fill: false }] : []),
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

const PLAIN_STATS: { metric: MetricName; label: string }[] = [
  { metric: 'hit1', label: 'Its top pick was a headline the reader clicked' },
  { metric: 'auc', label: 'It ranked a clicked headline above a skipped one' },
]

/**
 * The primary outcome for a room, not a reviewer (ADR-0012): plain LLM against twin on two
 * metrics read as percentages, with random as the floor. The full statistics stay in Explore.
 */
function PlainOutcome({ report }: { report: RunReport }) {
  const find = (id: string) => report.arms.find((a) => a.arm.toLowerCase() === id)
  const shown = [
    { id: 'a', className: 'arm-a' },
    { id: 'd', className: 'arm-d' },
    { id: 'random', className: 'baseline' },
  ].flatMap(({ id, className }) => {
    const arm = find(id)
    return arm ? [{ id, className, arm }] : []
  })
  return (
    <>
      <dl className="plain-outcome">
        {PLAIN_STATS.map(({ metric, label }) => (
          <div key={metric}>
            <dt>{label}</dt>
            {shown.map(({ id, className, arm }) => (
              <dd key={id} className={className}>
                <span className="plain-value">{percent(arm.metrics[metric].mean, 0)}</span>
                {armName(id)}
              </dd>
            ))}
          </div>
        ))}
      </dl>
      <p className="small muted">
        {report.n_users} real readers. The rule for a win was fixed before the test run.
      </p>
    </>
  )
}

/** `fill: false` for a page whose own layout already takes the height left. */
type Page = { tab: string; content: ReactNode; fill?: boolean }

/** How far a page may be enlarged: past this, a short page's text gets cartoonish. */
const MAX_ZOOM = 2
/** The share of a bar chart's width its track keeps: zooming grows the labels beside it. */
const MIN_TRACK = 0.45

/** One page on screen; the next and previous keys turn pages before the deck moves (ADR-0012). */
function PagedReport({ banner, pages }: { banner: ReactNode; pages: Page[] }) {
  const [page, setPage] = useState(0)
  const pageRef = useRef(page)
  pageRef.current = page
  const panelRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const fill = pages[page].fill ?? true

  useLayoutEffect(() => {
    // The charts are drawn at a fixed size: zoom the page up to fill the screen it is shown on.
    const panel = panelRef.current
    const content = contentRef.current
    if (!fill || !panel || !content || panel.clientHeight === 0) return
    const fits = (zoom: number) => {
      content.style.zoom = String(zoom)
      const tracksKeepRoom = [...content.querySelectorAll('.bar-chart')].every(
        (chart) =>
          chart.querySelector('.bar-track')!.getBoundingClientRect().width >=
          MIN_TRACK * chart.getBoundingClientRect().width,
      )
      return (
        content.getBoundingClientRect().height <= panel.getBoundingClientRect().height &&
        content.scrollWidth <= content.clientWidth &&
        tracksKeepRoom
      )
    }
    content.style.zoom = String(largestFit(fits, MAX_ZOOM))
  }, [page, fill])

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
      <div role="tabpanel" id="report-page" aria-labelledby={`report-tab-${page}`} ref={panelRef}>
        {fill ? (
          <div className="report-page" ref={contentRef}>
            {pages[page].content}
          </div>
        ) : (
          pages[page].content
        )}
      </div>
    </div>
  )
}
