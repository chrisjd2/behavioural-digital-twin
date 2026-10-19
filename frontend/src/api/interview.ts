import { requestJson } from './client'
import type { Headline, IdentityHit } from './runs'

/** Mirrors `backend.interview.InterviewRequest`. The conversation so far lives on the server. */
export type InterviewRequest = {
  run_id: string
  user_id: string
  arm: string
  session_id: string | null // null starts a new conversation
  question: string
}

/** Mirrors `backend.interview.InterviewReply`. */
export type InterviewReply = {
  session_id: string // send it back with the next question
  run_id: string
  user_id: string
  arm: string
  model: string // the run's model, which answered
  text: string
  mock: boolean // a fake reply from the mock LLM
  cited: Headline[] // past clicks the reply cites, in order
  identity_hits: IdentityHit[] // the ADR-0007 identity screen fired on the reply
}

/** Mirrors `backend.interview.RecordedExchange`. */
export type RecordedExchange = {
  question: string
  answer: string
  cited: Headline[]
  identity_hits: IdentityHit[]
}

/** Mirrors `backend.interview.RecordedInterview`. Shown, labelled "recorded", as the fallback. */
export type RecordedInterview = {
  run_id: string
  user_id: string
  arm: string
  model: string
  mock: boolean
  exchanges: RecordedExchange[]
}

/** Throws an `ApiError` on a failed call, a rate limit (429) or an ended conversation. */
export function askAgent(request: InterviewRequest): Promise<InterviewReply> {
  return requestJson<InterviewReply>('/api/interview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function fetchRecordedInterview(): Promise<RecordedInterview> {
  return requestJson<RecordedInterview>('/api/interview/recorded')
}
