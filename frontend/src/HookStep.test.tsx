import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HookExample } from './api/hook'
import HookStep from './HookStep'
import { hookFixture, statusFixture, stubApi } from './test-fixtures'

const LABEL = 'Illustrative example (dev set)'

function setup(hook: HookExample | number = hookFixture) {
  stubApi({ status: statusFixture, urls: { '/api/hook': hook } })
  const user = userEvent.setup()
  const onRunMock = vi.fn()
  render(<HookStep onRunMock={onRunMock} />)
  return Object.assign(user, { onRunMock })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Step 0 Hook', () => {
  it('opens on the question, with no headlines yet', async () => {
    setup()

    expect(
      screen.getByText('What makes an AI better at predicting what you’ll click?'),
    ).toBeInTheDocument()
    expect(screen.getByText(LABEL)).toBeInTheDocument()
    expect(screen.queryByText('Pharmacy recall widens')).not.toBeInTheDocument()
  })

  it('runs guess, history, guess again and reveal from the keyboard', async () => {
    const user = setup()

    await user.keyboard('{ArrowRight}')
    expect(await screen.findByText('Pharmacy recall widens')).toBeInTheDocument()
    expect(screen.getByText('Senate vote delayed')).toBeInTheDocument()
    expect(screen.getByText('news / newsus')).toBeInTheDocument()
    expect(user.onRunMock).toHaveBeenCalledWith(false)
    expect(screen.getByText(/vote 1 or 2/i)).toBeInTheDocument()
    expect(screen.queryByText('Impeachment moves on')).not.toBeInTheDocument()
    expect(screen.queryByText(/they clicked this/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()

    await user.keyboard('h')
    const history = screen.getByRole('region', { name: /what this reader clicked before/i })
    expect(
      within(history)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['news / newspolitics Impeachment moves on', 'travel / travelnews Order ginger ale'])
    expect(screen.getByText(/vote again/i)).toBeInTheDocument()
    expect(screen.queryByText(/they clicked this/i)).not.toBeInTheDocument()

    await user.keyboard('r')
    const clicked = screen.getByRole('article', { name: 'Headline 2' })
    expect(within(clicked).getByText('They clicked this')).toBeInTheDocument()
    const skipped = screen.getByRole('article', { name: 'Headline 1' })
    expect(within(skipped).getByText('They skipped this')).toBeInTheDocument()
    // Each agent's two scores side by side, and whether its pick was the real click.
    const plain = screen.getByRole('listitem', { name: 'Plain LLM' })
    expect(plain).toHaveClass('arm-a')
    expect(plain).toHaveTextContent(/picked headline 1: wrong/i)
    expect(within(plain).getByText('65%')).toBeInTheDocument()
    expect(within(plain).getByText('40%')).toBeInTheDocument()
    const twin = screen.getByRole('listitem', { name: 'Twin + profile + memory' })
    expect(twin).toHaveClass('arm-d')
    expect(twin).toHaveTextContent(/picked headline 2: right/i)
    expect(within(twin).getByText('72%')).toBeInTheDocument()
    expect(within(twin).getByText('I follow every twist in Washington.')).toBeInTheDocument()
    expect(screen.getByText(LABEL)).toBeInTheDocument()
    expect(screen.queryByText('Impeachment moves on')).not.toBeInTheDocument() // room to read
    expect(screen.getByText(/simulated from anonymised research data/i)).toBeInTheDocument()

    await user.keyboard('{ArrowLeft}')
    expect(screen.getByText('Impeachment moves on')).toBeInTheDocument()
    await user.keyboard('{ArrowLeft}')
    expect(screen.queryByText(/they clicked this/i)).not.toBeInTheDocument()
    expect(screen.queryByText('Impeachment moves on')).not.toBeInTheDocument()
  })

  it('has the same controls as buttons, with the history toggle pressed state', async () => {
    const user = setup()
    const toggle = screen.getByRole('button', { name: /show what this reader clicked before/i })
    expect(toggle).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Pharmacy recall widens')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Order ginger ale')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /reveal the real click/i }))
    expect(screen.getByText('They clicked this')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /hide the real click/i }))
    expect(screen.queryByText('They clicked this')).not.toBeInTheDocument()
  })

  it('ignores presenter keys with modifiers', async () => {
    const user = setup()

    await user.keyboard('{Control>}{ArrowRight}{/Control}')

    expect(
      screen.getByText('What makes an AI better at predicting what you’ll click?'),
    ).toBeInTheDocument()
  })

  it('leaves keys it has no stage for to the presenter deck', async () => {
    const user = setup()
    const used: boolean[] = []
    const record = (event: KeyboardEvent) => used.push(event.defaultPrevented)
    window.addEventListener('keydown', record)

    await user.keyboard('{ArrowLeft}') // on the title: nothing before it
    await user.keyboard('{ArrowRight}')
    await screen.findByText('Pharmacy recall widens')
    await user.keyboard('{ArrowRight}{ArrowRight}') // history, then reveal
    await user.keyboard('{ArrowRight}') // revealed: nothing after it
    window.removeEventListener('keydown', record)

    expect(used).toEqual([false, true, true, true, false])
  })

  it('shows the error, not an empty example, when the hook cannot load', async () => {
    const user = setup(404)

    await user.keyboard('{ArrowRight}')

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be loaded.*404/i)
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.getByText(LABEL)).toBeInTheDocument()
  })

  it('says so when the reader has no earlier clicks', async () => {
    const user = setup({ ...hookFixture, history: [] })

    await user.keyboard('{ArrowRight}')
    await screen.findByText('Pharmacy recall widens')
    await user.keyboard('h')

    expect(screen.getByText(/no earlier clicks/i)).toBeInTheDocument()
  })

  it('makes no pick for an agent that scored both headlines the same', async () => {
    const [plain, twin] = hookFixture.reveal.predictions
    const tied = { ...plain, calls: plain.calls.map((call) => ({ ...call, p_click: 50 })) }
    const user = setup({
      ...hookFixture,
      reveal: { ...hookFixture.reveal, predictions: [tied, twin] },
    })

    await user.keyboard('{ArrowRight}')
    await screen.findByText('Pharmacy recall widens')
    await user.keyboard('r')

    expect(screen.getByRole('listitem', { name: 'Plain LLM' })).toHaveTextContent(
      /scored both the same/i,
    )
  })

  it('labels a mock run and synthetic data', async () => {
    const user = setup({ ...hookFixture, mock: true, data_source: 'synthetic' })

    await user.keyboard('{ArrowRight}')

    expect(await screen.findByText(/mock run: the predictions are fake/i)).toBeInTheDocument()
    expect(screen.getByText(/synthetic data: fake headlines/i)).toBeInTheDocument()
  })
})
