import { requestJson } from './client'
import type { Headline } from './runs'

/** Mirrors `backend.interview.Turn`. */
export type Turn = { role: 'interviewer' | 'agent'; text: string }

/** Mirrors `backend.interview.InterviewRequest`. */
export type InterviewRequest = {
  run_id: string
  user_id: string
  arm: string
  messages: Turn[] // oldest first, ending with the interviewer's question
}

/** Mirrors `backend.interview.InterviewReply`. */
export type InterviewReply = {
  run_id: string
  user_id: string
  arm: string
  text: string
  mock: boolean // a fake reply from the mock LLM
  cited: Headline[] // past clicks the reply cites, in order
}

/** Mirrors `backend.interview.RecordedExchange`. */
export type RecordedExchange = { question: string; answer: string; cited: Headline[] }

/** Mirrors `backend.interview.RecordedInterview`. Shown, labelled "recorded", as the fallback. */
export type RecordedInterview = {
  run_id: string
  user_id: string
  arm: string
  model: string
  mock: boolean
  exchanges: RecordedExchange[]
}

/** Throws with the backend's detail on a failed call or a rate limit (429). */
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
