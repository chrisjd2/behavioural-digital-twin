import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Status } from './api/status'
import { populationFixture, statusFixture, stubApi, type Reply } from './test-fixtures'

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Seed state lives in App, so render the app and open Step 1. */
async function renderSeed(status: Status = statusFixture, experiment?: Reply) {
  const fetchMock = stubApi({ status, experiment })
  const user = userEvent.setup()
  render(<App />)
  await user.click(screen.getByRole('button', { name: /seed/i }))
  await screen.findByRole('heading', { level: 2, name: /seed/i })
  return { fetchMock, user }
}

const field = (name: RegExp) => screen.getByRole('spinbutton', { name })
const buildButton = () => screen.getByRole('button', { name: /build population/i })

describe('Step 1 Seed', () => {
  it('shows real MIND as the data source and the ExperimentConfig defaults', async () => {
    await renderSeed()

    expect(screen.getByText(/real mind data/i)).toBeInTheDocument()
    expect(field(/^users/i)).toHaveValue(30)
    expect(field(/^candidates per agent/i)).toHaveValue(8)
    expect(field(/^seed/i)).toHaveValue(20261019)
  })

  it('marks the synthetic sample as fake', async () => {
    await renderSeed({ ...statusFixture, data_source: 'synthetic' })

    expect(screen.getByText(/synthetic sample/i)).toBeInTheDocument()
    expect(screen.getByText(/fake data/i)).toBeInTheDocument()
  })

  it('says when there is no data and disables building', async () => {
    await renderSeed({ ...statusFixture, data_source: 'none' })

    expect(screen.getByText(/no data found/i)).toBeInTheDocument()
    expect(buildButton()).toBeDisabled()
  })

  it('shows plain-language cards for arms A-D and both baselines, with E as a control', async () => {
    await renderSeed()

    const arms = screen.getByRole('list', { name: /arms/i })
    for (const name of [
      'Plain LLM',
      'Invented persona',
      'Twin + memory',
      'Twin + profile + memory',
    ]) {
      expect(within(arms).getByRole('heading', { name })).toBeInTheDocument()
    }
    expect(within(arms).getByText('control')).toBeInTheDocument()
    expect(within(arms).getByText(/wrong twin/i)).toBeInTheDocument()

    const baselines = screen.getByRole('list', { name: /baselines/i })
    expect(within(baselines).getByRole('heading', { name: /popularity/i })).toBeInTheDocument()
    expect(within(baselines).getByRole('heading', { name: /random/i })).toBeInTheDocument()
  })

  it('starts with no population built (empty, not an error)', async () => {
    await renderSeed()

    expect(screen.getByTestId('population-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('population-error')).not.toBeInTheDocument()
  })

  it('builds a population with the chosen settings and shows the summary', async () => {
    const { fetchMock, user } = await renderSeed(statusFixture, populationFixture)

    await user.clear(field(/^users/i))
    await user.type(field(/^users/i), '12')
    await user.click(buildButton())

    const summary = await screen.findByTestId('population-summary')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/experiment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ n_users: 12, seed: 20261019, max_candidates: 8 }),
    })
    expect(within(summary).getByText('41,236')).toBeInTheDocument()
    expect(within(summary).getByText(/outside the test set/i)).toBeInTheDocument()
    expect(within(summary).getByText('4.1%')).toBeInTheDocument()
    expect(within(summary).getByText('23.1%')).toBeInTheDocument()
    expect(within(summary).getByText('news')).toBeInTheDocument()
    expect(screen.queryByTestId('population-empty')).not.toBeInTheDocument()
  })

  it('sends the default for an emptied field instead of null', async () => {
    const { fetchMock, user } = await renderSeed(statusFixture, populationFixture)

    await user.clear(field(/^candidates per agent/i))
    await user.click(buildButton())

    await screen.findByTestId('population-summary')
    const [, init] = fetchMock.mock.lastCall as unknown as [string, RequestInit]
    expect(JSON.parse(String(init.body))).toEqual(statusFixture.experiment_defaults)
    expect(field(/^candidates per agent/i)).toHaveValue(8)
  })

  it('keeps the built preview when navigating away and back', async () => {
    const { user } = await renderSeed(statusFixture, populationFixture)

    await user.click(buildButton())
    await screen.findByTestId('population-summary')
    const stepper = screen.getByRole('navigation', { name: /steps/i })
    await user.click(within(stepper).getByRole('button', { name: /population/i }))
    expect(screen.getByRole('heading', { level: 2, name: /population/i })).toBeInTheDocument()
    await user.click(within(stepper).getByRole('button', { name: /seed/i }))

    expect(screen.getByTestId('population-summary')).toBeInTheDocument()
  })

  it('shows a failed build as an error, not an empty population', async () => {
    const { user } = await renderSeed(statusFixture, 409)

    await user.click(buildButton())

    expect(await screen.findByTestId('population-error')).toHaveTextContent('Server said 409')
    expect(screen.queryByTestId('population-empty')).not.toBeInTheDocument()
    expect(screen.queryByTestId('population-summary')).not.toBeInTheDocument()
  })

  it('turns a validation 422 into a readable message', async () => {
    const { user } = await renderSeed(statusFixture, {
      errorStatus: 422,
      body: {
        detail: [
          {
            loc: ['body', 'max_candidates'],
            msg: 'Input should be greater than or equal to 2',
          },
        ],
      },
    })

    await user.click(buildButton())

    expect(await screen.findByTestId('population-error')).toHaveTextContent(
      'max_candidates: Input should be greater than or equal to 2',
    )
  })

  it('hides the build control and the dev settings in DEMO_MODE', async () => {
    await renderSeed({ ...statusFixture, demo_mode: true })

    expect(screen.queryByRole('button', { name: /build population/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    expect(screen.getByText(/read-only demo/i)).toBeInTheDocument()
  })
})
