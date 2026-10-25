/** Screens 8-10 (ADR-0012): What I built (pipeline and arms), How I tested it, Plan met reality. */
import { ARMS, BASELINES, CONTROL, armClass, type ArmCard } from './arms'
import { Reveal, Slide } from './slides'
import './BuildSlide.css'

function Strip() {
  return (
    <div className="build-strip">
      <div className="build-stage">
        <strong>MIND clicks</strong>
        <span className="muted">≈ email sends and clicks</span>
      </div>
      <span className="build-arrow" aria-hidden="true">
        →
      </span>
      <div className="build-stage">
        <strong>5 arms + 2 baselines</strong>
      </div>
      <span className="build-arrow" aria-hidden="true">
        →
      </span>
      <div className="build-stage">
        <strong>Gemini</strong>
      </div>
      <span className="build-arrow" aria-hidden="true">
        →
      </span>
      <div className="build-stage">
        <strong>Metrics</strong>
      </div>
      <span className="build-arrow" aria-hidden="true">
        →
      </span>
      <div className="build-stage">
        <strong>This app</strong>
      </div>
    </div>
  )
}

/** Made up to show the scoring, not taken from a run. Sorted by the agent's click chance. */
const EXAMPLE = [
  { headline: 'Mortgage rates jump', chance: 70, clicked: true },
  { headline: 'Celebrity divorce', chance: 40, clicked: false },
  { headline: 'New iPhone leak', chance: 30, clicked: false },
  { headline: 'Stock market dips', chance: 25, clicked: false },
  { headline: 'Chiefs win in overtime', chance: 20, clicked: true },
  { headline: 'Weather warning', chance: 15, clicked: false },
  { headline: 'Recipe: easy pasta', chance: 10, clicked: false },
  { headline: 'Royal family news', chance: 5, clicked: false },
]

const TESTING = [
  <div key="example" className="build-part build-test">
    <h3>Scoring one reader</h3>
    <p className="build-note">Made-up numbers; each reader gets 8 headlines, up to 2 clicked.</p>
    <table className="auc-example">
      <thead>
        <tr>
          <th scope="col">Headline</th>
          <th scope="col">Click chance</th>
          <th scope="col">Really clicked?</th>
        </tr>
      </thead>
      <tbody>
        {EXAMPLE.map(({ headline, chance, clicked }) => (
          <tr key={headline} className={clicked ? 'clicked' : undefined}>
            <th scope="row">{headline}</th>
            <td>{chance}</td>
            <td>{clicked ? 'Clicked' : 'Skipped'}</td>
          </tr>
        ))}
      </tbody>
    </table>
    <p>
      Every clicked headline against every skipped one: 2 × 6 = 12 pairs. Mortgage beats all 6,
      Chiefs beats 3, so 9 of 12 are right: <strong>AUC 0.75</strong>. Random ≈ 0.5, perfect = 1.
    </p>
  </div>,
  <div key="tests" className="build-part build-test">
    <h3>The test framework</h3>
    <ul>
      <li>Same headlines, order and prompt in every arm: only what the agent knows changes.</li>
      <li>Each writes a gut reaction, then a 0–100 click chance, at temperature 0.</li>
      <li>Pre-registered before the test run: D − A AUC per reader, with a 95% CI.</li>
      <li>Prompts tuned on a separate 30-user dev set only, then tagged frozen.</li>
      <li>The 300-user test set run once, against popularity and random baselines.</li>
    </ul>
  </div>,
]

function ArmRow({ arm }: { arm: ArmCard }) {
  return (
    <tr className={armClass(arm.id)}>
      <th scope="row">
        {arm.id.length === 1 && <span className="arm-letter">{arm.id.toUpperCase()}</span>}
        {arm.name}
        {arm === CONTROL && <span className="control-tag">control</span>}
      </th>
      <td>{arm.knows}</td>
      <td>{arm.description}</td>
    </tr>
  )
}

/** Every arm in plain language: what its agent is given, and why it is there. */
function ArmsTable() {
  return (
    <table className="arms-table">
      <thead>
        <tr>
          <th scope="col">Arm</th>
          <th scope="col">The agent knows</th>
          <th scope="col">How, and why</th>
        </tr>
      </thead>
      <tbody>
        {[...ARMS, CONTROL].map((arm) => (
          <ArmRow key={arm.id} arm={arm} />
        ))}
      </tbody>
      <tbody>
        <tr>
          <th scope="rowgroup" colSpan={3} className="arms-group">
            Baselines, no AI
          </th>
        </tr>
        {BASELINES.map((baseline) => (
          <ArmRow key={baseline.id} arm={baseline} />
        ))}
      </tbody>
    </table>
  )
}

const CHANGES = [
  <div key="e" className="build-part">
    <h3>Arm E: the wrong twin</h3>
    <p>
      The plan had four arms. If the twin wins, is it because it knows <em>this</em> person, or just
      sounds realistic? So I added a <strong>wrong twin</strong>: arm D given someone else’s
      history.
    </p>
  </div>,
  <div key="power" className="build-part">
    <h3>A bigger test set</h3>
    <p>
      The dev run was noisier than planned, so a power check, set in advance, raised the test set
      from 200 to 300 users before the freeze.
    </p>
  </div>,
  <div key="persona" className="build-part">
    <h3>Not built: a persona inferred from clicks</h3>
    <p>
      Guessing someone&rsquo;s age, job or politics from what they read is the line a brand
      shouldn&rsquo;t cross. Arm D keeps the grounding without the guesswork: what they read, not
      who they are.
    </p>
  </div>,
]

export default function BuildSlide({ id }: { id: 'build' | 'testing' | 'changes' }) {
  if (id === 'build') {
    return (
      <Slide kicker="Tinker" title="What I built">
        <Strip />
        <ArmsTable />
      </Slide>
    )
  }
  return id === 'testing' ? (
    <Slide kicker="Tinker" title="How I tested it">
      <Reveal label="How I tested it" items={TESTING} />
    </Slide>
  ) : (
    <Slide kicker="Tinker" title="Plan met reality">
      <Reveal label="Plan met reality" items={CHANGES} />
    </Slide>
  )
}
