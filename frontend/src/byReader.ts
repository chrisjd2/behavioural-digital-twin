import type { Reaction, RunEvent } from './api/simulation'

/**
 * "By reader" replay: the same reader's headline through every LLM arm in turn, then the real
 * click. The order is declared up front, never chosen by outcome: the first COMPARISONS readers
 * in the run's seeded sampling order; for each, alternately (from the first) their first
 * clicked and their first unclicked headline in feed order. No arm's p_click is looked at.
 */
export const COMPARISONS = 20
export const ARM_BEAT_MS = 900
export const REVEAL_BEAT_MS = 1600

export type Comparison = {
  user_id: string
  news_id: string
  headline: string
  clicked: boolean
  reactions: Reaction[] // in the run's arm order
}

export function buildComparisons(
  events: RunEvent[],
  readers: string[],
  arms: string[],
  limit = COMPARISONS,
): Comparison[] {
  // user -> news (in feed order: each call emits its headlines in display order) -> reactions
  const reactions = new Map<string, Map<string, Reaction[]>>()
  for (const event of events) {
    if (event.kind !== 'reaction') continue
    const feed = reactions.get(event.user_id) ?? new Map<string, Reaction[]>()
    reactions.set(event.user_id, feed)
    feed.set(event.news_id, [...(feed.get(event.news_id) ?? []), event])
  }
  const rank = (r: Reaction) => arms.indexOf(r.arm)
  const comparisons: Comparison[] = []
  for (const user_id of readers) {
    const feed = reactions.get(user_id)
    if (!feed) continue
    const items = [...feed.values()]
    const wantClicked = comparisons.length % 2 === 0
    const chosen = items.find((rs) => rs[0].clicked === wantClicked) ?? items[0]
    const { news_id, headline, clicked } = chosen[0]
    comparisons.push({
      user_id,
      news_id,
      headline,
      clicked,
      reactions: [...chosen].sort((a, b) => rank(a) - rank(b)),
    })
    if (comparisons.length === limit) break
  }
  return comparisons
}

export function comparisonMs(c: Comparison): number {
  return c.reactions.length * ARM_BEAT_MS + REVEAL_BEAT_MS
}

/** When each comparison starts, in playback ms at 1x; the last entry is the total. */
export function startTimes(comparisons: Comparison[]): number[] {
  const starts = [0]
  for (const c of comparisons) starts.push(starts.at(-1)! + comparisonMs(c))
  return starts
}

export type ReaderFrame = {
  index: number // the comparison on screen
  shown: number // how many of its arms' reactions are showing
  revealed: boolean
  finished: boolean
}

export function frameAt(comparisons: Comparison[], starts: number[], elapsed: number): ReaderFrame {
  const total = starts.at(-1)!
  if (comparisons.length === 0 || elapsed >= total) {
    const last = comparisons.at(-1)
    return {
      index: comparisons.length - 1,
      shown: last?.reactions.length ?? 0,
      revealed: true,
      finished: true,
    }
  }
  let index = 0
  while (starts[index + 1] <= elapsed) index++
  const within = elapsed - starts[index]
  const arms = comparisons[index].reactions.length
  return {
    index,
    shown: Math.min(arms, Math.floor(within / ARM_BEAT_MS) + 1),
    revealed: within >= arms * ARM_BEAT_MS,
    finished: false,
  }
}

/** Where the comparison after the one at `elapsed` starts (or the end). */
export function nextReaderStart(starts: number[], elapsed: number): number {
  return starts.find((s) => s > elapsed) ?? starts.at(-1)!
}
