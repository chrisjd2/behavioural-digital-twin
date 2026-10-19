import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPanel from './AgentPanel'
import { agentFixture, runFixture, statusFixture, stubApi, type Reply } from './test-fixtures'

const AGENT_URL = `/api/run/${runFixture.run_id}/agent/U1`

function open(reply: Reply = agentFixture) {
  stubApi({ status: statusFixture, urls: { [AGENT_URL]: reply } })
  const onClose = vi.fn()
  render(<AgentPanel runId={runFixture.run_id} userId="U1" onClose={onClose} />)
  return onClose
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AgentPanel', () => {
  it('carries the simulated-data label', async () => {
    open()

    await screen.findByRole('tablist')
    expect(
      screen.getByText(
        "Simulated from anonymised research data (MIND). Not a real person's voice.",
      ),
    ).toBeInTheDocument()
  })

  it('shows the click history and the feed headlines without revealing clicks', async () => {
    open()

    const history = await screen.findByRole('region', { name: /past clicks/i })
    expect(within(history).getByText('The workout that may help you live longer')).toBeVisible()
    expect(within(history).getByText('Election Day 2019: races to watch')).toBeVisible()
    const feed = screen.getByRole('region', { name: /headlines in this feed/i })
    expect(within(feed).getByText('How to get a six-pack in 30 days')).toBeVisible()
    expect(within(feed).queryByText(/clicked/i)).not.toBeInTheDocument()
  })

  it('has one tab per arm in run order', async () => {
    open()

    const tabs = within(await screen.findByRole('tablist')).getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual([
      expect.stringMatching(/^A.*Plain LLM/),
      expect.stringMatching(/^B.*Invented persona/),
      expect.stringMatching(/^C.*Twin \+ memory/),
      expect.stringMatching(/^D.*Twin \+ profile \+ memory/),
      expect.stringMatching(/^E.*Wrong twin.*control/),
    ])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent(/knows nothing about this reader/i)
  })

  it('labels the invented persona as made up', async () => {
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('tab', { name: /invented persona/i }))

    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('Made up — not from this user’s data')).toBeVisible()
    expect(panel).toHaveTextContent('Tom Kim')
    expect(panel).toHaveTextContent('insurance agent')
  })

  it('shows memories with their retrieval reasons', async () => {
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('tab', { name: /twin \+ memory$/i }))

    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveTextContent('Similar to: How to get a six-pack')
    expect(panel).toHaveTextContent('Recent click')
  })

  it('shows the profile with its evidence, then the memories', async () => {
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('tab', { name: /profile \+ memory/i }))

    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveTextContent('Fitness routines and preventative health advice.')
    expect(within(panel).getAllByText('The workout that may help you live longer')).toHaveLength(2)
    expect(panel).toHaveTextContent(/identity screen: no flags/i)
  })

  it('flags identity-screen hits on a profile', async () => {
    const user = userEvent.setup()
    const d = agentFixture.arms[3]
    if (d.kind !== 'profile') throw new Error('fixture D is a profile')
    const hit = { kind: 'age', term: '45-year-old', text: 'A 45-year-old' }
    open({
      ...agentFixture,
      arms: [{ ...d, profile: { ...d.profile, identity_hits: [hit] } }],
    })

    await user.click(await screen.findByRole('tab', { name: /profile \+ memory/i }))

    expect(screen.getByRole('tabpanel')).toHaveTextContent(/identity screen flagged 1/i)
    expect(screen.getByRole('tabpanel')).toHaveTextContent('45-year-old')
  })

  it('marks the wrong twin as a control with its donor', async () => {
    const user = userEvent.setup()
    open()

    await user.click(await screen.findByRole('tab', { name: /wrong twin/i }))

    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('control')).toBeVisible()
    expect(panel).toHaveTextContent(/reader U2/)
    expect(panel).toHaveTextContent('Celebrity news and TV personalities.')
  })

  it('moves between tabs with the arrow keys', async () => {
    const user = userEvent.setup()
    open()

    const first = await screen.findByRole('tab', { name: /plain llm/i })
    first.focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: /invented persona/i })).toHaveFocus()
    expect(screen.getByRole('tab', { name: /invented persona/i })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: /wrong twin/i })).toHaveFocus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: /plain llm/i })).toHaveFocus()
  })

  it('shows an error, not an empty panel, when the agent fails to load', async () => {
    open(500)

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load reader U1/i)
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('closes with the close button and with Escape', async () => {
    const user = userEvent.setup()
    const onClose = open()

    await user.click(await screen.findByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
