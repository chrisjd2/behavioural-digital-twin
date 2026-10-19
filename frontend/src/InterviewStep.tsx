import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  askAgent,
  fetchRecordedInterview,
  type RecordedInterview,
  type Turn,
} from './api/interview'
import { fetchReport } from './api/report'
import { fetchPopulation, type Headline, type RunSummary } from './api/runs'
import { ARMS, CONTROL } from './arms'
import { IDENTITY_STARTER, SIMULATED_LABEL, STARTERS } from './labels'
import './interview.css'

const ARM_CARDS = Object.fromEntries([...ARMS, CONTROL].map((a) => [a.id.toUpperCase(), a]))
const LLM_ARMS = ['A', 'B', 'C', 'D', 'E']
const DEFAULT_ARM = 'D'

/** What each arm's agent will say about itself, so the audience knows what it is talking to. */
const ARM_NOTES: Record<string, string> = {
  A: 'Knows nothing about this reader: it speaks for a typical reader.',
  B: 'An invented character, not built from this reader’s data. It will say so.',
  C: 'Knows this reader’s past clicks.',
  D: 'Knows this reader’s past clicks and a profile of them.',
  E: 'Control: knows another reader’s clicks and profile, and will say so.',
}

type Readers =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; userIds: string[]; median: string | undefined }

type Entry =
  | { kind: 'question'; text: string }
  | { kind: 'answer'; text: string; mock: boolean; cited: Headline[] }

type Fallback =
  | { state: 'none' }
  | { state: 'loading'; reason: string }
  | { state: 'error'; reason: string; message: string }
  | { state: 'ready'; reason: string; recorded: RecordedInterview }

const messageOf = (error: unknown) => (error instanceof Error ? error.message : 'It failed.')

type Props = { run: RunSummary; mockLlm: boolean }

/**
 * Step 5: ask one agent, in one arm, about its news habits. Replies come live from the server's
 * LLM under the ADR-0007 guardrails; if the call fails or is rate-limited, the recorded
 * exchanges are shown instead, labelled "recorded" (ADR-0008). Render with `key={runId}`.
 */
export default function InterviewStep({ run, mockLlm }: Props) {
  const [readers, setReaders] = useState<Readers>({ state: 'loading' })
  const [userId, setUserId] = useState<string>()
  const arms = LLM_ARMS.filter((a) => run.arms.includes(a))
  const [arm, setArm] = useState(arms.includes(DEFAULT_ARM) ? DEFAULT_ARM : arms[0])

  useEffect(() => {
    let current = true
    // The report only supplies the default reader; a run without arms A and D has no median.
    Promise.all([fetchPopulation(run.run_id), fetchReport(run.run_id).catch(() => null)])
      .then(([population, report]) => {
        if (!current) return
        const userIds = population.agents.map((a) => a.user_id)
        const median = report?.primary?.median_user
        setReaders({ state: 'ready', userIds, median })
        setUserId(median && userIds.includes(median) ? median : userIds[0])
      })
      .catch(
        (error: unknown) => current && setReaders({ state: 'error', message: messageOf(error) }),
      )
    return () => {
      current = false
    }
  }, [run.run_id])

  if (arms.length === 0) {
    return <p className="result-empty">This run has no LLM arms, so there is no agent to ask.</p>
  }
  if (readers.state === 'loading') return <p className="muted">Loading the run’s readers…</p>
  if (readers.state === 'error') {
    return (
      <p role="alert" className="result-error">
        Could not load the run’s readers: {readers.message}
      </p>
    )
  }
  if (readers.userIds.length === 0 || !userId) {
    return <p className="result-empty">This run has no readers to interview.</p>
  }

  return (
    <div className="interview">
      <aside className="interview-setup" aria-label="Who you are interviewing">
        <label className="interview-field">
          <span className="field-label">Reader</span>
          <select value={userId} onChange={(e) => setUserId(e.target.value)}>
            {readers.userIds.map((id) => (
              <option key={id} value={id}>
                {id === readers.median ? `${id} (median reader)` : id}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="interview-arms">
          <legend className="field-label">Arm</legend>
          {arms.map((a) => (
            <label key={a} className={`interview-arm arm-${a.toLowerCase()}`}>
              <input
                type="radio"
                name="interview-arm"
                value={a}
                checked={a === arm}
                onChange={() => setArm(a)}
              />
              <span className="arm-letter">{a}</span>
              <span>
                {ARM_CARDS[a]?.name ?? `Arm ${a}`}
                {a === 'E' && <span className="control-tag">control</span>}
              </span>
            </label>
          ))}
        </fieldset>
        <p className={`interview-arm-note arm-${arm.toLowerCase()}`}>{ARM_NOTES[arm]}</p>
        {mockLlm && <p className="live-runs-note">Interview replies use the MOCK LLM</p>}
      </aside>
      <Chat key={`${userId}:${arm}`} runId={run.run_id} userId={userId} arm={arm} />
    </div>
  )
}

/** One conversation with one agent; a new reader or arm starts a new one. */
function Chat({ runId, userId, arm }: { runId: string; userId: string; arm: string }) {
  const [entries, setEntries] = useState<Entry[]>([])
  const [draft, setDraft] = useState('')
  const [asking, setAsking] = useState(false)
  const [fallback, setFallback] = useState<Fallback>({ state: 'none' })
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' })
  }, [entries, fallback])

  function showRecorded(reason: string) {
    if (fallback.state === 'ready' || fallback.state === 'loading') {
      setFallback({ ...fallback, reason })
      return
    }
    setFallback({ state: 'loading', reason })
    fetchRecordedInterview()
      .then((recorded) => setFallback({ state: 'ready', reason, recorded }))
      .catch((error: unknown) => setFallback({ state: 'error', reason, message: messageOf(error) }))
  }

  function ask(question: string) {
    const text = question.trim()
    if (!text || asking) return
    const asked: Entry[] = [...entries, { kind: 'question', text }]
    const messages: Turn[] = asked.map((e) => ({
      role: e.kind === 'question' ? 'interviewer' : 'agent',
      text: e.text,
    }))
    setEntries(asked)
    setDraft('')
    setAsking(true)
    askAgent({ run_id: runId, user_id: userId, arm, messages })
      .then((reply) =>
        setEntries([
          ...asked,
          { kind: 'answer', text: reply.text, mock: reply.mock, cited: reply.cited },
        ]),
      )
      // The unanswered question stays on screen and in the conversation.
      .catch((error: unknown) => showRecorded(messageOf(error)))
      .finally(() => setAsking(false))
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    ask(draft)
  }

  return (
    <section className={`interview-chat arm-${arm.toLowerCase()}`} aria-label="Interview">
      <p className="simulated-label interview-label">{SIMULATED_LABEL}</p>
      <div className="transcript" aria-live="polite">
        {entries.length === 0 && fallback.state === 'none' && (
          <p className="muted transcript-empty">
            Ask about news interests and reading habits. Questions about who this reader is get “I
            don’t know, it’s not in my data.”
          </p>
        )}
        {entries.map((entry, i) =>
          entry.kind === 'question' ? (
            <Question key={i} text={entry.text} />
          ) : (
            <Answer key={i} arm={arm} text={entry.text} cited={entry.cited} mock={entry.mock} />
          ),
        )}
        {asking && <p className="muted thinking">Agent {arm} is answering…</p>}
        <RecordedFallback fallback={fallback} />
        <div ref={end} />
      </div>
      <div className="starters" aria-label="Suggested questions">
        {STARTERS.map((q) => (
          <button
            key={q}
            type="button"
            className="starter"
            disabled={asking}
            onClick={() => ask(q)}
          >
            {q}
          </button>
        ))}
        <button
          type="button"
          className="starter starter-identity"
          disabled={asking}
          onClick={() => ask(IDENTITY_STARTER)}
          title="An identity question: the agent should say it does not know"
        >
          {IDENTITY_STARTER} <span className="starter-hint">tests the guardrail</span>
        </button>
      </div>
      <form className="composer" onSubmit={onSubmit}>
        <label className="visually-hidden" htmlFor="interview-question">
          Your question
        </label>
        <input
          id="interview-question"
          value={draft}
          maxLength={1000}
          placeholder="Ask about their news habits"
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="primary" disabled={asking || !draft.trim()}>
          Ask
        </button>
      </form>
    </section>
  )
}

function Question({ text }: { text: string }) {
  return (
    <div className="turn turn-question">
      <p>{text}</p>
    </div>
  )
}

function Answer({
  arm,
  text,
  cited,
  mock,
  recorded,
}: {
  arm: string
  text: string
  cited: Headline[]
  mock: boolean
  recorded?: boolean
}) {
  return (
    <div className={`turn turn-answer arm-${arm.toLowerCase()}${recorded ? ' is-recorded' : ''}`}>
      <span className="arm-letter" aria-hidden="true">
        {arm}
      </span>
      <div>
        <p className="turn-tags">
          {recorded && <span className="badge-recorded">recorded</span>}
          {mock && <span className="badge-mock-small">MOCK</span>}
        </p>
        <p className="turn-text">{text}</p>
        {cited.length > 0 && (
          <ul className="cited" aria-label="Past clicks cited">
            {cited.map((h) => (
              <li key={h.news_id}>
                <span className="cited-id">{h.news_id}</span>{' '}
                {h.title ?? 'Headline not in the data'}
                {h.category && <span className="muted"> · {h.category}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function RecordedFallback({ fallback }: { fallback: Fallback }) {
  if (fallback.state === 'none') return null
  const why = (
    <p className="fallback-reason">The live interview is unavailable: {fallback.reason}</p>
  )
  if (fallback.state === 'loading') {
    return (
      <div className="fallback" role="status">
        {why}
        <p className="muted">Loading the recorded exchanges…</p>
      </div>
    )
  }
  if (fallback.state === 'error') {
    return (
      <div className="fallback" role="alert">
        {why}
        <p>The recorded exchanges could not be loaded either: {fallback.message}</p>
      </div>
    )
  }
  const { recorded } = fallback
  return (
    <div className="fallback" role="status">
      {why}
      <p className="fallback-source">
        Showing recorded exchanges instead, with reader {recorded.user_id}, arm {recorded.arm} (
        {ARM_CARDS[recorded.arm]?.name ?? 'unknown arm'}).
      </p>
      {recorded.exchanges.map((e, i) => (
        <div key={i} className="recorded-exchange">
          <Question text={e.question} />
          <Answer
            arm={recorded.arm}
            text={e.answer}
            cited={e.cited}
            mock={recorded.mock}
            recorded
          />
        </div>
      ))}
    </div>
  )
}
