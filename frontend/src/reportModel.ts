/** Pure helpers for the Report step: chart geometry, number formats, bucket browsing. */
import type { Bucket, Estimate, NotResultReason, PrimaryOutcome } from './api/report'
import { ARMS, BASELINES, CONTROL } from './arms'

export type Domain = [number, number]

/** Where `value` falls on a track, as a percentage of its width, clamped to the track. */
export function position(value: number, [min, max]: Domain): number {
  return Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100))
}

export type CiBar = { start: number; width: number; mean: number; low: number; high: number }

/** A bar from zero to the mean with whiskers at the 95% CI, all in % of the track. */
export function ciBar(estimate: Estimate, domain: Domain): CiBar {
  const zero = position(0, domain)
  const mean = position(estimate.mean, domain)
  return {
    start: Math.min(zero, mean),
    width: Math.abs(mean - zero),
    mean,
    low: position(estimate.low, domain),
    high: position(estimate.high, domain),
  }
}

/** `value` rounded up to a multiple of `step`, so axes end on a tidy tick. */
export function niceMax(value: number, step: number): number {
  return Math.ceil(value / step - 1e-9) * step
}

/** Three decimals with a sign and a true minus (U+2212). */
export function signed(value: number): string {
  const text = Math.abs(value).toFixed(3)
  return value < 0 && text !== '0.000' ? `−${text}` : `+${text}`
}

export const decimal = (value: number) => value.toFixed(3)
export const percent = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`

/** The pre-registered outcome: the D − A estimate, its CI and the verdict the run stored. */
export function outcomeLine({ difference, verdict }: PrimaryOutcome): string {
  const { mean, low, high } = difference
  return `D − A AUC ${signed(mean)} [${signed(low)}, ${signed(high)}]: ${verdict}`
}

export function notResultText(reasons: NotResultReason[]): string {
  return `NOT A RESULT: ${reasons.join(', ')}`
}

export function bucketCounts(primary: PrimaryOutcome): Record<Bucket, number> {
  return Object.fromEntries(primary.buckets.map((b) => [b.bucket, b.users.length])) as Record<
    Bucket,
    number
  >
}

/** Which user the drill-down shows: the median user, or one user of a bucket. */
export type Browse = { mode: 'median' } | { mode: 'bucket'; bucket: Bucket; index: number }

function bucketUsers(primary: PrimaryOutcome, bucket: Bucket) {
  return primary.buckets.find((b) => b.bucket === bucket)?.users ?? []
}

export function currentUser(browse: Browse, primary: PrimaryOutcome): string | undefined {
  if (browse.mode === 'median') return primary.median_user
  return bucketUsers(primary, browse.bucket)[browse.index]?.user_id
}

/** The next (`1`) or previous (`-1`) user in the bucket, wrapping at either end. */
export function stepBrowse(browse: Browse, delta: 1 | -1, primary: PrimaryOutcome): Browse {
  if (browse.mode === 'median') return browse
  const size = bucketUsers(primary, browse.bucket).length
  if (size === 0) return browse
  return { ...browse, index: (browse.index + delta + size) % size }
}

const NAMES: Record<string, string> = Object.fromEntries(
  [...ARMS, CONTROL, ...BASELINES].map((card) => [card.id, card.name]),
)

/** Plain-language arm name, e.g. "Plain LLM" for A and "Popularity" for popularity. */
export function armName(arm: string): string {
  return NAMES[arm.toLowerCase()] ?? arm
}

/** The CSS class carrying an arm's colour; baselines fall back to grey. */
export function armClass(arm: string): string {
  return `arm-${arm.toLowerCase()}`
}

/** "A", "B"... for arms; baselines have no letter. */
export function armLetter(arm: string): string | undefined {
  return arm.length === 1 ? arm : undefined
}
