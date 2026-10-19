import { requestJson } from './client'
import type { Headline } from './runs'

/** Mirrors `backend.hook.HookCall`. */
export type HookCall = { news_id: string; p_click: number; reaction: string }

/** Mirrors `backend.hook.HookPrediction`. */
export type HookPrediction = { arm: string; calls: HookCall[] } // calls in headline order

/** Mirrors `backend.hook.HookReveal`. */
export type HookReveal = { clicked_id: string; predictions: HookPrediction[] } // A, then D

/** Mirrors `backend.hook.HookExample`. The answer is only under `reveal`. */
export type HookExample = {
  run_id: string
  user_id: string
  mock: boolean
  data_source: string
  headlines: Headline[] // the pair, in the run's display order
  history: Headline[] // most recent past clicks, oldest first
  reveal: HookReveal
}

export function fetchHook(): Promise<HookExample> {
  return requestJson<HookExample>('/api/hook')
}
