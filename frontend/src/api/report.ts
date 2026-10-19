import { requestJson } from './client'
import type { Headline } from './runs'

/** Mirrors `backend.report_views.Estimate`. */
export type Estimate = { mean: number; low: number; high: number }

/** Mirrors `backend.report_views.Calibration`. Probabilities, 0-1. */
export type Calibration = { mean_p_click: number; feed_ctr: number; sample_ctr: number }

export type MetricName = 'auc' | 'mrr' | 'ndcg5' | 'hit1'

/** Mirrors `backend.report_views.ArmKind`. */
export type ArmKind = 'llm' | 'baseline'

/** Mirrors `backend.report_views.ArmReport`. */
export type ArmReport = {
  arm: string
  kind: ArmKind
  n: number
  metrics: Record<MetricName, Estimate>
  tie_share: number
  parse_failure_rate: number
  calibration: Calibration | null // null for baselines
}

/** Mirrors `backend.report_views.PairedDifference`: per-user AUC, arm − reference. */
export type PairedDifference = { arm: string; reference: string; auc: Estimate }

/** Mirrors `backend.report.Bucket`. */
export type Bucket = 'Twin better' | 'About the same' | 'Plain LLM better'

/** Mirrors `backend.report.Verdict`. */
export type Verdict = 'twins beat plain LLM' | 'no detectable difference' | 'plain LLM better'

/** Mirrors `backend.report_views.BucketUser`. */
export type BucketUser = { user_id: string; d_minus_a: number }

/** Mirrors `backend.report_views.OutcomeBucket`. */
export type OutcomeBucket = { bucket: Bucket; users: BucketUser[] } // largest D − A first

/** Mirrors `backend.report_views.PrimaryOutcome`. */
export type PrimaryOutcome = {
  difference: Estimate
  verdict: Verdict
  buckets: OutcomeBucket[]
  median_user: string
}

/** Mirrors `backend.report_views.ReliabilityBin`. */
export type ReliabilityBin = {
  low: number
  high: number
  n: number
  clicks: number
  mean_p_click: number | null // null for an empty bin
}

/** Mirrors `backend.report_views.Reliability`. */
export type Reliability = { arm: string; bins: ReliabilityBin[] }

/** Mirrors `backend.report_views.NotResultReason`. */
export type NotResultReason = 'mock' | 'dev' | 'synthetic' | 'unfrozen'

/** Mirrors `backend.report_views.RunReport`. */
export type RunReport = {
  run_id: string
  population: string
  data_source: string
  model: string
  mock: boolean
  is_result: boolean
  not_result_reasons: NotResultReason[]
  n_users: number
  arms: ArmReport[] // run order
  differences: PairedDifference[]
  primary: PrimaryOutcome | null // D − A; null unless both arms ran
  reliability: Reliability[] // LLM arms only
  identity_screen: Record<string, Record<string, number>>
}

/** Mirrors `backend.report_views.CandidateOutcome`: the real click label. */
export type CandidateOutcome = Headline & { clicked: boolean }

/** Mirrors `backend.report_views.Prediction`. */
export type Prediction = {
  news_id: string
  rank: number // 1 = top pick
  p_click: number | null // 0-100; null for baselines
  reaction: string | null
}

/** Mirrors `backend.report_views.ArmPredictions`. */
export type ArmPredictions = {
  arm: string
  kind: ArmKind
  auc: number
  predictions: Prediction[] // display order
}

/** Mirrors `backend.report_views.UserPredictions`. Reveals labels: Report only. */
export type UserPredictions = {
  run_id: string
  user_id: string
  mock: boolean
  is_result: boolean
  data_source: string
  d_minus_a: number | null
  bucket: Bucket | null
  candidates: CandidateOutcome[] // display order
  arms: ArmPredictions[]
}

const runUrl = (runId: string) => `/api/run/${encodeURIComponent(runId)}`

export function fetchReport(runId: string): Promise<RunReport> {
  return requestJson<RunReport>(`${runUrl(runId)}/report`)
}

export function fetchPredictions(runId: string, userId: string): Promise<UserPredictions> {
  return requestJson<UserPredictions>(
    `${runUrl(runId)}/user/${encodeURIComponent(userId)}/predictions`,
  )
}
