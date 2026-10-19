import { describe, expect, it } from 'vitest'
import type { RunEvent } from './api/simulation'
import {
  ARM_BEAT_MS,
  COMPARISONS,
  REVEAL_BEAT_MS,
  buildComparisons,
  frameAt,
  nextReaderStart,
  startTimes,
  type Comparison,
} from './byReader'
import { replayEvents } from './test-fixtures'

const ARMS = ['A', 'B', 'random']

describe('buildComparisons', () => {
  it('follows the run’s sampling order, not the order events arrived in', () => {
    const comparisons = buildComparisons(replayEvents, ['U2', 'U1'], ARMS)
    expect(comparisons.map((c) => c.user_id)).toEqual(['U2', 'U1'])
  })

  it('alternates a clicked and an unclicked headline, first in feed order', () => {
    const [first, second] = buildComparisons(replayEvents, ['U1', 'U2'], ARMS)
    expect([first.news_id, first.clicked]).toEqual(['N9', true])
    expect([second.news_id, second.clicked]).toEqual(['N10', false])
  })

  it('lists the same headline’s reaction from every LLM arm, in the run’s arm order', () => {
    const [first] = buildComparisons(replayEvents, ['U1'], ['B', 'A', 'random'])
    expect(first.reactions.map((r) => [r.arm, r.user_id, r.news_id])).toEqual([
      ['B', 'U1', 'N9'],
      ['A', 'U1', 'N9'],
    ])
  })

  it('never looks at p_click, so no arm’s wins can steer the choice', () => {
    const flipped: RunEvent[] = replayEvents.map((e) =>
      e.kind === 'reaction' ? { ...e, p_click: 100 - e.p_click } : e,
    )
    const key = (cs: Comparison[]) => cs.map((c) => `${c.user_id}/${c.news_id}`)
    expect(key(buildComparisons(flipped, ['U1', 'U2'], ARMS))).toEqual(
      key(buildComparisons(replayEvents, ['U1', 'U2'], ARMS)),
    )
  })

  it('stops at the limit and skips readers with no reactions', () => {
    expect(
      buildComparisons(replayEvents, ['U9', 'U1', 'U2'], ARMS, 1).map((c) => c.user_id),
    ).toEqual(['U1'])
  })
})

describe('by-reader timing', () => {
  const comparisons = buildComparisons(replayEvents, ['U1', 'U2'], ARMS)
  const starts = startTimes(comparisons)
  const each = 2 * ARM_BEAT_MS + REVEAL_BEAT_MS

  it('gives each comparison a beat per arm plus the reveal', () => {
    expect(starts).toEqual([0, each, 2 * each])
  })

  it('fits about 20 five-arm comparisons into two minutes at 1x', () => {
    expect((COMPARISONS * (5 * ARM_BEAT_MS + REVEAL_BEAT_MS)) / 1000).toBeCloseTo(122, 0)
  })

  it('shows arms one by one, then reveals the real click', () => {
    expect(frameAt(comparisons, starts, 0)).toEqual({
      index: 0,
      shown: 1,
      revealed: false,
      finished: false,
    })
    expect(frameAt(comparisons, starts, ARM_BEAT_MS).shown).toBe(2)
    expect(frameAt(comparisons, starts, 2 * ARM_BEAT_MS).revealed).toBe(true)
    expect(frameAt(comparisons, starts, each).index).toBe(1)
    expect(frameAt(comparisons, starts, 2 * each).finished).toBe(true)
  })

  it('skips to the next reader, then the end', () => {
    expect(nextReaderStart(starts, 10)).toBe(each)
    expect(nextReaderStart(starts, each)).toBe(2 * each)
    expect(nextReaderStart(starts, 2 * each)).toBe(2 * each)
  })

  it('treats a run with no reactions as finished', () => {
    expect(frameAt([], [0], 0).finished).toBe(true)
  })
})
