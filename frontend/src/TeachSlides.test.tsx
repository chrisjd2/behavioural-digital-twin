import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ArmReport, RunReport } from './api/report'
import type { RunSummary } from './api/runs'
import { SCREENS, type ScreenId } from './deck'
import { SIMULATED_LABEL } from './labels'
import type { Runs } from './Presenter'
import { TeachSlide } from './TeachSlides'
import {
  runFixture,
  runPopulationFixture,
  statusFixture,
  stubApi,
  type Reply,
} from './test-fixtures'

afterEach(() => {
  vi.unstubAllGlobals()
})

const RUN = runFixture.run_id
const REPORT = `/api/run/${RUN}/report`

const arm = (name: string, calibration: ArmReport['calibration']): ArmReport => ({
  arm: name,
  kind: calibration ? 'llm' : 'baseline',
  n: 2,
  metrics: {
    auc: { mean: 0.6, low: 0.5, high: 0.7 },
    mrr: { mean: 0.4, low: 0.3, high: 0.5 },
    ndcg5: { mean: 0.5, low: 0.4, high: 0.6 },
    hit1: { mean: 0.3, low: 0.2, high: 0.4 },
  },
  tie_share: 0,
  parse_failure_rate: 0,
  calibration,
})

const reportFixture = (arms: ArmReport[], mock = false): RunReport => ({
  run_id: RUN,
  population: 'dev',
  data_source: 'mind',
  model: 'gemini-test-001',
  mock,
  is_result: false,
  not_result_reasons: mock ? ['mock', 'dev'] : ['dev'],
  n_users: 2,
  arms,
  differences: [],
  primary: null,
  reliability: [],
  identity_screen: {},
})

const ARMS = [
  arm('A', { mean_p_click: 0.512, feed_ctr: 0.0412, sample_ctr: 0.2 }),
  arm('D', { mean_p_click: 0.4321, feed_ctr: 0.0412, sample_ctr: 0.2 }),
  arm('random', null),
]

const ready = (run: RunSummary | undefined): Runs => ({ state: 'ready', run })

function show(id: ScreenId, runs: Runs, urls: Record<string, Reply> = {}, mockLlm = false) {
  stubApi({ status: statusFixture, urls })
  const user = userEvent.setup()
  render(<TeachSlide screen={SCREENS.find((s) => s.id === id)!} runs={runs} mockLlm={mockLlm} />)
  return user
}

describe('Check-in (screen 13)', () => {
  it("asks the question with arm D's mean p_click and the feed CTR from the run", async () => {
    show('checkin', ready(runFixture), { [REPORT]: reportFixture(ARMS) })

    expect(screen.getByRole('heading', { level: 2, name: 'Check-in' })).toBeInTheDocument()
    const question = await screen.findByText(/chance of a click/i)
    expect(question).toHaveTextContent(
      'The twins predicted a 43.2% chance of a click. In the real feed it was 4.1%. What would you do with that in a campaign?',
    )
    expect(screen.queryByText('MOCK')).not.toBeInTheDocument()
    expect(screen.getByText('Dev run. Not a reported result.')).toBeInTheDocument()
  })

  it('labels both numbers MOCK for a mock run', async () => {
    show('checkin', ready({ ...runFixture, mock: true }), {
      [REPORT]: reportFixture(ARMS, true),
    })

    const question = await screen.findByText(/chance of a click/i)
    expect(within(question).getAllByText('MOCK')).toHaveLength(2)
    expect(
      screen.getByText('MOCK run: fake LLM output. Not a reported result.'),
    ).toBeInTheDocument()
  })

  it('shows an error, not blanks, when the report fails', async () => {
    show('checkin', ready(runFixture), { [REPORT]: 500 })

    expect(await screen.findByRole('alert')).toHaveTextContent(/server said 500/i)
    expect(screen.queryByText(/chance of a click/i)).not.toBeInTheDocument()
  })

  it('shows an error when the saved runs failed to load', () => {
    show('checkin', { state: 'error', message: 'Server said 503' })

    expect(screen.getByRole('alert')).toHaveTextContent(/saved runs could not be loaded/i)
  })

  it('says so while the runs load', () => {
    show('checkin', { state: 'loading' })
    expect(screen.getByText(/loading the saved run/i)).toBeInTheDocument()
  })

  it('says so when there is no saved run', () => {
    show('checkin', ready(undefined))
    expect(screen.getByText(/no saved run yet/i)).toBeInTheDocument()
  })

  it('says so when the run has no arm D calibration', async () => {
    show('checkin', ready(runFixture), { [REPORT]: reportFixture([ARMS[0], ARMS[2]]) })

    expect(await screen.findByText(/no arm D calibration/i)).toBeInTheDocument()
  })
})

describe('Takeaways (screen 14)', () => {
  it('reveals the four takeaways one by one, then the callback line', async () => {
    const user = show('takeaways', ready(runFixture))

    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
    for (let i = 0; i < 5; i++) await user.keyboard('{ArrowRight}')

    const items = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toHaveLength(5)
    expect(items[0]).toMatch(/^Grounding beats inventing/)
    expect(items[1]).toMatch(/^It.s personal/)
    expect(items[2]).toMatch(/^Don.t trust its probabilities/)
    expect(items[3]).toMatch(/consented first-party data.*Data 360.*validate before you trust/)
    expect(items[4]).toBe(
      'A twin built from my clicks would know what I read. It wouldn’t know me.',
    )
    expect(screen.queryByRole('button', { name: /show next/i })).not.toBeInTheDocument()
  })
})

describe('Thanks (screen 15)', () => {
  it('asks the question again and invites questions', () => {
    show('thanks', ready(runFixture))

    expect(screen.getByText('Can an AI impersonate a customer?')).toBeInTheDocument()
    expect(screen.getByText('Questions?')).toBeInTheDocument()
  })

  it('opens the Interview for the default run', async () => {
    const user = show('thanks', ready(runFixture), {
      [`/api/run/${RUN}/population`]: runPopulationFixture,
      [REPORT]: reportFixture(ARMS),
    })

    await user.click(screen.getByRole('button', { name: /interview a twin/i }))
    expect(await screen.findByText(SIMULATED_LABEL)).toBeInTheDocument()
    const reader = runPopulationFixture.agents[0].user_id
    expect(await screen.findByRole('option', { name: new RegExp(reader) })).toBeInTheDocument()
    expect(screen.queryByText('Interview replies use the MOCK LLM')).not.toBeInTheDocument()
  })

  it('notes the MOCK LLM on the Interview when the server runs it', async () => {
    const user = show(
      'thanks',
      ready(runFixture),
      { [`/api/run/${RUN}/population`]: runPopulationFixture, [REPORT]: reportFixture(ARMS) },
      true,
    )

    await user.click(screen.getByRole('button', { name: /interview a twin/i }))
    expect(await screen.findByText('Interview replies use the MOCK LLM')).toBeInTheDocument()
  })

  it('offers no Interview when there is no run, and says why', () => {
    show('thanks', ready(undefined))

    expect(screen.queryByRole('button', { name: /interview/i })).not.toBeInTheDocument()
    expect(screen.getByText(/no saved run yet/i)).toBeInTheDocument()
  })

  it('offers no Interview when the runs failed to load, and says why', () => {
    show('thanks', { state: 'error', message: 'Server said 503' })

    expect(screen.getByRole('alert')).toHaveTextContent(/saved runs could not be loaded/i)
  })
})
