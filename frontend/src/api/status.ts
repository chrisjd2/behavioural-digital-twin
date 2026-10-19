import { requestJson } from './client'
import type { ExperimentRequest } from './experiment'

/** Mirrors `backend.data.DataKind`. */
export type DataSource = 'mind' | 'synthetic' | 'none'

/** Mirrors `backend.main.Status`. */
export type Status = {
  mock: boolean
  demo_mode: boolean
  model: string
  data_source: DataSource
  call_count: number
  experiment_defaults: ExperimentRequest
}

export function fetchStatus(): Promise<Status> {
  return requestJson<Status>('/api/status')
}
