import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HookExample } from './api/hook'
import HookStep from './HookStep'
import { statusFixture, stubApi } from './test-fixtures'

const hookFixture: HookExample = {
  run_id: '20261019-152445-dev-5c2e8d',
  user_id: 'U1',
  mock: false,
  data_source: 'mind',
  headlines: [
    { news_id: 'N1', category: 'health', subcategory: 'medical', title: 'Pharmacy recall widens' },
    { news_id: 'N2', category: 'news', subcategory: 'newsus', title: 'Senate vote delayed' },
  ],
  history: [
    { news_id: 'H1', category: 'news', subcategory: 'newspolitics', title: 'Impeachment moves on' },
    { news_id: 'H2', category: 'travel', subcategory: 'travelnews', title: 'Order ginger ale' },
  ],
  reveal: {
    clicked_id: 'N2',
    predictions: [
      {
        arm: 'A',
        calls: [
          { news_id: 'N1', p_click: 65, reaction: 'I need to check my medicine cabinet.' },
          { news_id: 'N2', p_click: 40, reaction: 'Politics again, maybe later.' },
        ],
      },
      {
        arm: 'D',
        calls: [
          { news_id: 'N1', p_click: 30, reaction: 'Not really my kind of story.' },
          { news_id: 'N2', p_click: 72.4, reaction: 'I follow every twist in Washington.' },
        ],
      },
    ],
  },
}

const LABEL = 'Illustrative example (dev set)'

function setup(hook: HookExample | number = hookFixture) {
  stubApi({ status: statusFixture, urls: { '/api/hook': hook } })
  const user = userEvent.setup()
  render(<HookStep />)
  return user
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Step 0 Hook', () => {
  it('opens on the question, with no headlines yet', async () => {
    setup()

    expect(screen.getByText('Can an AI impersonate a customer?')).toBeInTheDocument()
    expect(screen.getByText(LABEL)).toBeInTheDocument()
    expect(screen.queryByText('Pharmacy recall widens')).not.toBeInTheDocument()
  })

  it('runs guess, history, guess again and reveal from the keyboard', async () => {
    const user = setup()

    await user.keyboard('{ArrowRight}')
    expect(await screen.findByText('Pharmacy recall widens')).toBeInTheDocument()
    expect(screen.getByText('Senate vote delayed')).toBeInTheDocument()
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
    ).toEqual(['news Impeachment moves on', 'travel Order ginger ale'])
    expect(screen.getByText(/vote again/i)).toBeInTheDocument()
    expect(screen.queryByText(/they clicked this/i)).not.toBeInTheDocument()

    await user.keyboard('r')
    const clicked = screen.getByRole('article', { name: 'Headline 2' })
    expect(within(clicked).getByText('They clicked this')).toBeInTheDocument()
    expect(within(clicked).getByText('72%')).toBeInTheDocument()
    expect(within(clicked).getByText('I follow every twist in Washington.')).toBeInTheDocument()
    const skipped = screen.getByRole('article', { name: 'Headline 1' })
    expect(within(skipped).getByText('They skipped this')).toBeInTheDocument()
    expect(within(skipped).getByText('65%')).toBeInTheDocument()
    expect(
      within(skipped)
        .getByText(/plain llm/i)
        .closest('li'),
    ).toHaveClass('arm-a')
    expect(
      within(skipped)
        .getByText(/twin \+ profile/i)
        .closest('li'),
    ).toHaveClass('arm-d')
    expect(screen.getByText(LABEL)).toBeInTheDocument()
    expect(screen.queryByText('Impeachment moves on')).not.toBeInTheDocument() // room to read

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

    expect(screen.getByText('Can an AI impersonate a customer?')).toBeInTheDocument()
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

  it('labels a mock run and synthetic data', async () => {
    const user = setup({ ...hookFixture, mock: true, data_source: 'synthetic' })

    await user.keyboard('{ArrowRight}')

    expect(await screen.findByText('MOCK')).toBeInTheDocument()
    expect(screen.getByText(/synthetic data: fake headlines/i)).toBeInTheDocument()
  })
})
