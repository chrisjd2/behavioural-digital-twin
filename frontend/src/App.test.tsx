import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { SCREENS } from './deck'
import {
  hookFixture,
  runEventsFixture,
  runFixture,
  runPopulationFixture,
  statusFixture,
  stubApi,
} from './test-fixtures'

afterEach(() => {
  vi.unstubAllGlobals()
})

const RUNS = { runs: [runFixture], problems: [] }
const POPULATION = { [`/api/run/${runFixture.run_id}/population`]: runPopulationFixture }

function setup(runs: unknown = RUNS, urls: Record<string, unknown> = {}) {
  stubApi({
    status: statusFixture,
    runs: runs as never,
    urls: { '/api/hook': hookFixture, ...POPULATION, ...(urls as Record<string, never>) },
  })
  const user = userEvent.setup()
  render(<App />)
  return user
}

function counter() {
  return screen.getByTestId('deck-counter').textContent
}

type User = ReturnType<typeof userEvent.setup>

/** One press of the next key; on the Hook, past its title, wait for the example first. */
async function next(user: User) {
  if (counter() === '12 / 17' && !screen.queryByText(/you be the twin/i))
    await screen.findByText(hookFixture.headlines[0].title ?? '')
  await user.keyboard('{PageDown}')
}

/** Jump to a screen's section, then step to it, through the Hook's stages if on the way. */
async function goTo(user: User, id: string) {
  const index = SCREENS.findIndex((s) => s.id === id)
  await user.click(
    within(screen.getByRole('navigation', { name: /sections/i })).getByRole('button', {
      name: SCREENS[index].section,
    }),
  )
  for (let press = 0; press < 20 && counter() !== `${index + 1} / 17`; press++) await next(user)
  expect(counter()).toBe(`${index + 1} / 17`)
}

describe('Presenter deck (ADR-0012)', () => {
  it('opens on the first slide of About me', () => {
    setup()

    expect(screen.getByRole('heading', { level: 2, name: 'Chris Davies' })).toBeInTheDocument()
    expect(counter()).toBe('1 / 17')
    const sections = screen.getByRole('navigation', { name: /sections/i })
    expect(within(sections).getByRole('button', { name: 'About me' })).toHaveAttribute(
      'aria-current',
      'step',
    )
  })

  it('walks all 17 screens in order with the next key, stepping through the Hook on the way', async () => {
    const user = setup()
    const seen = [counter()]

    for (let press = 0; press < 100 && counter() !== '17 / 17'; press++) {
      await next(user)
      if (counter() !== seen.at(-1)) seen.push(counter())
    }

    expect(seen).toEqual(SCREENS.map((_, i) => `${i + 1} / 17`))
    expect(screen.getByRole('heading', { level: 2, name: 'Thanks' })).toBeInTheDocument()
  })

  it('goes back with the previous key and stops at the first screen', async () => {
    const user = setup()

    await user.keyboard('{ArrowRight}{ArrowRight}{ArrowLeft}')
    expect(counter()).toBe('2 / 17')
    await user.keyboard('{PageUp}{PageUp}')
    expect(counter()).toBe('1 / 17')
  })

  it('marks the current section as the deck moves', async () => {
    const user = setup()

    await goTo(user, 'gap')
    const sections = screen.getByRole('navigation', { name: /sections/i })
    expect(within(sections).getByRole('button', { name: 'Learn' })).toHaveAttribute(
      'aria-current',
      'step',
    )
    expect(
      screen.getByRole('heading', { level: 2, name: 'The gap and my angle' }),
    ).toBeInTheDocument()
  })

  it('shows Population for the default run, without the run picker', async () => {
    const user = setup()

    await goTo(user, 'population')
    expect(screen.getByRole('heading', { level: 2, name: 'Population' })).toBeInTheDocument()
    expect(await screen.findByRole('group', { name: /readers around/i })).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.getByText(/simulated from anonymised research data/i)).toBeInTheDocument()
  })

  it('replays the default run on Simulation, with no live-run or run controls', async () => {
    const user = setup(RUNS, { [`/api/run/${runFixture.run_id}/events`]: runEventsFixture })

    await goTo(user, 'simulation')
    expect(await screen.findByText(/recorded run, sped up/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /live dev run/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /refresh/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /run/i })).not.toBeInTheDocument()
  })

  it("asks for the default run's report on Report, with no run picker", async () => {
    const user = setup()

    await goTo(user, 'report')
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(`/api/run/${runFixture.run_id}/report`, undefined),
    )
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('says when the run on screen is not a reported result', async () => {
    const user = setup()

    await goTo(user, 'population')
    expect(screen.getByText('Dev run. Not a reported result.')).toBeInTheDocument()
  })

  it('shows the MOCK badge for a mock run on the run screens only', async () => {
    const user = setup({ runs: [{ ...runFixture, mock: true }], problems: [] })

    await goTo(user, 'population')
    await waitFor(() => expect(screen.getByText('MOCK')).toBeInTheDocument())
    await goTo(user, 'brief')
    expect(screen.queryByText('MOCK')).not.toBeInTheDocument()
  })

  it('shows an error, not an empty step, when the runs cannot be loaded', async () => {
    const user = setup(500)

    await goTo(user, 'report')
    expect(await screen.findByRole('alert')).toHaveTextContent(/saved runs could not be loaded/i)
  })

  it('says so when there is no saved run', async () => {
    const user = setup({ runs: [], problems: [] })

    await goTo(user, 'simulation')
    expect(await screen.findByText(/no saved run/i)).toBeInTheDocument()
  })

  it('switches to the free stepper and back to the same screen', async () => {
    const user = setup()

    await goTo(user, 'build')
    await user.click(screen.getByRole('button', { name: 'Explore' }))
    expect(screen.getByRole('navigation', { name: /steps/i })).toBeInTheDocument()
    await user.keyboard('{ArrowRight}') // the stepper's own Hook, not the deck
    await user.click(screen.getByRole('button', { name: 'Presenter' }))
    expect(screen.getByRole('heading', { level: 2, name: 'How I built it' })).toBeInTheDocument()
    expect(counter()).toBe('10 / 17')
  })
})
