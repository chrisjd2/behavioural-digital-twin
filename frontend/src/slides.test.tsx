import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { PrivateMedia, Reveal, Slide } from './slides'

const ITEMS = ['Consultant', 'Developer', 'Architect']

function shown() {
  return screen.queryAllByRole('listitem').map((li) => li.textContent)
}

describe('Slide', () => {
  it('has a heading and its content', () => {
    render(
      <Slide kicker="About me" title="Who I am">
        <p>Denmark</p>
      </Slide>,
    )
    expect(screen.getByRole('heading', { level: 2, name: 'Who I am' })).toBeInTheDocument()
    expect(screen.getByText('About me')).toBeInTheDocument()
    expect(screen.getByText('Denmark')).toBeInTheDocument()
  })
})

describe('Reveal', () => {
  it('reveals one item per click', async () => {
    const user = userEvent.setup()
    render(<Reveal label="Career" items={ITEMS} />)

    expect(shown()).toEqual([])
    await user.click(screen.getByRole('button', { name: /show next/i }))
    await user.click(screen.getByRole('button', { name: /show next/i }))
    expect(shown()).toEqual(['Consultant', 'Developer'])
  })

  it('reveals with the next key, and hides with the previous key', async () => {
    const user = userEvent.setup()
    render(<Reveal label="Career" items={ITEMS} />)

    await user.keyboard('{ArrowRight}{PageDown}')
    expect(shown()).toEqual(['Consultant', 'Developer'])
    await user.keyboard('{ArrowLeft}')
    expect(shown()).toEqual(['Consultant'])
  })

  it('leaves keys to the deck once everything, or nothing, is shown', async () => {
    const user = userEvent.setup()
    render(<Reveal label="Career" items={ITEMS} />)
    const used: boolean[] = []
    const record = (event: KeyboardEvent) => used.push(event.defaultPrevented)
    window.addEventListener('keydown', record)

    await user.keyboard('{ArrowLeft}{ArrowRight}{ArrowRight}{ArrowRight}{ArrowRight}')
    window.removeEventListener('keydown', record)

    expect(used).toEqual([false, true, true, true, false])
    expect(screen.queryByRole('button', { name: /show next/i })).not.toBeInTheDocument()
  })

  it('ignores keys while typing', async () => {
    const user = userEvent.setup()
    render(
      <>
        <input aria-label="Note" />
        <Reveal label="Career" items={ITEMS} />
      </>,
    )

    await user.click(screen.getByRole('textbox'))
    await user.keyboard('{ArrowRight}')
    expect(shown()).toEqual([])
  })
})

describe('PrivateMedia', () => {
  it('shows the file from frontend/public/private', () => {
    render(<PrivateMedia name="dog.jpg" caption="My Australian Shepherd" />)
    expect(screen.getByRole('img', { name: 'My Australian Shepherd' })).toHaveAttribute(
      'src',
      '/private/dog.jpg',
    )
  })

  it('shows a placeholder when the file is missing', () => {
    render(<PrivateMedia name="dog.jpg" caption="My Australian Shepherd" />)
    fireEvent.error(screen.getByRole('img'))

    const placeholder = screen.getByRole('img', { name: 'My Australian Shepherd' })
    expect(placeholder).not.toHaveAttribute('src')
    expect(placeholder).toHaveTextContent('My Australian Shepherd')
  })

  it('plays a video file, with the same placeholder when it is missing', () => {
    const { container } = render(<PrivateMedia name="voice.mp4" caption="Voice platform" />)
    const video = container.querySelector('video')
    expect(video).toHaveAttribute('src', '/private/voice.mp4')
    fireEvent.error(video!)

    expect(container.querySelector('video')).toBeNull()
    expect(screen.getByRole('img', { name: 'Voice platform' })).toHaveTextContent('Voice platform')
  })
})
