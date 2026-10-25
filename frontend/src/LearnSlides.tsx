/** Part 2's Learn beat (ADR-0012, screens 4-7): how the idea was picked and what was read. */
import type { ReactNode } from 'react'
import type { Screen, ScreenId } from './deck'
import { PrivateMedia, Reveal, Slide } from './slides'
import './learn.css'

export const LEARN_SCREENS = new Set<ScreenId>(['brief', 'mirofish', 'research', 'gap'])

const OPTIONS: ReactNode[] = [
  <>
    <strong>Option 1: A2A protocols.</strong> A natural next step after a lot of MCP server work,
    but new to me.
  </>,
  <>
    <strong>Option 2: An idea I&rsquo;d parked.</strong> MiroFish&rsquo;s synthetic users, applied
    to marketing: predicting how audiences react to new content.
  </>,
]

const MIROFISH: ReactNode[] = [
  <>
    <strong>Carried forward:</strong> the UI flow (seed → agent graph → simulation → report →
    interview an agent).
  </>,
  <>
    <strong>Why it didn&rsquo;t fit:</strong> it judges by audience consensus, not individual
    behaviour, and its stack needed licences and was costly to set up and run.
  </>,
]

const PAPERS: { name: string; finding: string; change: string }[] = [
  {
    name: 'Stanford (Park et al. 2024)',
    finding:
      'Agents of 1,052 real people, built from interviews, were 85% as accurate as a human retest.',
    change: 'Real individual data works',
  },
  {
    name: 'Synthetic personas (Maiorano 2026)',
    finding: 'On 399 headline A/B tests, a plain LLM picked the winner 49.2%; personas only 34.6%.',
    change: 'Made-up personas hurt',
  },
  {
    name: 'Twin-2K-500 (Toubia et al. 2025)',
    finding: 'Twins of 2,058 people scored 71.7% vs 81.7% human retest. Twins are too “rational”.',
    change: 'Measure calibration',
  },
  {
    name: 'Agent4Rec (SIGIR 2024)',
    finding: 'Precision fell to 21% at realistic base rates; agents rarely dislike things.',
    change: 'Base rates matter',
  },
  {
    name: 'PyMC Labs × Colgate (2025)',
    finding: 'A free-text reaction first, then a score, reached 90% of human test-retest.',
    change: 'Every arm writes a reaction, then p_click',
  },
  {
    name: 'Deng et al. (2026)',
    finding: 'A compact task-specific profile beat the full transcript.',
    change: 'Arm D’s distilled profile',
  },
]

const GAP: ReactNode[] = [
  <>
    <strong>Already explored:</strong> grounding agents in real data, from interviews (Stanford),
    movie histories (Agent4Rec) and retail transactions with fine-tuning (Large Behavior Model,
    2026).
  </>,
  <>
    <strong>My angle:</strong> combine what the research found, one ingredient at a time, on the
    same headlines and real clicks. Off the shelf, no fine-tuning; every arm writes a gut reaction,
    then its click chance.
    <ol className="learn-ladder" aria-label="Arms">
      <li>
        <strong>A</strong> Plain LLM
      </li>
      <li>
        <strong>B</strong> Invented persona
      </li>
      <li>
        <strong>C</strong> + memories of the reader&rsquo;s past clicks
      </li>
      <li>
        <strong>D</strong> + a distilled profile of those clicks
      </li>
      <li>
        <strong>E</strong> D with someone else&rsquo;s clicks: is the gain personal?
      </li>
    </ol>
  </>,
  <p className="learn-question">What makes an AI better at predicting what you’ll click?</p>,
]

export default function LearnSlide({ screen }: { screen: Screen }) {
  return (
    <Slide kicker={screen.section} title={screen.title}>
      <LearnBody id={screen.id} />
    </Slide>
  )
}

function LearnBody({ id }: { id: ScreenId }) {
  switch (id) {
    case 'brief':
      return (
        <>
          <blockquote className="learn-quote">
            &ldquo;Pick a new technology or idea, explore it, build something, explain it.&rdquo;
          </blockquote>
          <Reveal label="Options" items={OPTIONS} />
        </>
      )
    case 'mirofish':
      return (
        <div className="learn-split">
          <div className="learn-media">
            <PrivateMedia name="mirofish-readme.png" caption="MiroFish README on GitHub" />
            <PrivateMedia name="mirofish-ui.png" caption="MiroFish UI" />
          </div>
          <Reveal label="What I took from MiroFish" items={MIROFISH} />
        </div>
      )
    case 'research':
      return (
        <>
          <p className="learn-lede">How well trodden is this?</p>
          <div className="learn-split">
            <Reveal
              label="Reading map"
              items={PAPERS.map((paper) => (
                <>
                  <strong>{paper.name}</strong> {paper.finding}{' '}
                  <span className="learn-change">→ {paper.change}</span>
                </>
              ))}
            />
            <div className="learn-media learn-media-small">
              <PrivateMedia name="paper-stanford.png" caption="Stanford paper, first page" />
              <PrivateMedia name="claude-chat.png" caption="Searching with Claude" />
            </div>
          </div>
          <p className="learn-footnote">
            Found through a mix of Google and Claude. I read every one.
          </p>
        </>
      )
    case 'gap':
      return <Reveal label="The gap and my angle" items={GAP} />
    default:
      return null
  }
}
