import { requestJson } from './client'
import type { DataSource } from './status'

/** Mirrors `backend.main.ExperimentRequest`. */
export type ExperimentRequest = {
  n_users: number
  seed: number
  max_candidates: number
}

/** Mirrors `backend.run_views.CategoryCount`. */
export type CategoryCount = {
  category: string
  users: number
}

/** Mirrors `backend.main.PopulationSummary`. */
export type PopulationSummary = {
  population: 'dev'
  data_source: DataSource
  n_users: number
  seed: number
  max_candidates: number
  user_ids: string[]
  eligible_users: number
  n_candidates: number
  categories: CategoryCount[]
  mean_feed_ctr: number
  mean_sample_ctr: number
}

export function buildPopulation(request: ExperimentRequest): Promise<PopulationSummary> {
  return requestJson<PopulationSummary>('/api/experiment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}
