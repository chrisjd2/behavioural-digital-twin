import { requestJson } from './client'
import type { RunSummary } from './runs'

/** Mirrors `backend.simulation.CallStarted`. */
export type CallStarted = { seq: number; kind: 'call_started'; user_id: string; arm: string }

/** Mirrors `backend.simulation.Reaction`. `clicked` is the real label, revealed after the card. */
export type Reaction = {
  seq: number
  kind: 'reaction'
  user_id: string
  arm: string
  news_id: string
  headline: string
  reaction: string
  p_click: number
  clicked: boolean
}

/** Mirrors `backend.simulation.ArmProgress`. */
export type ArmProgress = {
  seq: number
  kind: 'arm_progress'
  arm: string
  done: number
  total: number
}

/** Mirrors `backend.simulation.RunComplete`. */
export type RunComplete = { seq: number; kind: 'run_complete'; run_id: string }

/** Mirrors `backend.simulation.EventView`. */
export type RunEvent = CallStarted | Reaction | ArmProgress | RunComplete

/** Mirrors `backend.simulation.RunEvents`. */
export type RunEvents = {
  run: RunSummary
  recorded_seconds: number
  events: RunEvent[] // by seq
  readers: string[] // the run's seeded sampling order (events arrive in completion order)
}

/** Mirrors `backend.simulation.ArmName`. */
export type ArmName = 'A' | 'B' | 'C' | 'D' | 'E' | 'popularity' | 'random'

/** Mirrors `backend.simulation.LiveRunRequest`. Always the dev population. */
export type LiveRunRequest = { arms?: ArmName[]; n_users?: number }

/** Mirrors `backend.simulation.LiveRunStarted`. */
export type LiveRunStarted = { live_id: string }

/** Mirrors `backend.simulation.RunSaved`. */
export type RunSaved = { run_id: string }

/** Mirrors `backend.simulation.RunFailed`. */
export type RunFailed = { detail: string }

/** Every event of a saved run, fetched once: the replay then needs no network (ADR-0008). */
export function fetchRunEvents(runId: string): Promise<RunEvents> {
  return requestJson<RunEvents>(`/api/run/${encodeURIComponent(runId)}/events`)
}

export function startLiveRun(request: LiveRunRequest): Promise<LiveRunStarted> {
  return requestJson<LiveRunStarted>('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export type LiveRunHandlers = {
  onEvent: (event: RunEvent) => void
  onSaved: (saved: RunSaved) => void
  onFailed: (message: string) => void
}

/** Follow a live run's SSE stream until it is saved or fails. Returns a function that stops. */
export function followLiveRun(liveId: string, handlers: LiveRunHandlers): () => void {
  const source = new EventSource(`/api/run/${encodeURIComponent(liveId)}/stream`)
  const parse = <T>(message: MessageEvent<string>) => JSON.parse(message.data) as T
  source.addEventListener('run_event', (m) => handlers.onEvent(parse<RunEvent>(m)))
  source.addEventListener('run_saved', (m) => {
    source.close()
    handlers.onSaved(parse<RunSaved>(m))
  })
  source.addEventListener('run_failed', (m) => {
    source.close()
    handlers.onFailed(parse<RunFailed>(m).detail)
  })
  source.onerror = () => {
    source.close()
    handlers.onFailed('Lost the connection to the live run.')
  }
  return () => source.close()
}
