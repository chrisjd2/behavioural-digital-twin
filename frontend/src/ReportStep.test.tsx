import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Explorer from './Explorer'
import type { ArmReport, RunReport, UserPredictions } from './api/report'
import ReportStep from './ReportStep'
import { runFixture, statusFixture, stubApi, type Reply } from './test-fixtures'

const RUN = runFixture.run_id
const reportUrl = `/api/run/${RUN}/report`
const predictionsUrl = (user: string) => `/api/run/${RUN}/user/${user}/predictions`

const estimate = (mean: number) => ({ mean, low: mean - 0.03, high: mean + 0.03 })
const arm = (name: string, auc: number, kind: 'llm' | 'baseline' = 'llm'): ArmReport => ({
  arm: name,
  kind,
  n: 3,
  metrics: { auc: estimate(auc), mrr: estimate(0.5), ndcg5: estimate(0.5), hit1: estimate(0.3) },
  tie_share: 0.05,
  parse_failure_rate: 0.01,
  calibration: kind === 'llm' ? { mean_p_click: 0.43, feed_ctr: 0.0707, sample_ctr: 0.1771 } : null,
})

const reportFixture: RunReport = {
  run_id: RUN,
  population: 'test',
  data_source: 'mind',
  model: 'gemini-test-001',
  mock: false,
  is_result: true,
  not_result_reasons: [],
  n_users: 3,
  arms: [
    arm('A', 0.55),
    arm('D', 0.7),
    arm('E', 0.56),
    arm('popularity', 0.69, 'baseline'),
    arm('random', 0.51, 'baseline'),
  ],
  differences: [
    { arm: 'D', reference: 'A', auc: { mean: 0.1468, low: 0.1017, high: 0.1915 } },
    { arm: 'D', reference: 'E', auc: { mean: 0.1413, low: 0.0957, high: 0.1884 } },
  ],
  primary: {
    difference: { mean: 0.1468, low: 0.1017, high: 0.1915 },
    verdict: 'twins beat plain LLM',
    buckets: [
      {
        bucket: 'Twin better',
        users: [
          { user_id: 'U1', d_minus_a: 0.5 },
          { user_id: 'U2', d_minus_a: 0.2 },
        ],
      },
      { bucket: 'About the same', users: [{ user_id: 'U3', d_minus_a: 0 }] },
      { bucket: 'Plain LLM better', users: [] },
    ],
    bucket_threshold: 0.1,
    median_user: 'U3',
  },
  reliability: [
    {
      arm: 'A',
      bins: [
        { low: 0, high: 0.1, n: 4, clicks: 1, mean_p_click: 0.05 },
        { low: 0.1, high: 0.2, n: 0, clicks: 0, mean_p_click: null },
      ],
    },
  ],
  identity_screen: {
    D: { profiles: 3, flagged_profiles: 1, hits: 2, unusable_profiles: 0, dropped_items: 0 },
  },
}

const predictions = (user_id: string): UserPredictions => ({
  run_id: RUN,
  user_id,
  mock: false,
  is_result: true,
  data_source: 'mind',
  d_minus_a: 0.5,
  bucket: 'Twin better',
  candidates: [
    { news_id: 'N1', category: 'sports', subcategory: 'nfl', title: 'Helmet brawl', clicked: true },
    { news_id: 'N2', category: 'news', subcategory: 'us', title: 'Tiny homes', clicked: false },
  ],
  arms: [
    {
      arm: 'A',
      kind: 'llm',
      auc: 0,
      predictions: [
        { news_id: 'N1', rank: 2, p_click: 30, reaction: 'Meh.' },
        { news_id: 'N2', rank: 1, p_click: 60, reaction: 'Curious.' },
      ],
    },
    {
      arm: 'D',
      kind: 'llm',
      auc: 1,
      predictions: [
        { news_id: 'N1', rank: 1, p_click: 80, reaction: 'I follow this team.' },
        { news_id: 'N2', rank: 2, p_click: 10, reaction: 'Not for me.' },
      ],
    },
    {
      arm: 'popularity',
      kind: 'baseline',
      auc: 1,
      predictions: [
        { news_id: 'N1', rank: 1, p_click: null, reaction: null },
        { news_id: 'N2', rank: 2, p_click: null, reaction: null },
      ],
    },
  ],
})

function renderReport(report: Reply = reportFixture, urls: Record<string, Reply> = {}) {
  const fetchMock = stubApi({
    status: statusFixture,
    urls: {
      [reportUrl]: report,
      [predictionsUrl('U1')]: predictions('U1'),
      [predictionsUrl('U2')]: predictions('U2'),
      [predictionsUrl('U3')]: predictions('U3'),
      ...urls,
    },
  })
  const user = userEvent.setup()
  render(<ReportStep runId={RUN} />)
  return { user, fetchMock }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Report step', () => {
  it('states the primary outcome from the stored verdict, verbatim', async () => {
    // The CI excludes 0, but the UI never re-derives the verdict: it shows what the run stored.
    const stored = {
      ...reportFixture,
      primary: { ...reportFixture.primary!, verdict: 'no detectable difference' as const },
    }
    renderReport(stored)

    expect(await screen.findByTestId('outcome')).toHaveTextContent(
      'D − A AUC +0.147 [+0.102, +0.192]: no detectable difference',
    )
    expect(
      screen.getByText(
        'Pre-registered rule (ADR-0001): twins beat plain LLM only if the 95% CI on the mean per-user D − A AUC difference excludes 0 and is positive. Entirely negative: plain LLM better. Otherwise: no detectable difference.',
      ),
    ).toBeVisible()
  })

  it('shows no banner for a result run', async () => {
    renderReport()

    await screen.findByTestId('outcome')
    expect(screen.queryByText(/not a result/i)).not.toBeInTheDocument()
  })

  it('banners a run that is not a result with its reasons', async () => {
    renderReport({
      ...reportFixture,
      is_result: false,
      mock: true,
      data_source: 'synthetic',
      not_result_reasons: ['mock', 'dev', 'synthetic'],
    })

    const banner = await screen.findByRole('note')
    expect(banner).toHaveTextContent('NOT A RESULT: MOCK, dev, synthetic')
    expect(banner).toHaveTextContent(/synthetic sample: fake readers/i)
  })

  it('shows an error, not an empty report, when the report fails to load', async () => {
    renderReport(422)

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load this run’s report/i)
    expect(screen.queryByText(/has no arms/i)).not.toBeInTheDocument()
  })

  it('says when the report has no arms', async () => {
    renderReport({ ...reportFixture, arms: [], primary: null })

    expect(await screen.findByText(/has no arms to show/i)).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says when a run has no primary outcome', async () => {
    renderReport({ ...reportFixture, primary: null })

    expect(await screen.findByText(/no primary outcome/i)).toBeVisible()
  })

  it('draws a bar with a CI whisker per LLM arm and baselines as reference lines', async () => {
    renderReport()

    const auc = await screen.findByRole('img', { name: /^AUC:/ })
    expect(auc).toHaveAccessibleName(/plain llm: 0\.550, 95% ci \[0\.520, 0\.580\]/i)
    expect([...auc.querySelectorAll('.bar-row')].map((r) => r.classList[1])).toEqual([
      'arm-a',
      'arm-d',
      'arm-e',
    ])
    expect(auc.querySelectorAll('.bar')).toHaveLength(3)
    expect(auc.querySelectorAll('.whisker')).toHaveLength(3)
    const references = auc.querySelectorAll('.reference-baseline text')
    expect([...references].map((r) => r.textContent)).toEqual(['Popularity 0.690', 'Random 0.510'])
  })

  it('lists paired differences', async () => {
    renderReport()

    const chart = await screen.findByRole('img', { name: /paired auc differences/i })
    expect(chart).toHaveAccessibleName(/D − A AUC: \+0\.147.*D − E AUC: \+0\.141/)
  })

  it('draws calibration against feed CTR and sample CTR, inflated by design', async () => {
    renderReport()

    const chart = await screen.findByRole('img', { name: /mean p_click per arm/i })
    expect(chart.querySelector('.reference-feed text')).toHaveTextContent('Feed CTR 7.1%')
    expect(chart.querySelector('.reference-sample text')).toHaveTextContent(
      'Sample CTR 17.7% (inflated by design)',
    )
  })

  it('keeps the reliability diagram collapsed until opened', async () => {
    const { user } = renderReport()

    const summary = await screen.findByText('Reliability diagram')
    const details = summary.closest('details')!
    expect(details).not.toHaveAttribute('open')
    await user.click(summary)
    expect(details).toHaveAttribute('open')
    const diagram = screen.getByRole('img', { name: /arm a reliability/i })
    expect(within(diagram as unknown as HTMLElement).getByText('clicked, in sample')).toBeVisible()
  })

  it('shows diagnostics per arm', async () => {
    renderReport()

    const table = await screen.findByRole('region', { name: 'Diagnostics table' })
    expect(within(table).getByText('1 of 3 profiles flagged (2 hits, 0 unusable)')).toBeVisible()
    expect(within(table).getAllByRole('row')).toHaveLength(6)
  })
})

describe('Users by outcome', () => {
  it('opens on the median user with bucket counts shown', async () => {
    const { fetchMock } = renderReport()

    const group = await screen.findByRole('group', { name: /whose rankings/i })
    expect(within(group).getByRole('button', { name: /median user/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(within(group).getByRole('button', { name: /^2 twin better/i })).toBeVisible()
    expect(within(group).getByRole('button', { name: /^1 about the same/i })).toBeVisible()
    expect(within(group).getByRole('button', { name: /^0 plain llm better/i })).toBeVisible()
    expect(await screen.findByRole('heading', { name: /user U3/i })).toBeVisible()
    expect(fetchMock).toHaveBeenCalledWith(predictionsUrl('U3'), undefined)
  })

  it('steps through a bucket’s users', async () => {
    const { user } = renderReport()

    await user.click(await screen.findByRole('button', { name: /^2 twin better/i }))
    expect(screen.getByText('Twin better: user 1 of 2')).toBeVisible()
    expect(await screen.findByRole('heading', { name: /user U1/i })).toBeVisible()

    await user.click(screen.getByRole('button', { name: /next user/i }))
    expect(screen.getByText('Twin better: user 2 of 2')).toBeVisible()
    expect(await screen.findByRole('heading', { name: /user U2/i })).toBeVisible()

    await user.click(screen.getByRole('button', { name: /next user/i }))
    expect(await screen.findByRole('heading', { name: /user U1/i })).toBeVisible()
  })

  it('states each bucket’s rule from the threshold the report serves', async () => {
    renderReport({
      ...reportFixture,
      primary: { ...reportFixture.primary!, bucket_threshold: 0.15 },
    })

    expect(await screen.findByText('D − A AUC above +0.15')).toBeVisible()
    expect(screen.getByText('D − A AUC within ±0.15')).toBeVisible()
    expect(screen.getByText('D − A AUC below −0.15')).toBeVisible()
  })

  it('says when a bucket is empty', async () => {
    const { user } = renderReport()

    await user.click(await screen.findByRole('button', { name: /^0 plain llm better/i }))

    expect(screen.getByText('No users in “Plain LLM better”.')).toBeVisible()
    expect(screen.queryByRole('heading', { name: /^user U/i })).not.toBeInTheDocument()
  })

  it('shows every arm’s ranking side by side against the real clicks', async () => {
    renderReport()

    const table = await screen.findByRole('region', { name: 'Rankings table' })
    const rows = within(table).getAllByRole('row')
    const clicked = rows.find((r) => r.textContent?.includes('Helmet brawl'))!
    expect(within(clicked).getByText('Clicked')).toBeVisible()
    expect(
      within(clicked).getByLabelText('Twin + profile + memory: rank 1, p_click 80'),
    ).toBeVisible()
    expect(within(clicked).getByLabelText('Plain LLM: rank 2, p_click 30')).toBeVisible()
    expect(within(clicked).getByLabelText('Popularity: rank 1')).toBeVisible()
  })

  it('shows an error when a user’s predictions fail to load', async () => {
    renderReport(reportFixture, { [predictionsUrl('U3')]: 500 })

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not load user U3’s predictions/i,
    )
  })
})

describe('Paged report (presenter mode, #57)', () => {
  function renderPaged(report: Reply = reportFixture) {
    stubApi({
      status: statusFixture,
      urls: { [reportUrl]: report, [predictionsUrl('U3')]: predictions('U3') },
    })
    const user = userEvent.setup()
    render(<ReportStep runId={RUN} paged />)
    return user
  }

  /** A key press the report did not use is left for the deck (its defaultPrevented is false). */
  function press(key: string) {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
    act(() => {
      document.body.dispatchEvent(event)
    })
    return event.defaultPrevented
  }

  const PAGES = [
    'Primary outcome',
    'AUC and MRR',
    'nDCG@5 and Hit@1',
    'Paired differences',
    'Calibration',
    'Reliability diagram',
    'Users by outcome',
    'Diagnostics',
  ]

  it('shows one page at a time, with a tab per page, starting on the primary outcome', async () => {
    renderPaged()

    const tabs = await screen.findByRole('tablist', { name: /report pages/i })
    expect(
      within(tabs)
        .getAllByRole('tab')
        .map((t) => t.textContent),
    ).toEqual(PAGES)
    expect(within(tabs).getByRole('tab', { name: 'Primary outcome' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByTestId('outcome')).toBeVisible()
    expect(screen.queryByRole('img', { name: /paired auc differences/i })).not.toBeInTheDocument()
  })

  it('splits the four metrics over two pages, two panels each', async () => {
    const user = renderPaged()

    await user.click(await screen.findByRole('tab', { name: 'AUC and MRR' }))
    expect(screen.getByRole('img', { name: /^AUC:/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /^MRR:/ })).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /^Hit@1:/ })).not.toBeInTheDocument()
    expect(screen.getByText(/dashed grey lines: the popularity and random/i)).toBeVisible()

    await user.click(screen.getByRole('tab', { name: 'nDCG@5 and Hit@1' }))
    expect(screen.getByRole('img', { name: /^nDCG@5:/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /^Hit@1:/ })).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /^AUC:/ })).not.toBeInTheDocument()
  })

  it('steps through its pages with the next key before the deck moves on', async () => {
    renderPaged()
    await screen.findByTestId('outcome')

    for (const page of PAGES.slice(1)) {
      expect(press('PageDown')).toBe(true)
      expect(screen.getByRole('tab', { name: page })).toHaveAttribute('aria-selected', 'true')
    }
    expect(press('ArrowRight')).toBe(false)
    expect(press('ArrowLeft')).toBe(true)
    expect(screen.getByRole('tab', { name: 'Users by outcome' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('leaves the previous key for the deck on the first page', async () => {
    renderPaged()
    await screen.findByTestId('outcome')

    expect(press('ArrowLeft')).toBe(false)
  })

  it('gives the reliability diagram its own page, open, rather than a disclosure', async () => {
    const user = renderPaged()

    await user.click(await screen.findByRole('tab', { name: 'Calibration' }))
    expect(screen.getByRole('img', { name: /mean p_click per arm/i })).toBeInTheDocument()
    expect(screen.queryByText('Reliability diagram', { selector: 'summary' })).toBeNull()

    await user.click(screen.getByRole('tab', { name: 'Reliability diagram' }))
    expect(screen.getByRole('img', { name: /arm a reliability/i })).toBeInTheDocument()
    expect(screen.getByText(/on the dashed diagonal, predictions match that share/i)).toBeVisible()
  })

  it('keeps the not-a-result banner on every page', async () => {
    const user = renderPaged({
      ...reportFixture,
      is_result: false,
      mock: true,
      not_result_reasons: ['mock'],
    })

    await user.click(await screen.findByRole('tab', { name: 'Diagnostics' }))
    expect(screen.getByRole('note')).toHaveTextContent('NOT A RESULT: MOCK')
    expect(screen.getByRole('region', { name: 'Diagnostics table' })).toBeInTheDocument()
  })

  it('has no pages without a primary outcome or calibration to show', async () => {
    renderPaged({
      ...reportFixture,
      primary: null,
      arms: reportFixture.arms.map((a) => ({ ...a, calibration: null })),
    })

    const tabs = await screen.findByRole('tablist', { name: /report pages/i })
    expect(
      within(tabs)
        .getAllByRole('tab')
        .map((t) => t.textContent),
    ).toEqual([
      'Primary outcome',
      'AUC and MRR',
      'nDCG@5 and Hit@1',
      'Paired differences',
      'Diagnostics',
    ])
    expect(screen.getByText(/no primary outcome/i)).toBeVisible()
  })

  it('takes no keys while loading or after an error', async () => {
    renderPaged(500)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(press('ArrowRight')).toBe(false)
  })
})

describe('App', () => {
  it('opens the report of the selected run at Step 4', async () => {
    const fetchMock = stubApi({
      status: statusFixture,
      runs: { runs: [runFixture], problems: [] },
      urls: { [reportUrl]: reportFixture, [predictionsUrl('U3')]: predictions('U3') },
    })
    const user = userEvent.setup()
    render(<Explorer onPresent={() => {}} />)

    await user.click(screen.getByRole('button', { name: /report/i }))

    expect(await screen.findByTestId('outcome')).toBeVisible()
    expect(fetchMock).toHaveBeenCalledWith(reportUrl, undefined)
  })
})
