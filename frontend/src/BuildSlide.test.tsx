import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import BuildSlide from './BuildSlide'

/** The revealed parts, not the lists nested inside them. */
function parts() {
  return [...screen.getByRole('list', { name: 'What I built' }).children]
}

describe('BuildSlide', () => {
  it('reveals the four parts in order', async () => {
    const user = userEvent.setup()
    render(<BuildSlide />)

    expect(screen.getByRole('heading', { level: 2, name: 'What I built' })).toBeInTheDocument()
    expect(parts()).toHaveLength(0)

    await user.keyboard('{ArrowRight}')
    expect(parts()).toHaveLength(1)
    expect(parts()[0]).toHaveTextContent('MIND clicks')
    expect(parts()[0]).toHaveTextContent('Gemini')

    await user.keyboard('{ArrowRight}')
    expect(parts()[1]).toHaveTextContent(/wrong twin/i)

    await user.keyboard('{ArrowRight}')
    expect(parts()[2]).toHaveTextContent(/200 to 300 users/)
    expect(parts()[2]).toHaveTextContent(/30-user dev set/)

    await user.keyboard('{ArrowRight}')
    const who = within(parts()[3] as HTMLElement)
    expect(who.getByText('Me')).toBeInTheDocument()
    expect(who.getByText('Claude')).toBeInTheDocument()
    expect(who.getByText('Checked by hand')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /show next/i })).not.toBeInTheDocument()
  })

  it('names the five arms and two baselines in their arm colours', async () => {
    const user = userEvent.setup()
    render(<BuildSlide />)
    await user.click(screen.getByRole('button', { name: /show next/i }))

    const arms = within(screen.getByRole('list', { name: 'Arms and baselines' })).getAllByRole(
      'listitem',
    )
    expect(arms.map((li) => [li.textContent, li.className])).toEqual([
      ['APlain LLM', 'build-arm arm-a'],
      ['BInvented persona', 'build-arm arm-b'],
      ['CTwin + memory', 'build-arm arm-c'],
      ['DTwin + profile + memory', 'build-arm arm-d'],
      ['EWrong twincontrol', 'build-arm arm-e'],
      ['Popularity', 'build-arm baseline'],
      ['Random', 'build-arm baseline'],
    ])
  })
})
