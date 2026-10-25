/** Screens 8-10 (ADR-0012): What I built, The arms, then Plan met reality. */
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
      <ul className="build-stage build-arms" aria-label="Arms and baselines">
        {[...ARMS, CONTROL].map((arm) => (
          <li key={arm.id} className={`build-arm ${armClass(arm.id)}`}>
            <span className="arm-letter">{arm.id.toUpperCase()}</span>
            {arm.name}
            {arm === CONTROL && <span className="control-tag">control</span>}
          </li>
        ))}
        {BASELINES.map((baseline) => (
          <li key={baseline.id} className={`build-arm ${armClass(baseline.id)}`}>
            {baseline.name}
          </li>
        ))}
      </ul>
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

const BUILT = [
  <Strip key="strip" />,
  <div key="task" className="build-part">
    <h3>Every agent, the same task</h3>
    <ul>
      <li>Up to 8 headlines from one real feed, up to 2 of them clicked.</li>
      <li>Same headlines, order and prompt in every arm: only what the agent knows changes.</li>
      <li>Each writes a gut reaction, then a 0–100 click chance, at temperature 0.</li>
    </ul>
  </div>,
  <div key="tests" className="build-part">
    <h3>The test framework</h3>
    <ul>
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

export default function BuildSlide({ id }: { id: 'build' | 'arms' | 'changes' }) {
  if (id === 'arms') {
    return (
      <Slide kicker="Tinker" title="The arms">
        <ArmsTable />
      </Slide>
    )
  }
  return id === 'build' ? (
    <Slide kicker="Tinker" title="What I built">
      <Reveal label="What I built" items={BUILT} />
    </Slide>
  ) : (
    <Slide kicker="Tinker" title="Plan met reality">
      <Reveal label="Plan met reality" items={CHANGES} />
    </Slide>
  )
}
