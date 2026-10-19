import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SeedStep from './SeedStep'
import { populationFixture, statusFixture, stubApi } from './test-fixtures'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SeedStep', () => {
  it('shows real MIND as the data source and the ExperimentConfig defaults', () => {
    render(<SeedStep status={statusFixture} />)

    expect(screen.getByText(/real mind data/i)).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /^users/i })).toHaveValue(30)
    expect(screen.getByRole('spinbutton', { name: /^candidates per agent/i })).toHaveValue(8)
    expect(screen.getByRole('spinbutton', { name: /^seed/i })).toHaveValue(20261019)
  })

  it('marks the synthetic sample as fake', () => {
    render(<SeedStep status={{ ...statusFixture, data_source: 'synthetic' }} />)

    expect(screen.getByText(/synthetic sample/i)).toBeInTheDocument()
    expect(screen.getByText(/fake data/i)).toBeInTheDocument()
  })

  it('says when there is no data and disables building', () => {
    render(<SeedStep status={{ ...statusFixture, data_source: 'none' }} />)

    expect(screen.getByText(/no data found/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /build population/i })).toBeDisabled()
  })

  it('shows plain-language cards for arms A-D and both baselines, with E as a control', () => {
    render(<SeedStep status={statusFixture} />)

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

  it('starts with no population built (empty, not an error)', () => {
    render(<SeedStep status={statusFixture} />)

    expect(screen.getByTestId('population-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('population-error')).not.toBeInTheDocument()
  })

  it('builds a population with the chosen settings and shows the summary', async () => {
    const fetchMock = stubApi({ status: statusFixture, experiment: populationFixture })
    const user = userEvent.setup()
    render(<SeedStep status={statusFixture} />)

    const users = screen.getByRole('spinbutton', { name: /^users/i })
    await user.clear(users)
    await user.type(users, '12')
    await user.click(screen.getByRole('button', { name: /build population/i }))

    const summary = await screen.findByTestId('population-summary')
    expect(fetchMock).toHaveBeenCalledWith('/api/experiment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ n_users: 12, seed: 20261019, max_candidates: 8 }),
    })
    expect(within(summary).getByText('41,236')).toBeInTheDocument()
    expect(within(summary).getByText('4.1%')).toBeInTheDocument()
    expect(within(summary).getByText('23.1%')).toBeInTheDocument()
    expect(within(summary).getByText('news')).toBeInTheDocument()
    expect(screen.queryByTestId('population-empty')).not.toBeInTheDocument()
  })

  it('shows a failed build as an error, not an empty population', async () => {
    stubApi({ status: statusFixture, experiment: 422 })
    const user = userEvent.setup()
    render(<SeedStep status={statusFixture} />)

    await user.click(screen.getByRole('button', { name: /build population/i }))

    expect(await screen.findByTestId('population-error')).toHaveTextContent('Server said 422')
    expect(screen.queryByTestId('population-empty')).not.toBeInTheDocument()
    expect(screen.queryByTestId('population-summary')).not.toBeInTheDocument()
  })

  it('hides the build control in DEMO_MODE', () => {
    render(<SeedStep status={{ ...statusFixture, demo_mode: true }} />)

    expect(screen.queryByRole('button', { name: /build population/i })).not.toBeInTheDocument()
    expect(screen.getByText(/read-only demo/i)).toBeInTheDocument()
  })
})
