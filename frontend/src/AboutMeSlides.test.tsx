import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AboutMeSlide from './AboutMeSlides'

describe('About me slides', () => {
  it('shows the career as four roles at once, each with its note', () => {
    render(<AboutMeSlide id="career" />)

    expect(screen.getByRole('heading', { level: 2, name: 'Career' })).toBeInTheDocument()
    const roles = within(screen.getByRole('list', { name: 'Career' })).getAllByRole('listitem')
    expect(roles.map((li) => li.querySelector('strong')?.textContent)).toEqual([
      'Application consultant',
      'Developer',
      'Technical architect',
      'Product role',
    ])
    expect(roles[0]).toHaveTextContent(/emails and journeys in SFMC/i)
    expect(roles[2]).toHaveTextContent(/two large SFMC clients/i)
    expect(roles[3]).toHaveTextContent(/operations briefing platform/i)
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
    render(<AboutMeSlide id="life" />)
    const media = screen.getAllByRole('img')
    expect(media).toHaveLength(3)
    for (const img of media) fireEvent.error(img)

    const placeholders = screen.getAllByRole('img')
    expect(placeholders).toHaveLength(3)
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
