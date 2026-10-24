import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Explorer from './Explorer'
import { defaultRunId, type RunList } from './api/runs'
import PopulationStep from './PopulationStep'
import {
  agentFixture,
  runFixture,
  runPopulationFixture,
  statusFixture,
  stubApi,
  type Reply,
} from './test-fixtures'

const RESULT = {
  ...runFixture,
  run_id: '20261020-090000-test-abcdef',
  created: '2026-10-20T09:00:00+00:00',
  population: 'test',
  is_result: true,
}
const NEWER_MOCK = {
  ...runFixture,
  run_id: '20261021-090000-dev-mock01',
  created: '2026-10-21T09:00:00+00:00',
  mock: true,
}

const populationUrl = (runId: string) => `/api/run/${runId}/population`

async function openPopulation(
  runs: Reply = { runs: [runFixture], problems: [] },
  urls: Record<string, Reply> = {
    [populationUrl(runFixture.run_id)]: runPopulationFixture,
    [`/api/run/${runFixture.run_id}/agent/U1`]: agentFixture,
  },
) {
  const fetchMock = stubApi({ status: statusFixture, runs, urls })
  const user = userEvent.setup()
  render(<Explorer onPresent={() => {}} />)
  await user.click(screen.getByRole('button', { name: /population/i }))
  return { user, fetchMock }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Population in presenter mode (#57)', () => {
  it('lays the graph out to the height of its box, not the window', async () => {
    // jsdom has no layout: every observed box reports 1500 x 520.
    vi.stubGlobal(
      'ResizeObserver',
      class {
        callback: ResizeObserverCallback
        constructor(callback: ResizeObserverCallback) {
          this.callback = callback
        }
        observe() {
          this.callback(
            [{ contentRect: { width: 1500, height: 520 } } as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          )
        }
        disconnect() {}
      },
    )
    stubApi({
      status: statusFixture,
      urls: { [populationUrl(runFixture.run_id)]: runPopulationFixture },
    })
    render(<PopulationStep runId={runFixture.run_id} fit />)

    const graph = await screen.findByRole('group', { name: /readers around/i })
    expect(graph).toHaveAttribute('viewBox', '0 0 1500 520')
  })
})

describe('defaultRunId', () => {
  it('picks the newest result run, else the newest run', () => {
    expect(defaultRunId([NEWER_MOCK, runFixture, RESULT])).toBe(RESULT.run_id)
    expect(defaultRunId([NEWER_MOCK, runFixture])).toBe(NEWER_MOCK.run_id)
    expect(defaultRunId([])).toBeUndefined()
  })
})

describe('Run picker', () => {
  it('opens on the newest result run', async () => {
    const list: RunList = { runs: [NEWER_MOCK, RESULT], problems: [] }
    const { fetchMock } = await openPopulation(list, {
      [populationUrl(RESULT.run_id)]: runPopulationFixture,
    })

    const picker = await screen.findByRole('combobox', { name: /run/i })
    expect(picker).toHaveValue(RESULT.run_id)
    expect(within(picker).getAllByRole('option')).toHaveLength(2)
    expect(fetchMock).toHaveBeenCalledWith(populationUrl(RESULT.run_id), undefined)
  })

  it('names the kind of run first', async () => {
    const unfrozen = { ...runFixture, run_id: 'unfrozen', population: 'test' }
    const synthetic = { ...unfrozen, run_id: 'synthetic', data_source: 'synthetic' }
    const list: RunList = {
      runs: [NEWER_MOCK, RESULT, unfrozen, synthetic, runFixture],
      problems: [],
    }
    await openPopulation(list, { [populationUrl(RESULT.run_id)]: runPopulationFixture })

    const options = within(await screen.findByRole('combobox', { name: /run/i })).getAllByRole(
      'option',
    )
    expect(options.map((o) => o.textContent?.split(' · ')[0])).toEqual([
      'MOCK',
      'Result',
      'Unfrozen test',
      'Synthetic test',
      'Dev',
    ])
  })

  it('refreshes the run list and keeps the chosen run', async () => {
    const first: RunList = { runs: [runFixture], problems: [] }
    const { user, fetchMock } = await openPopulation(first)
    await screen.findByRole('combobox', { name: /run/i })

    fetchMock.mockClear()
    await user.click(screen.getByRole('button', { name: /refresh runs/i }))

    expect(fetchMock).toHaveBeenCalledWith('/api/runs', undefined)
    expect(await screen.findByRole('combobox', { name: /run/i })).toHaveValue(runFixture.run_id)
  })

  it('switches run and keeps the choice for the other run steps', async () => {
    const list: RunList = { runs: [NEWER_MOCK, runFixture], problems: [] }
    const { user, fetchMock } = await openPopulation(list, {
      [populationUrl(NEWER_MOCK.run_id)]: runPopulationFixture,
      [populationUrl(runFixture.run_id)]: runPopulationFixture,
    })

    const picker = await screen.findByRole('combobox', { name: /run/i })
    expect(picker).toHaveValue(NEWER_MOCK.run_id)
    expect(screen.getByText(/mock run: fake llm output/i)).toBeInTheDocument()
    await user.selectOptions(picker, runFixture.run_id)
    expect(fetchMock).toHaveBeenCalledWith(populationUrl(runFixture.run_id), undefined)

    await user.click(screen.getByRole('button', { name: /simulation/i }))
    expect(screen.getByRole('combobox', { name: /run/i })).toHaveValue(runFixture.run_id)
  })

  it('shows an error, not an empty list, when the runs fail to load, and retries', async () => {
    const { user, fetchMock } = await openPopulation(500)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/could not load the saved runs/i)
    expect(screen.queryByText(/no saved runs/i)).not.toBeInTheDocument()
    fetchMock.mockClear()
    await user.click(within(alert).getByRole('button', { name: /try again/i }))
    expect(fetchMock).toHaveBeenCalledWith('/api/runs', undefined)
  })

  it('says when there are no saved runs', async () => {
    await openPopulation({ runs: [], problems: [] })

    expect(await screen.findByText(/no saved runs yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('lists run files that could not be opened', async () => {
    await openPopulation({
      runs: [runFixture],
      problems: [{ run_id: 'old-run', problem: 'incompatible', detail: "missing field 'history'" }],
    })

    expect(await screen.findByText(/1 saved run could not be opened/i)).toBeInTheDocument()
    expect(screen.getByText(/old-run: saved by an older version/i)).toBeInTheDocument()
  })
})

describe('Population step', () => {
  it('draws one node per reader behind a single Tab stop', async () => {
    await openPopulation()

    const readers = await screen.findAllByRole('button', { name: /^reader U\d:/i })
    expect(readers).toHaveLength(2)
    expect(readers[0]).toHaveAccessibleName('Reader U1: 4 past clicks in health, news')
    expect(readers.map((r) => r.getAttribute('tabindex'))).toEqual(['0', '-1'])
    expect(screen.getByRole('group', { name: /2 readers around the 3 categories/i })).toBeVisible()
  })

  it('moves between readers with the arrow keys', async () => {
    const { user } = await openPopulation()

    const first = await screen.findByRole('button', { name: /^reader U1:/i })
    first.focus()
    await user.keyboard('{ArrowRight}')

    const second = screen.getByRole('button', { name: /^reader U2:/i })
    expect(second).toHaveFocus()
    expect(second).toHaveAttribute('tabindex', '0')
    expect(first).toHaveAttribute('tabindex', '-1')
    await user.keyboard('{ArrowRight}')
    expect(first).toHaveFocus()
  })

  it('opens the reader panel on click and closes it again', async () => {
    const { user } = await openPopulation()

    await user.click(await screen.findByRole('button', { name: /^reader U1:/i }))

    const panel = await screen.findByRole('complementary', { name: /reader U1/i })
    expect(await within(panel).findByRole('tablist')).toBeInTheDocument()
    expect(within(panel).getByText(/simulated from anonymised research data/i)).toBeVisible()
    await user.click(within(panel).getByRole('button', { name: /close/i }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^reader U1:/i })).toHaveFocus()
  })

  it('opens a reader from the keyboard', async () => {
    const { user } = await openPopulation()

    const reader = await screen.findByRole('button', { name: /^reader U1:/i })
    reader.focus()
    await user.keyboard('{Enter}')

    expect(await screen.findByRole('complementary', { name: /reader U1/i })).toBeInTheDocument()
  })

  it('shows an error, not an empty graph, when the population fails to load', async () => {
    await openPopulation(undefined, { [populationUrl(runFixture.run_id)]: 422 })

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load this run/i)
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
  })

  it('marks synthetic readers as fake', async () => {
    await openPopulation(undefined, {
      [populationUrl(runFixture.run_id)]: { ...runPopulationFixture, data_source: 'synthetic' },
    })

    expect(await screen.findByText(/synthetic sample: these readers are fake/i)).toBeVisible()
  })
})
