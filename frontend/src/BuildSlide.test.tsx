import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import BuildSlide from './BuildSlide'

/** The revealed parts, not the lists nested inside them. */
function parts(label: string) {
  return [...screen.getByRole('list', { name: label }).children]
}

describe('BuildSlide', () => {
  it('What I built: the pipeline, the task, then the test framework', async () => {
    const user = userEvent.setup()
    render(<BuildSlide id="build" />)

    expect(screen.getByRole('heading', { level: 2, name: 'What I built' })).toBeInTheDocument()
    expect(parts('What I built')).toHaveLength(0)

    await user.keyboard('{ArrowRight}')
    expect(parts('What I built')[0]).toHaveTextContent('MIND clicks')
    expect(parts('What I built')[0]).toHaveTextContent('Gemini')

    await user.keyboard('{ArrowRight}')
    expect(parts('What I built')[1]).toHaveTextContent(/only what the agent knows changes/)
    expect(parts('What I built')[1]).toHaveTextContent(/gut reaction, then a 0–100 click chance/)

    await user.keyboard('{ArrowRight}')
    expect(parts('What I built')[2]).toHaveTextContent(/Pre-registered before the test run/)
    expect(parts('What I built')[2]).toHaveTextContent(/30-user dev set/)
    expect(parts('What I built')[2]).toHaveTextContent(/300-user test set run once/)
    expect(screen.queryByRole('button', { name: /show next/i })).not.toBeInTheDocument()
  })

  it('names the five arms and two baselines in their arm colours', async () => {
    const user = userEvent.setup()
    render(<BuildSlide id="build" />)
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

  it('The arms: what each agent knows, with the baselines apart', () => {
    render(<BuildSlide id="arms" />)

    expect(screen.getByRole('heading', { level: 2, name: 'The arms' })).toBeInTheDocument()
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows.map((row) => row.querySelector('th')?.textContent)).toEqual([
      'APlain LLM',
      'BInvented persona',
      'CTwin + memory',
      'DTwin + profile + memory',
      'EWrong twincontrol',
      'Baselines, no AI',
      'Popularity',
      'Random',
    ])
    expect(rows[3]).toHaveTextContent('Past clicks and a profile of them')
    expect(rows[4]).toHaveTextContent(/Tests whether gains are personal/)
  })

  it('Plan met reality: the wrong twin, the bigger test set, the persona not built', async () => {
    const user = userEvent.setup()
    render(<BuildSlide id="changes" />)

    expect(screen.getByRole('heading', { level: 2, name: 'Plan met reality' })).toBeInTheDocument()
    await user.keyboard('{ArrowRight}')
    expect(parts('Plan met reality')[0]).toHaveTextContent(/wrong twin/i)
    await user.keyboard('{ArrowRight}')
    expect(parts('Plan met reality')[1]).toHaveTextContent(/from 200 to 300 users/)
    await user.keyboard('{ArrowRight}')
    expect(parts('Plan met reality')[2]).toHaveTextContent(
      /Not built: a persona inferred from clicks/,
    )
    expect(screen.queryByRole('button', { name: /show next/i })).not.toBeInTheDocument()
  })
})
