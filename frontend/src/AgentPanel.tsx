import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import {
  fetchAgent,
  type AgentDetail,
  type ArmKnowledge,
  type Headline,
  type Memory,
  type Profile,
} from './api/runs'
import { ARMS, CONTROL } from './arms'
import { SIMULATED_LABEL } from './labels'

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; agent: AgentDetail }

const ARM_NAMES: Record<string, string> = Object.fromEntries(
  [...ARMS, CONTROL].map((a) => [a.id.toUpperCase(), a.name]),
)

const FIELD_NAMES: Record<string, string> = {
  interests: 'Interests',
  rarely_clicks: 'Rarely clicks',
  style_preferences: 'Style',
  recent_shifts: 'Recent shifts',
}

type Props = { runId: string; userId: string; onClose: () => void }

/**
 * One reader: each arm's tab shows exactly what that arm's agent was given (what it knew, then the
 * headlines it scored); the reader's full history sits apart, since no arm sees all of it.
 * Render with `key={userId}` so another reader starts from a clean state.
 */
export default function AgentPanel({ runId, userId, onClose }: Props) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const title = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    title.current?.focus()
    let current = true
    fetchAgent(runId, userId)
      .then((agent) => current && setLoad({ state: 'ready', agent }))
      .catch(
        (error: unknown) =>
          current &&
          setLoad({
            state: 'error',
            message: error instanceof Error ? error.message : 'The request failed.',
          }),
      )
    return () => {
      current = false
    }
  }, [runId, userId])

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') onClose()
  }

  return (
    <aside className="agent-panel" aria-labelledby="agent-title" onKeyDown={onKeyDown}>
      <div className="agent-head">
        <h3 id="agent-title" ref={title} tabIndex={-1}>
          Reader {userId}
        </h3>
        <button type="button" className="close" onClick={onClose} aria-label="Close reader panel">
          Close
        </button>
      </div>
      <p className="simulated-label">{SIMULATED_LABEL}</p>

      {load.state === 'loading' && <p className="muted">Loading reader {userId}…</p>}
      {load.state === 'error' && (
        <p role="alert" className="result-error">
          Could not load reader {userId}: {load.message}
        </p>
      )}
      {load.state === 'ready' && load.agent.mock && (
        <p className="mock-note">
          <span className="badge-mock">MOCK</span> This run used fake LLM output: its profiles are
          not real model output.
        </p>
      )}
      {load.state === 'ready' && <AgentBody agent={load.agent} />}
    </aside>
  )
}

function AgentBody({ agent }: { agent: AgentDetail }) {
  return (
    <>
      <ArmTabs arms={agent.arms} candidates={agent.candidates} />
      <details className="reader-history">
        <summary>
          The real reader’s past clicks ({agent.history.length}), newest first. No arm is shown all
          of them.
        </summary>
        <HeadlineList items={[...agent.history].reverse()} />
      </details>
    </>
  )
}

function HeadlineList({ items }: { items: Headline[] }) {
  return (
    <ul className="headlines">
      {items.map((h, i) => (
        <li key={`${h.news_id}-${i}`}>
          <span className="headline-category">
            {h.category ? `${h.category} / ${h.subcategory}` : h.news_id}
          </span>
          <span>{h.title ?? 'Headline not in this run’s news file'}</span>
        </li>
      ))}
    </ul>
  )
}

function ArmTabs({ arms, candidates }: { arms: ArmKnowledge[]; candidates: Headline[] }) {
  const [selected, setSelected] = useState(0)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])

  function select(index: number) {
    const next = (index + arms.length) % arms.length
    setSelected(next)
    tabs.current[next]?.focus()
  }

  function onKeyDown(event: KeyboardEvent) {
    const moves: Record<string, number> = {
      ArrowRight: selected + 1,
      ArrowLeft: selected - 1,
      Home: 0,
      End: arms.length - 1,
    }
    if (event.key in moves) {
      event.preventDefault()
      select(moves[event.key])
    }
  }

  if (arms.length === 0) {
    return <p className="result-empty">This run has no LLM arms, so no agent knew anything.</p>
  }
  const current = arms[selected] ?? arms[0]
  const id = (arm: string) => `arm-tab-${arm}`

  return (
    <div className="arm-tabs">
      <div role="tablist" aria-label="What each arm was given" onKeyDown={onKeyDown}>
        {arms.map((k, i) => (
          <button
            key={k.arm}
            ref={(el) => {
              tabs.current[i] = el
            }}
            type="button"
            role="tab"
            id={id(k.arm)}
            className={`arm-tab arm-${k.arm.toLowerCase()}`}
            aria-selected={i === selected}
            aria-controls="arm-tabpanel"
            tabIndex={i === selected ? 0 : -1}
            onClick={() => setSelected(i)}
          >
            <span className="arm-letter">{k.arm}</span>
            <span className="arm-tab-name">{ARM_NAMES[k.arm] ?? `Arm ${k.arm}`}</span>
            {k.kind === 'profile' && k.wrong_twin && <span className="control-tag">control</span>}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="arm-tabpanel"
        aria-labelledby={id(current.arm)}
        className={`arm-panel arm-${current.arm.toLowerCase()}`}
        tabIndex={0}
      >
        <Knowledge knowledge={current} />
        <section className="arm-feed" aria-labelledby="feed-title">
          <h5 id="feed-title">The {candidates.length} headlines it scored</h5>
          <p className="muted small">The same for every arm. Clicks are revealed in Simulation.</p>
          <HeadlineList items={candidates} />
        </section>
      </div>
    </div>
  )
}

function Knowledge({ knowledge }: { knowledge: ArmKnowledge }) {
  switch (knowledge.kind) {
    case 'nothing':
      return (
        <p className="knows-nothing">
          Knows nothing about this reader. It predicts for “a typical Microsoft News reader”.
        </p>
      )
    case 'persona': {
      const p = knowledge.persona
      return (
        <>
          <p className="invented-banner">Made up — not from this user’s data</p>
          <p className="persona-name">{p.name}</p>
          <p>
            {p.age}, {p.job}, {p.location} ({p.life_stage})
          </p>
          <dl className="persona">
            <dt>Personality</dt>
            <dd>
              {Object.entries(p.big_five)
                .map(([trait, level]) => `${level} ${trait}`)
                .join(', ')}
            </dd>
            <dt>Values</dt>
            <dd>{p.values.join(' and ')}</dd>
            <dt>News habit</dt>
            <dd>{p.news_habit}</dd>
          </dl>
        </>
      )
    }
    case 'memories':
      return <Memories memories={knowledge.memories} />
    case 'profile':
      return (
        <>
          {knowledge.wrong_twin && (
            <p className="wrong-twin">
              <span className="control-tag">control</span> Someone else’s profile and clicks:
              borrowed from reader {knowledge.wrong_twin.donor}
              {knowledge.wrong_twin.shared_history !== null &&
                `, who shares ${knowledge.wrong_twin.shared_history} past clicks with this reader`}
              .
            </p>
          )}
          <ProfileView profile={knowledge.profile} />
          <Memories memories={knowledge.memories} />
        </>
      )
  }
}

function ProfileView({ profile }: { profile: Profile }) {
  const hits = profile.identity_hits
  return (
    <section className="profile" aria-label="Distilled profile">
      <h5>Distilled profile</h5>
      {!profile.ok && (
        <p className="notice">
          This profile was unusable, so the agent never saw it: its prompt was arm C’s.
        </p>
      )}
      {profile.fields.map(({ field, items }) => (
        <div key={field} className="profile-field">
          <p className="profile-field-name">{FIELD_NAMES[field] ?? field}</p>
          <ul>
            {items.map((item, i) => (
              <li key={i}>
                <p>{item.text}</p>
                <ul className="evidence" aria-label="Evidence">
                  {item.evidence.map((e, j) => (
                    <li key={`${e.news_id}-${j}`}>{e.title ?? e.news_id}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {hits.length === 0 ? (
        <p className="muted small">Identity screen: no flags.</p>
      ) : (
        <div className="notice">
          <p>
            Identity screen flagged {hits.length} {hits.length === 1 ? 'claim' : 'claims'} about who
            the reader is. A person reviews every flag.
          </p>
          <ul>
            {hits.map((h, i) => (
              <li key={i}>
                {h.kind}: “{h.term}” in “{h.text}”
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function Memories({ memories }: { memories: Memory[] }) {
  return (
    <section className="memories" aria-label="Memories">
      <h5>Memories ({memories.length})</h5>
      <ul className="headlines">
        {memories.map((m, i) => (
          <li key={`${m.news_id}-${i}`}>
            <span className="headline-category">{m.category}</span>
            <span>{m.headline}</span>
            <span className="reason">{reason(m.reason)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function reason(text: string): string {
  if (text === 'recent') return 'Recent click'
  return text.charAt(0).toUpperCase() + text.slice(1)
}
