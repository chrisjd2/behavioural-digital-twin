import { describe, expect, it } from 'vitest'
import type { OutcomeBucket, PrimaryOutcome } from './api/report'
import {
  bucketCounts,
  ciBar,
  currentUser,
  niceMax,
  notResultText,
  outcomeLine,
  position,
  signed,
  stepBrowse,
  type Browse,
} from './reportModel'

describe('CI bar geometry', () => {
  it('places the bar from zero to the mean and whiskers at the CI, in % of the track', () => {
    expect(ciBar({ mean: 0.5, low: 0.4, high: 0.6 }, [0, 1])).toEqual({
      start: 0,
      width: 50,
      mean: 50,
      low: 40,
      high: 60,
    })
  })

  it('maps onto a domain that does not start at zero', () => {
    const bar = ciBar({ mean: 0.1, low: -0.1, high: 0.2 }, [-0.2, 0.2])
    expect(bar.start).toBeCloseTo(50)
    expect(bar.width).toBeCloseTo(25)
    expect(bar.low).toBeCloseTo(25)
    expect(bar.high).toBeCloseTo(100)
  })

  it('draws a negative bar leftwards from zero', () => {
    const bar = ciBar({ mean: -0.1, low: -0.15, high: -0.05 }, [-0.2, 0.2])
    expect(bar.start).toBeCloseTo(25)
    expect(bar.width).toBeCloseTo(25)
  })

  it('clamps positions to the track', () => {
    expect(position(1.5, [0, 1])).toBe(100)
    expect(position(-1, [0, 1])).toBe(0)
  })

  it('rounds a domain maximum up to a tidy step', () => {
    expect(niceMax(0.459, 0.1)).toBeCloseTo(0.5)
    expect(niceMax(0.5, 0.1)).toBeCloseTo(0.5)
  })
})

const bucket = (name: OutcomeBucket['bucket'], ids: string[]): OutcomeBucket => ({
  bucket: name,
  users: ids.map((user_id, i) => ({ user_id, d_minus_a: 0.5 - i * 0.1 })),
})

const primary: PrimaryOutcome = {
  difference: { mean: 0.1468452380952381, low: 0.10170188492063492, high: 0.19148571428571426 },
  verdict: 'twins beat plain LLM',
  buckets: [
    bucket('Twin better', ['U1', 'U2', 'U3']),
    bucket('About the same', ['U4']),
    bucket('Plain LLM better', []),
  ],
  bucket_threshold: 0.1,
  median_user: 'U4',
}

describe('primary outcome', () => {
  it('states D − A with its CI and the stored verdict verbatim', () => {
    expect(outcomeLine(primary)).toBe('D − A AUC +0.147 [+0.102, +0.191]: twins beat plain LLM')
    expect(outcomeLine({ ...primary, verdict: 'no detectable difference' })).toMatch(
      /: no detectable difference$/,
    )
  })

  it('signs numbers with a true minus', () => {
    expect(signed(-0.0426)).toBe('−0.043')
    expect(signed(0)).toBe('+0.000')
  })
})

describe('outcome buckets', () => {
  it('counts the users in each bucket', () => {
    expect(bucketCounts(primary)).toEqual({
      'Twin better': 3,
      'About the same': 1,
      'Plain LLM better': 0,
    })
  })

  it('opens on the median user', () => {
    expect(currentUser({ mode: 'median' }, primary)).toBe('U4')
  })

  it('steps through a bucket’s users and wraps at either end', () => {
    let browse: Browse = { mode: 'bucket', bucket: 'Twin better', index: 0 }
    expect(currentUser(browse, primary)).toBe('U1')
    browse = stepBrowse(browse, 1, primary)
    expect(currentUser(browse, primary)).toBe('U2')
    browse = stepBrowse(stepBrowse(browse, 1, primary), 1, primary)
    expect(currentUser(browse, primary)).toBe('U1')
    browse = stepBrowse(browse, -1, primary)
    expect(currentUser(browse, primary)).toBe('U3')
  })

  it('has no user in an empty bucket', () => {
    expect(currentUser({ mode: 'bucket', bucket: 'Plain LLM better', index: 0 }, primary)).toBe(
      undefined,
    )
  })
})

describe('not-a-result banner', () => {
  it('names every reason', () => {
    expect(notResultText(['mock', 'dev', 'synthetic'])).toBe('NOT A RESULT: MOCK, dev, synthetic')
    expect(notResultText(['unfrozen'])).toBe('NOT A RESULT: unfrozen')
  })
})
