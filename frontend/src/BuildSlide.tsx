/** Screen 8, What I built (ADR-0012): the pipeline and two plan changes. */
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

const PARTS = [
  <Strip key="strip" />,
  <div key="e" className="build-part">
    <h3>Plan met reality: arm E</h3>
    <p>
      The plan had four arms. If the twin wins, is it because it knows <em>this</em> person, or just
      sounds realistic? So I added a <strong>wrong twin</strong>: arm D given someone else’s
      history.
    </p>
  </div>,
  <div key="prereg" className="build-part">
    <h3>Plan met reality: pre-registration</h3>
    <ul>
      <li>
        Before the test set: primary metric and decision rule committed, prompts tagged frozen.
      </li>
      <li>A power check raised the test set from 200 to 300 users.</li>
      <li>Prompts tuned on a separate 30-user dev set only.</li>
    </ul>
  </div>,
]

export default function BuildSlide() {
  return (
    <Slide kicker="Tinker" title="What I built">
      <Reveal label="What I built" items={PARTS} />
    </Slide>
  )
}
