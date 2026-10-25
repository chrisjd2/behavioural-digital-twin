import { useEffect, useReducer, useRef, useState } from 'react'
import { fetchHook, type HookCall, type HookExample, type HookReveal } from './api/hook'
import type { Headline } from './api/runs'
import { ARMS } from './arms'
import './hook.css'
import { isTyping } from './deck'
import { commandFor, INITIAL, step } from './hookState'
import { SIMULATED_LABEL } from './labels'

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; example: HookExample }

const QUESTION = 'Can an AI predict which headlines you’ll click?'

const PROMPTS = {
  guess: 'Which headline did this reader click? Vote 1 or 2.',
  history: 'Here is what they clicked before. Vote again.',
  reveal: 'The real click, and what two AI agents predicted.',
}

function armName(arm: string): string {
  return ARMS.find((a) => a.id === arm.toLowerCase())?.name ?? `Arm ${arm}`
}

function toggleFullscreen(element: HTMLElement | null) {
  if (document.fullscreenElement) void document.exitFullscreen()
  else void element?.requestFullscreen?.()
}

/** MIND's category and subcategory, e.g. "news / newsus": what links a headline to the history. */
function topic(headline: Headline): string {
  return [headline.category ?? 'unknown', headline.subcategory].filter(Boolean).join(' / ')
}

function title(headline: Headline): string {
  return headline.title ?? `${headline.news_id} (headline not in the data)`
}

/** Reports the shown run up to App, whose MOCK badge describes the run on screen. */
export default function HookStep({ onRunMock }: { onRunMock: (mock: boolean) => void }) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [state, dispatch] = useReducer(step, INITIAL)
  const stageRef = useRef<HTMLElement>(null)

  useEffect(() => {
    fetchHook()
      .then((example) => {
        setLoad({ state: 'ready', example })
        onRunMock(example.mock)
      })
      .catch((error: unknown) =>
        setLoad({
          state: 'error',
          message: error instanceof Error ? error.message : 'The example could not be loaded.',
        }),
      )
  }, [onRunMock])

  const stateRef = useRef(state)
  stateRef.current = state

  useEffect(() => {
    // On document, so it runs before the presenter deck's window listener (ADR-0012).
    function onKey(event: KeyboardEvent) {
      if (isTyping(event.target)) return
      const command = commandFor(event)
      if (!command) return
      if (command === 'fullscreen') toggleFullscreen(stageRef.current)
      // A key with no stage to go to is left for the deck: the slide before or after.
      else if (step(stateRef.current, command) === stateRef.current) return
      else dispatch(command)
      event.preventDefault()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const revealed = state.stage === 'reveal'
  const prompt = revealed ? PROMPTS.reveal : state.history ? PROMPTS.history : PROMPTS.guess

  return (
    <section ref={stageRef} className="hook" aria-labelledby="step-title">
      {/* The stepper already shows the step; the row is kept for the prompt and the label. */}
      <h2 id="step-title" className="hook-kicker">
        Step 0 Hook
      </h2>
      <div className="hook-top">
        <p className="hook-prompt" aria-live="polite">
          {state.stage !== 'title' && load.state === 'ready' ? prompt : ''}
        </p>
        <p className="hook-stamp">Illustrative example (dev set)</p>
      </div>

      {state.stage === 'title' ? (
        <div className="hook-title">
          <p className="hook-question">{QUESTION}</p>
          <p className="hook-sub">
            One real reader. Two headlines from their feed. You be the twin.
          </p>
        </div>
      ) : load.state === 'loading' ? (
        <p className="muted hook-body">Loading the example…</p>
      ) : load.state === 'error' ? (
        <p role="alert" className="error hook-body">
          The hook example could not be loaded: {load.message}
        </p>
      ) : (
        <div className="hook-body">
          {(load.example.mock || load.example.data_source === 'synthetic') && (
            <p className="hook-caveat">
              {load.example.mock && 'Mock run: the predictions are fake LLM output, not results. '}
              {load.example.data_source === 'synthetic' && 'Synthetic data: fake headlines.'}
            </p>
          )}
          <div className={`hook-cards${state.history || revealed ? ' is-compact' : ''}`}>
            {load.example.headlines.map((headline, i) => (
              <HookCard
                key={headline.news_id}
                number={i + 1}
                headline={headline}
                clicked={revealed ? headline.news_id === load.example.reveal.clicked_id : undefined}
              />
            ))}
          </div>
          {state.history && !revealed && <History history={load.example.history} />}
          {revealed && <Scores reveal={load.example.reveal} />}
          {/* ADR-0007: the reveal shows agent reactions, also in full screen without the footer. */}
          {revealed && <p className="hook-simulated">{SIMULATED_LABEL}</p>}
        </div>
      )}

      <div className="hook-controls">
        <div className="hook-buttons">
          <button type="button" onClick={() => dispatch('prev')} disabled={state.stage === 'title'}>
            Back
          </button>
          <button
            type="button"
            aria-pressed={state.history}
            onClick={() => dispatch('history')}
            disabled={state.stage !== 'guess'}
          >
            Show what this reader clicked before
          </button>
          <button
            type="button"
            onClick={() => dispatch('reveal')}
            disabled={state.stage === 'title'}
          >
            {revealed ? 'Hide the real click' : 'Reveal the real click'}
          </button>
          <button type="button" onClick={() => dispatch('next')} disabled={revealed}>
            Next
          </button>
        </div>
        <p className="hook-keys">
          Keys: <kbd>←</kbd> <kbd>→</kbd> step, <kbd>H</kbd> history, <kbd>R</kbd> reveal,{' '}
          <kbd>F</kbd> full screen
        </p>
      </div>
    </section>
  )
}

/** `clicked` is undefined until the reveal. */
function HookCard({
  number,
  headline,
  clicked,
}: {
  number: number
  headline: Headline
  clicked: boolean | undefined
}) {
  const verdict = clicked === undefined ? '' : clicked ? ' is-clicked' : ' is-skipped'
  return (
    <article className={`hook-card${verdict}`} aria-label={`Headline ${number}`}>
      <span className="hook-card-number" aria-hidden="true">
        {number}
      </span>
      <p className="hook-card-category">{topic(headline)}</p>
      <p className="hook-card-title">{title(headline)}</p>
      {clicked !== undefined && (
        <p className="hook-verdict">{clicked ? 'They clicked this' : 'They skipped this'}</p>
      )}
    </article>
  )
}

/** The agent's pick is the headline it scored higher; a tie is no pick. */
function pick(calls: HookCall[]): number | undefined {
  const [first, second] = calls
  if (first.p_click === second.p_click) return undefined
  return first.p_click > second.p_click ? 0 : 1
}

function Scores({ reveal }: { reveal: HookReveal }) {
  return (
    <section className="hook-scores" aria-labelledby="hook-scores-title">
      <h3 id="hook-scores-title">
        Each agent scored both headlines. Its pick is the higher score.
      </h3>
      <ol>
        {reveal.predictions.map(({ arm, calls }) => {
          const picked = pick(calls)
          const right = picked !== undefined && calls[picked].news_id === reveal.clicked_id
          return (
            <li
              key={arm}
              aria-label={armName(arm)}
              className={`hook-score arm-${arm.toLowerCase()}`}
            >
              <p className="hook-arm">
                <span className="arm-letter">{arm}</span> {armName(arm)}
              </p>
              <p
                className={`hook-call${picked === undefined ? '' : right ? ' is-right' : ' is-wrong'}`}
              >
                {picked === undefined
                  ? 'Scored both the same'
                  : `${right ? '✓' : '✗'} Picked headline ${picked + 1}: ${right ? 'right' : 'wrong'}`}
              </p>
              <ul className="hook-bars">
                {calls.map((call, i) => (
                  <li
                    key={call.news_id}
                    className={call.news_id === reveal.clicked_id ? 'is-clicked' : undefined}
                  >
                    <span className="hook-bar-number">{i + 1}</span>
                    <span className="hook-bar" aria-hidden="true">
                      <span style={{ width: `${call.p_click}%` }} />
                    </span>
                    <strong className="hook-bar-p">{Math.round(call.p_click)}%</strong>
                    <q className="hook-reaction">{call.reaction}</q>
                  </li>
                ))}
              </ul>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function History({ history }: { history: Headline[] }) {
  return (
    <section className="hook-history" aria-labelledby="hook-history-title">
      <h3 id="hook-history-title">What this reader clicked before</h3>
      <p className="hook-history-note">Oldest first; the most recent click is last.</p>
      {history.length === 0 ? (
        <p className="muted">This reader has no earlier clicks in the data.</p>
      ) : (
        <ol>
          {history.map((h) => (
            <li key={h.news_id}>
              <span className="hook-category">{topic(h)}</span> {title(h)}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
