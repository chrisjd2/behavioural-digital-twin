/** Screens 8-9 (ADR-0012): What I built (the system and its test framework), then Plan met reality. */
import { ARMS, BASELINES, CONTROL, armClass } from './arms'
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
]

export default function BuildSlide({ id }: { id: 'build' | 'changes' }) {
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
