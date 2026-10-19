import { describe, expect, it } from 'vitest'
import type { RunEvent } from './api/simulation'
import {
  CARD_GAP_MS,
  DEFAULT_SECONDS,
  MAX_CARDS,
  MIN_EVENTS_PER_SECOND,
  REVEAL_MS,
  armProgress,
  eventsPerSecond,
  isRevealed,
  nextArmStart,
  playbackSeconds,
  skipTo,
  start,
  tick,
} from './replay'
import { replayEvents } from './test-fixtures'

describe('eventsPerSecond', () => {
  it('fits a large run into about two minutes at 1x', () => {
    expect(playbackSeconds(14_703, 1)).toBeCloseTo(DEFAULT_SECONDS)
    expect(eventsPerSecond(14_703, 1)).toBeCloseTo(14_703 / 120)
  })

  it('scales with the speed', () => {
    expect(playbackSeconds(14_703, 2)).toBeCloseTo(60)
    expect(playbackSeconds(14_703, 0.5)).toBeCloseTo(240)
  })

  it('counts the time left at the whole run’s pace', () => {
    expect(playbackSeconds(14_703, 1, 14_703 * 0.75)).toBeCloseTo(30)
  })

  it('does not crawl through a small run', () => {
    expect(eventsPerSecond(30, 1)).toBe(MIN_EVENTS_PER_SECOND)
    expect(playbackSeconds(30, 1)).toBeLessThan(DEFAULT_SECONDS)
  })
})

describe('tick', () => {
  const events = replayEvents
  const reactions = (s: ReturnType<typeof start>) => s.cards.map((c) => events[c.index].seq)

  it('advances by elapsed time times the rate and shows the newest reaction', () => {
    const rate = eventsPerSecond(events.length, 1)
    const next = tick(start(), 1000 / rate, events, 1) // one event's worth
    expect(next.position).toBeCloseTo(1)
    const later = tick(next, (3 * 1000) / rate, events, 1)
    expect(later.position).toBeCloseTo(4)
    expect(reactions(later)).toEqual([
      events.findLast((e, i) => i < 4 && e.kind === 'reaction')!.seq,
    ])
  })

  it('admits at most one card per gap, and keeps the newest few', () => {
    let state = start()
    for (let i = 0; i < 40; i++) state = tick(state, CARD_GAP_MS / 4, events, 1)
    expect(state.cards.length).toBeLessThanOrEqual(MAX_CARDS)
    const shownAt = state.cards.map((c) => c.shownAt)
    for (let i = 1; i < shownAt.length; i++) {
      expect(shownAt[i] - shownAt[i - 1]).toBeGreaterThanOrEqual(CARD_GAP_MS)
    }
  })

  it('reveals the real click only after the card has been read', () => {
    const state = tick(start(), 600, events, 1)
    const [card] = state.cards
    expect(isRevealed(card, state.clock)).toBe(false)
    expect(isRevealed(card, card.shownAt + REVEAL_MS)).toBe(true)
  })

  it('stops at the end', () => {
    const end = tick(start(), 10 * 60 * 1000, events, 1)
    expect(end.position).toBe(events.length)
    expect(end.finished).toBe(true)
  })
})

describe('skipping', () => {
  it('jumps to where the next arm starts', () => {
    const firstB = replayEvents.findIndex((e) => 'arm' in e && e.arm === 'B')
    expect(nextArmStart(replayEvents, 0)).toBe(firstB)
    expect(nextArmStart(replayEvents, firstB)).toBe(
      replayEvents.findIndex((e) => 'arm' in e && e.arm === 'random'),
    )
  })

  it('jumps to the end after the last arm', () => {
    const last = replayEvents.findIndex((e) => 'arm' in e && e.arm === 'random')
    expect(nextArmStart(replayEvents, last)).toBe(replayEvents.length)
  })

  it('shows the reaction at the skipped-to point straight away', () => {
    const at = nextArmStart(replayEvents, 0)
    const state = skipTo(start(), at + 3, replayEvents)
    expect(state.position).toBe(at + 3)
    expect(replayEvents[state.cards.at(-1)!.index].kind).toBe('reaction')
    expect((replayEvents[state.cards.at(-1)!.index] as { arm: string }).arm).toBe('B')
  })
})

describe('armProgress', () => {
  it('reports each arm’s latest progress, zero before it starts', () => {
    const progress = armProgress(replayEvents, 0, ['A', 'B', 'random'], 2)
    expect(progress).toEqual([
      { arm: 'A', done: 0, total: 2 },
      { arm: 'B', done: 0, total: 2 },
      { arm: 'random', done: 0, total: 2 },
    ])
    const all = armProgress(replayEvents, replayEvents.length, ['A', 'B', 'random'], 2)
    expect(all.map((p) => p.done)).toEqual([2, 2, 2])
  })

  it('counts only events already played', () => {
    const firstDone = replayEvents.findIndex((e) => e.kind === 'arm_progress')
    const events: RunEvent[] = replayEvents
    expect(armProgress(events, firstDone, ['A'], 2)[0].done).toBe(0)
    expect(armProgress(events, firstDone + 1, ['A'], 2)[0].done).toBe(1)
  })
})
