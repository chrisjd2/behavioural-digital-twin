/** Part 1 of the talk, About me (ADR-0012): screens 1-3, left out of the deck in DEMO_MODE. */
import { useEffect, useState } from 'react'
import { fetchStatus } from './api/status'
import { SCREENS, type ScreenId } from './deck'
import { PrivateMedia, Slide } from './slides'
import './aboutMe.css'

const KICKER = 'About me'

/** The screens this file draws; any other About me screen falls back to the deck's placeholder. */
const ABOUT_ME_IDS = ['career', 'life', 'handoff'] as const
export type AboutMeId = (typeof ABOUT_ME_IDS)[number]

export function isAboutMe(id: ScreenId): id is AboutMeId {
  return (ABOUT_ME_IDS as readonly ScreenId[]).includes(id)
}

export type DeckStart =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; first: number; mockLlm: boolean }

/** The first screen the deck may show: past About me when `/api/status` reports `demo_mode`. */
export function useDeckStart(): DeckStart {
  const [start, setStart] = useState<DeckStart>({ state: 'loading' })
  useEffect(() => {
    fetchStatus()
      .then((status) =>
        setStart({
          state: 'ready',
          first: status.demo_mode ? SCREENS.findIndex((s) => s.section !== KICKER) : 0,
          mockLlm: status.mock,
        }),
      )
      .catch((error: unknown) =>
        setStart({
          state: 'error',
          message: error instanceof Error ? error.message : 'The request failed.',
        }),
      )
  }, [])
  return start
}

/** Chris tells the story; the slide only names the stops. */
const CAREER = [
  { role: 'Application consultant', note: 'Emails and journeys in SFMC Engagement' },
  { role: 'Platform developer' },
  { role: 'Senior platform developer' },
  { role: 'Technical architect', note: 'Two large SFMC clients' },
  { role: 'Product role', note: 'Our operations briefing platform' },
]

const LIFE = [
  {
    heading: 'Learn',
    items: ['Learning to draw', 'New tech, for fun'],
    media: 'drawing.jpg',
    caption: 'A drawing of mine',
  },
  {
    heading: 'Tinker',
    items: ['Little games and tools', 'Speech-to-speech agents: calling friends in new voices'],
    media: 'voice.jpg',
    caption: 'My voice platform',
  },
  {
    heading: 'Teach',
    items: ['Tricks for my Australian Shepherd'],
    media: 'dog.jpg',
    caption: 'My dog',
  },
]

export default function AboutMeSlide({ id }: { id: AboutMeId }) {
  switch (id) {
    case 'career':
      return (
        <Slide kicker={KICKER} title="Career">
          <ol className="career" aria-label="Career">
            {CAREER.map(({ role, note }) => (
              <li key={role}>
                <strong>{role}</strong>
                {note && <span className="career-note"> · {note}</span>}
              </li>
            ))}
          </ol>
        </Slide>
      )
    case 'life':
      return (
        <Slide kicker={KICKER} title="Learn · Tinker · Teach in my life">
          <div className="life-columns">
            {LIFE.map((column) => (
              <section key={column.heading} className="life-column">
                <h3>{column.heading}</h3>
                <ul>
                  {column.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <PrivateMedia name={column.media} caption={column.caption} />
              </section>
            ))}
          </div>
        </Slide>
      )
    case 'handoff':
      return (
        <Slide
          kicker={KICKER}
          title="So when I got this brief, I did what I always do: learn, tinker, teach."
        />
      )
  }
}
