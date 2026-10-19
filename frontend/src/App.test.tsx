import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  hookFixture,
  runFixture,
  runPopulationFixture,
  statusFixture,
  stubApi,
} from './test-fixtures'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App shell', () => {
  it('poses the question and opens on Step 0 Hook', async () => {
    stubApi({ status: statusFixture, urls: { '/api/hook': hookFixture } })
    render(<App />)

    expect(
      screen.getByRole('heading', { level: 1, name: /can an ai impersonate a customer/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /hook/i })).toHaveAttribute('aria-current', 'step')
    expect(screen.getByRole('heading', { name: /hook/i, level: 2 })).toBeInTheDocument()
  })
  it('navigates all six steps, with placeholders for unbuilt ones', async () => {
    stubApi({ status: statusFixture })
    const user = userEvent.setup()
    render(<App />)

    const stepper = screen.getByRole('navigation', { name: /steps/i })
    const names = ['Hook', 'Seed', 'Population', 'Simulation', 'Report', 'Interview']
    expect(
      within(stepper)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(names.map((name, i) => `${i}${name}`))

    for (const name of ['Report', 'Interview']) {
      await user.click(within(stepper).getByRole('button', { name: new RegExp(name) }))
      expect(screen.getByRole('heading', { level: 2, name: new RegExp(name) })).toBeInTheDocument()
      expect(screen.getByText(/not built yet/i)).toBeInTheDocument()
    }
    await user.click(within(stepper).getByRole('button', { name: /population/i }))
    expect(screen.getByRole('heading', { level: 2, name: /population/i })).toBeInTheDocument()
    expect(screen.queryByText(/not built yet/i)).not.toBeInTheDocument()
    await user.click(within(stepper).getByRole('button', { name: /hook/i }))
    expect(screen.getByRole('heading', { level: 2, name: /hook/i })).toBeInTheDocument()
    expect(screen.getByText('Illustrative example (dev set)')).toBeInTheDocument()
  })

  describe('MOCK badge: the run on screen, not the server', () => {
    const mockServer = { ...statusFixture, mock: true }
    const runs = (mock: boolean) => ({ runs: [{ ...runFixture, mock }], problems: [] })
    const population = { [`/api/run/${runFixture.run_id}/population`]: runPopulationFixture }

    async function shows(badge: boolean) {
      await waitFor(() =>
        badge
          ? expect(screen.getByText('MOCK')).toBeInTheDocument()
          : expect(screen.queryByText('MOCK')).not.toBeInTheDocument(),
      )
    }

    it('no badge for a real hook run on a mock server', async () => {
      stubApi({ status: mockServer, urls: { '/api/hook': hookFixture } })
      const user = userEvent.setup()
      render(<App />)

      await user.keyboard('{ArrowRight}')
      await screen.findByText(hookFixture.headlines[0].title ?? '')
      await shows(false)
    })

    it('a badge for a mock hook run on a real server', async () => {
      stubApi({ status: statusFixture, urls: { '/api/hook': { ...hookFixture, mock: true } } })
      render(<App />)

      await shows(true)
    })

    it('follows the selected run on Steps 2-4, and Seed has none', async () => {
      stubApi({ status: statusFixture, runs: runs(true), urls: population })
      const user = userEvent.setup()
      render(<App />)

      await user.click(screen.getByRole('button', { name: /population/i }))
      await shows(true)
      await user.click(screen.getByRole('button', { name: /seed/i }))
      await shows(false)
    })

    it('no badge for a real selected run on a mock server', async () => {
      stubApi({ status: mockServer, runs: runs(false), urls: population })
      const user = userEvent.setup()
      render(<App />)

      await user.click(screen.getByRole('button', { name: /population/i }))
      await screen.findByRole('combobox')
      await shows(false)
    })
  })

  it('notes beside the build button that live runs use the MOCK LLM on a mock server', async () => {
    stubApi({ status: { ...statusFixture, mock: true } })
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /seed/i }))
    expect(await screen.findByText('Live runs use the MOCK LLM')).toBeInTheDocument()
  })

  it('has no live-run note on a real server', async () => {
    stubApi({ status: statusFixture })
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /seed/i }))
    await screen.findByText(/real mind data/i)
    expect(screen.queryByText('Live runs use the MOCK LLM')).not.toBeInTheDocument()
  })
  it('always carries the simulated-data label', () => {
    stubApi({ status: statusFixture })
    render(<App />)

    expect(
      screen.getByText(
        "Simulated from anonymised research data (MIND). Not a real person's voice.",
      ),
    ).toBeInTheDocument()
  })

  it('shows an error rather than an empty state when /api/status fails', async () => {
    stubApi({ status: 500 })
    render(<App />)

    expect(await screen.findByTestId('status-error')).toHaveTextContent(/cannot reach/i)
    expect(screen.queryByText('MOCK')).not.toBeInTheDocument()
  })
})
