import { describe, expect, it } from 'vitest'
import { largestFit } from './fit'

describe('largestFit', () => {
  it('finds the largest zoom that still fits, to within a hundredth', () => {
    expect(largestFit((zoom) => zoom <= 1.37, 2)).toBeCloseTo(1.37, 2)
  })

  it('stops at the cap when everything fits', () => {
    expect(largestFit(() => true, 2)).toBe(2)
  })

  it('never shrinks below 1, even when 1 does not fit', () => {
    expect(largestFit(() => false, 2)).toBe(1)
  })

  it('never returns a zoom that does not fit', () => {
    const limit = 1.555
    expect(largestFit((zoom) => zoom <= limit, 2)).toBeLessThanOrEqual(limit)
  })
})
