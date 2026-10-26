import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { SCREENS, type ScreenId } from './deck'
import LearnSlide, { LEARN_SCREENS } from './LearnSlides'

function renderScreen(id: ScreenId) {
  const found = SCREENS.find((s) => s.id === id)!
  return render(<LearnSlide screen={found} />)
}

async function revealAll(user: ReturnType<typeof userEvent.setup>) {
  let next = screen.queryByRole('button', { name: /show next/i })
  while (next) {
    await user.click(next)
    next = screen.queryByRole('button', { name: /show next/i })
  }
}

describe('Learn slides (screens 4-7)', () => {
  it('covers the four Learn screens', () => {
    expect([...LEARN_SCREENS]).toEqual(
      SCREENS.filter((s) => s.section === 'Learn').map((s) => s.id),
    )
  })

  it('The brief: the task, then the two options', async () => {
    const user = userEvent.setup()
    renderScreen('brief')
    expect(screen.getByRole('heading', { level: 2, name: 'The brief' })).toBeInTheDocument()
    expect(
      screen.getByText(/Pick a new technology or idea, explore it, build something, explain it/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/A2A protocols/)).not.toBeInTheDocument()

    await revealAll(user)
    expect(screen.getByText(/A2A protocols/)).toBeInTheDocument()
    expect(screen.getByText(/MiroFish/)).toBeInTheDocument()
  })

  it('Back to MiroFish: two screenshot slots fall back to placeholders', async () => {
    const user = userEvent.setup()
    renderScreen('mirofish')
    expect(screen.getAllByRole('img').map((img) => img.getAttribute('src'))).toEqual([
      '/private/mirofish-readme.png',
      '/private/mirofish-ui.png',
    ])
    for (const img of screen.getAllByRole('img')) fireEvent.error(img)

    const placeholders = screen.getAllByRole('img')
    expect(placeholders).toHaveLength(2)
    for (const p of placeholders) expect(p).not.toHaveAttribute('src')

    await revealAll(user)
    const points = [...screen.getByRole('list', { name: /what I took from MiroFish/i }).children]
    expect(points[0]).toHaveTextContent(/Why it didn’t fit:.*consensus, not individual behaviour/)
    expect(points[1]).toHaveTextContent(
      /Carried forward:.*seed → agent graph → simulation → report → interview/,
    )
  })

  it('Research path: reveals one paper at a time, with its figures', async () => {
    const user = userEvent.setup()
    renderScreen('research')
    const map = screen.getByRole('list', { name: /reading map/i })
    expect(map.children).toHaveLength(0)

    await user.keyboard('{ArrowRight}')
    expect(map.children).toHaveLength(1)
    expect(map).toHaveTextContent('Stanford (Park et al. 2024)')
    expect(map).toHaveTextContent('1,052')
    expect(map).toHaveTextContent('85%')
    expect(map).not.toHaveTextContent('Maiorano')

    await revealAll(user)
    expect(map.children).toHaveLength(6)
    for (const figure of [
      '399',
      '49.2%',
      '34.6%',
      '2,058',
      '71.7%',
      '81.7%',
      '21%',
      '90%',
      'Agent4Rec (SIGIR 2024)',
      'PyMC Labs × Colgate (2025)',
      'Deng et al. (2026)',
      'Twin-2K-500 (Toubia et al. 2025)',
      'Synthetic personas (Maiorano 2026)',
    ]) {
      expect(map).toHaveTextContent(figure)
    }
    expect(screen.getByText(/I read every one/)).toBeInTheDocument()
  })

  it('Research path: two screenshot slots fall back to placeholders', () => {
    renderScreen('research')
    const images = screen.getAllByRole('img')
    expect(images.map((i) => i.getAttribute('src'))).toEqual([
      '/private/paper-stanford.png',
      '/private/claude-chat.png',
    ])
    for (const img of images) fireEvent.error(img)
    for (const p of screen.getAllByRole('img')) expect(p).not.toHaveAttribute('src')
  })

  it('The gap and my angle: ends on the question', async () => {
    const user = userEvent.setup()
    renderScreen('gap')
    await revealAll(user)
    expect(screen.getByText(/Large Behavior Model, 2026/)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Arms' })).not.toBeInTheDocument()
    expect(
      screen.getByText('What makes an AI better at predicting what you’ll click?'),
    ).toBeInTheDocument()
  })
})
