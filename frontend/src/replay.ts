import type { RunEvent } from './api/simulation'

/**
 * Replay timing (ADR-0008): a saved run plays back event by event, evenly paced, so the whole
 * run fits about two minutes at 1x whatever its real timing was (cached calls finish in
 * milliseconds, fresh ones take minutes). The feed admits one card per gap so it stays readable.
 */
export const DEFAULT_SECONDS = 120
export const MIN_EVENTS_PER_SECOND = 4
export const SPEEDS = [0.5, 1, 2, 4] as const
export const CARD_GAP_MS = 1400
export const REVEAL_MS = 900
export const MAX_CARDS = 4

export type Card = { index: number; shownAt: number } // event index; playback clock in ms
export type Playback = {
  position: number // events played, fractional
  clock: number // ms spent playing; paused time does not count
  cards: Card[] // oldest first
  finished: boolean
}

export function eventsPerSecond(nEvents: number, speed: number): number {
  return Math.max(nEvents / DEFAULT_SECONDS, MIN_EVENTS_PER_SECOND) * speed
}

/** Seconds to play from event `from` to the end, at the whole run's pace. */
export function playbackSeconds(nEvents: number, speed: number, from = 0): number {
  return (nEvents - from) / eventsPerSecond(nEvents, speed)
}

export function start(): Playback {
  return { position: 0, clock: 0, cards: [], finished: false }
}

/** The index of the newest reaction among the first `played` events, or -1. */
function latestReaction(events: RunEvent[], played: number): number {
  for (let i = Math.min(played, events.length) - 1; i >= 0; i--) {
    if (events[i].kind === 'reaction') return i
  }
  return -1
}

function withCard(state: Playback, events: RunEvent[]): Playback {
  const index = latestReaction(events, Math.floor(state.position))
  const last = state.cards.at(-1)
  if (index < 0 || (last && last.index >= index)) return state
  const cards = [...state.cards, { index, shownAt: state.clock }].slice(-MAX_CARDS)
  return { ...state, cards }
}

/** Advance by `dtMs` of wall time at `speed`. */
export function tick(state: Playback, dtMs: number, events: RunEvent[], speed: number): Playback {
  const rate = eventsPerSecond(events.length, speed)
  const position = Math.min(events.length, state.position + (dtMs / 1000) * rate)
  const next = {
    ...state,
    position,
    clock: state.clock + dtMs,
    finished: position >= events.length,
  }
  const last = next.cards.at(-1)
  return last && next.clock - last.shownAt < CARD_GAP_MS ? next : withCard(next, events)
}

/** Jump to an event; the reaction there shows at once. */
export function skipTo(state: Playback, position: number, events: RunEvent[]): Playback {
  const target = Math.min(events.length, Math.max(0, position))
  return withCard({ ...state, position: target, finished: target >= events.length }, events)
}

export function isRevealed(card: Card, clock: number): boolean {
  return clock - card.shownAt >= REVEAL_MS
}

function armOf(event: RunEvent | undefined): string | undefined {
  return event && 'arm' in event ? event.arm : undefined
}

/** Where the arm after the one playing at `position` starts (arms run one after another). */
export function nextArmStart(events: RunEvent[], position: number): number {
  const from = Math.floor(position)
  const current = armOf(events[from])
  for (let i = from + 1; i < events.length; i++) {
    const arm = armOf(events[i])
    if (arm !== undefined && arm !== current) return i
  }
  return events.length
}

export type Progress = { arm: string; done: number; total: number }

/** Each arm's progress after the first `played` events; `total` until an arm reports its own. */
export function armProgress(
  events: RunEvent[],
  played: number,
  arms: string[],
  total: number,
): Progress[] {
  const latest = new Map<string, Progress>()
  for (let i = 0; i < Math.min(played, events.length); i++) {
    const event = events[i]
    if (event.kind === 'arm_progress') latest.set(event.arm, event)
  }
  return arms.map((arm) => {
    const p = latest.get(arm)
    return { arm, done: p?.done ?? 0, total: p?.total ?? total }
  })
}
