import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { statusFixture, stubApi } from './test-fixtures'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App shell', () => {
  it('poses the question and opens on Step 1 Seed', async () => {
    stubApi({ status: statusFixture })
    render(<App />)

    expect(
      screen.getByRole('heading', { level: 1, name: /can an ai impersonate a customer/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /seed/i })).toHaveAttribute('aria-current', 'step')
    expect(await screen.findByRole('heading', { name: /seed/i, level: 2 })).toBeInTheDocument()
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

    for (const name of ['Hook', 'Simulation', 'Interview']) {
      await user.click(within(stepper).getByRole('button', { name: new RegExp(name) }))
      expect(screen.getByRole('heading', { level: 2, name: new RegExp(name) })).toBeInTheDocument()
      expect(screen.getByText(/not built yet/i)).toBeInTheDocument()
    }
    for (const name of ['Population', 'Report']) {
      await user.click(within(stepper).getByRole('button', { name: new RegExp(name) }))
      expect(screen.getByRole('heading', { level: 2, name: new RegExp(name) })).toBeInTheDocument()
      expect(screen.queryByText(/not built yet/i)).not.toBeInTheDocument()
    }
  })

  it('shows MOCK on every step in mock mode', async () => {
    stubApi({ status: { ...statusFixture, mock: true } })
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('MOCK')).toBeInTheDocument()
    for (const name of ['Hook', 'Population', 'Interview']) {
      await user.click(screen.getByRole('button', { name: new RegExp(name) }))
      expect(screen.getByText('MOCK')).toBeInTheDocument()
    }
  })

  it('hides MOCK when the API is in real mode', async () => {
    stubApi({ status: statusFixture })
    render(<App />)

    await screen.findByText(/real mind data/i)
    expect(screen.queryByText('MOCK')).not.toBeInTheDocument()
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
