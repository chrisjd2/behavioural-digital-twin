/** Part 1 of the talk, About me (ADR-0012): screens 1-5, left out of the deck in DEMO_MODE. */
import { useEffect, useState, type ReactNode } from 'react'
import { fetchStatus } from './api/status'
import { SCREENS, type ScreenId } from './deck'
import { PrivateMedia, Reveal, Slide } from './slides'
import './aboutMe.css'

const KICKER = 'About me'

/** The screens this file draws; any other About me screen falls back to the deck's placeholder. */
const ABOUT_ME_IDS = ['title', 'who', 'career', 'life', 'handoff'] as const
export type AboutMeId = (typeof ABOUT_ME_IDS)[number]

export function isAboutMe(id: ScreenId): id is AboutMeId {
  return (ABOUT_ME_IDS as readonly ScreenId[]).includes(id)
}

export type DeckStart =
  { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; first: number }

/** The first screen the deck may show: past About me when `/api/status` reports `demo_mode`. */
export function useDeckStart(): DeckStart {
  const [start, setStart] = useState<DeckStart>({ state: 'loading' })
  useEffect(() => {
    fetchStatus()
      .then((status) =>
        setStart({
          state: 'ready',
          first: status.demo_mode ? SCREENS.findIndex((s) => s.section !== KICKER) : 0,
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

const CAREER = [
  <Stop
    key="consultant"
    role="Application consultant"
    note="Emails and journeys in SFMC Engagement"
  />,
  <Stop key="developer" role="Developer" />,
  <Stop key="architect" role="Technical architect" note="Two large SFMC clients" />,
  <Stop key="product" role="Product role" note="Our operations briefing platform">
    <ul className="career-work">
      <li>Deeper integrations with sending platforms</li>
      <li>Platform features, exposed externally</li>
      <li>Automation for operations</li>
      <li>New AI capabilities, incl. an MCP server</li>
      <li>Client visits, pitches, partner hackathons (e.g. Adobe)</li>
    </ul>
  </Stop>,
]

function Stop({ role, note, children }: { role: string; note?: string; children?: ReactNode }) {
  return (
    <>
      <strong>{role}</strong>
      {note && <span className="career-note"> · {note}</span>}
      {children}
    </>
  )
}

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
    case 'title':
      return (
        <Slide kicker={KICKER} title="Chris Davies">
          <PrivateMedia name="me.jpg" caption="Chris" />
        </Slide>
      )
    case 'who':
      return (
        <Slide kicker={KICKER} title="Who I am">
          <ul className="about-facts">
            <li>South African</li>
            <li>In Denmark for 10 years</li>
            <li>Studied web development</li>
            <li>7 years in martech</li>
          </ul>
        </Slide>
      )
    case 'career':
      return (
        <Slide kicker={KICKER} title="Career">
          <Reveal label="Career" items={CAREER} />
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
