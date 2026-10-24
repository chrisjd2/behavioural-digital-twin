import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import AboutMeSlide from './AboutMeSlides'

function careerStops() {
  return within(screen.getByRole('list', { name: /career/i }))
    .queryAllByRole('listitem')
    .filter((li) => li.parentElement?.getAttribute('aria-label') === 'Career')
}

describe('About me slides', () => {
  it('opens with the title and a photo slot', () => {
    render(<AboutMeSlide id="title" />)
    expect(screen.getByRole('heading', { level: 2, name: 'Chris Davies' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /chris/i })).toHaveAttribute('src', '/private/me.jpg')
  })

  it('says who Chris is in a few words', () => {
    render(<AboutMeSlide id="who" />)
    expect(screen.getByRole('heading', { level: 2, name: 'Who I am' })).toBeInTheDocument()
    for (const text of [/south african/i, /denmark.*10 years/i, /web development/i, /7 years/i])
      expect(screen.getByText(text)).toBeInTheDocument()
  })

  it('reveals the career timeline stop by stop', async () => {
    const user = userEvent.setup()
    render(<AboutMeSlide id="career" />)

    expect(careerStops()).toHaveLength(0)
    await user.keyboard('{ArrowRight}')
    expect(careerStops()[0]).toHaveTextContent(/application consultant/i)
    expect(careerStops()[0]).toHaveTextContent(/SFMC/)
    await user.click(screen.getByRole('button', { name: /show next/i }))
    await user.keyboard('{ArrowRight}{ArrowRight}')

    const stops = careerStops()
    expect(stops.map((li) => li.querySelector('strong')?.textContent)).toEqual([
      'Application consultant',
      'Developer',
      'Technical architect',
      'Product role',
    ])
    expect(stops[3]).toHaveTextContent(/MCP server/i)
    expect(stops[3]).toHaveTextContent(/Adobe/)
    expect(screen.queryByRole('button', { name: /show next/i })).not.toBeInTheDocument()
  })

  it('shows Learn, Tinker and Teach as columns, each with a media slot', () => {
    render(<AboutMeSlide id="life" />)
    for (const [column, file] of [
      ['Learn', 'drawing.jpg'],
      ['Tinker', 'voice.jpg'],
      ['Teach', 'dog.jpg'],
    ]) {
      const region = screen.getByRole('heading', { level: 3, name: column }).closest('section')!
      expect(within(region).getByRole('img')).toHaveAttribute('src', `/private/${file}`)
    }
    expect(screen.getByText(/learning to draw/i)).toBeInTheDocument()
    expect(screen.getByText(/speech-to-speech/i)).toBeInTheDocument()
    expect(screen.getByText(/australian shepherd/i)).toBeInTheDocument()
  })

  it('falls back to a placeholder for every missing media file', () => {
    render(
      <>
        <AboutMeSlide id="title" />
        <AboutMeSlide id="life" />
      </>,
    )
    const media = screen.getAllByRole('img')
    expect(media).toHaveLength(4)
    for (const img of media) fireEvent.error(img)

    const placeholders = screen.getAllByRole('img')
    expect(placeholders).toHaveLength(4)
    for (const placeholder of placeholders) expect(placeholder).not.toHaveAttribute('src')
  })

  it('hands off to Part 2', () => {
    render(<AboutMeSlide id="handoff" />)
    expect(
      screen.getByRole('heading', {
        level: 2,
        name: 'So when I got this brief, I did what I always do: learn, tinker, teach.',
      }),
    ).toBeInTheDocument()
  })
})
