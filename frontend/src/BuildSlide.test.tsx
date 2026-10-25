import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import BuildSlide from './BuildSlide'

/** The revealed parts, not the lists nested inside them. */
function parts(label: string) {
  return [...screen.getByRole('list', { name: label }).children]
}

describe('BuildSlide', () => {
  it('What I built: the pipeline, then every arm with what its agent knows', () => {
    render(<BuildSlide id="build" />)

    expect(screen.getByRole('heading', { level: 2, name: 'What I built' })).toBeInTheDocument()
    expect(screen.getByText('MIND clicks')).toBeInTheDocument()
    expect(screen.getByText('Gemini')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /show next/i })).not.toBeInTheDocument()

    const rows = screen.getAllByRole('row').slice(1)
    expect(rows.map((row) => [row.querySelector('th')?.textContent, row.className])).toEqual([
      ['APlain LLM', 'arm-a'],
      ['BInvented persona', 'arm-b'],
      ['CTwin + memory', 'arm-c'],
      ['DTwin + profile + memory', 'arm-d'],
      ['EWrong twincontrol', 'arm-e'],
      ['Baselines, no AI', ''],
      ['Popularity', 'baseline'],
      ['Random', 'baseline'],
    ])
    expect(rows[3]).toHaveTextContent('Past clicks and a profile of them')
    expect(rows[4]).toHaveTextContent(/Tests whether gains are personal/)
  })

  it('How I tested it: one reader ranked, their pairs scored, then the test framework', async () => {
    const user = userEvent.setup()
    render(<BuildSlide id="testing" />)

    expect(screen.getByRole('heading', { level: 2, name: 'How I tested it' })).toBeInTheDocument()
    expect(parts('How I tested it')).toHaveLength(0)

    await user.keyboard('{ArrowRight}')
    expect(parts('How I tested it')[0]).toHaveTextContent(/Made-up example/)
    const ranked = within(screen.getByRole('list', { name: 'Ranked by the agent' })).getAllByRole(
      'listitem',
    )
    expect(ranked.map((li) => li.textContent)).toEqual([
      'Mortgage rates jump70%Clicked',
      'Celebrity divorce40%',
      'New iPhone leak30%',
      'Stock market dips25%',
      'Chiefs win in overtime20%Clicked',
      'Weather warning15%',
      'Recipe: easy pasta10%',
      'Royal family news5%',
    ])

    await user.keyboard('{ArrowRight}')
    const pairs = within(screen.getByRole('list', { name: 'Pairs' })).getAllByRole('listitem')
    expect(pairs.map((li) => li.textContent)).toEqual([
      'Mortgageabove 6 of 6 skipped',
      'Chiefsabove 3 of 6 skipped',
    ])
    expect(parts('How I tested it')[1]).toHaveTextContent(/9 of 12 pairs right = AUC 0\.75/)

    await user.keyboard('{ArrowRight}')
    const framework = parts('How I tested it')[2]
    expect(framework).toHaveTextContent(/only what the agent knows changes/)
    expect(framework).toHaveTextContent(/gut reaction, then a 0–100 click chance/)
    expect(framework).toHaveTextContent(/Pre-registered before the test run/)
    expect(framework).toHaveTextContent(/30-user dev set/)
    expect(framework).toHaveTextContent(/300-user test set run once/)
    expect(screen.queryByRole('button', { name: /show next/i })).not.toBeInTheDocument()
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
