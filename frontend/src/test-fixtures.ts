import { vi } from 'vitest'
import type { PopulationSummary } from './api/experiment'
import type { Status } from './api/status'

export const statusFixture: Status = {
  mock: false,
  demo_mode: false,
  model: 'gemini-test-001',
  data_source: 'mind',
  call_count: 0,
  experiment_defaults: { n_users: 30, seed: 20261019, max_candidates: 8 },
}

export const populationFixture: PopulationSummary = {
  population: 'dev',
  data_source: 'mind',
  n_users: 30,
  seed: 20261019,
  max_candidates: 8,
  user_ids: ['U1', 'U2'],
  eligible_users: 41236,
  n_candidates: 236,
  categories: [
    { category: 'news', users: 27 },
    { category: 'sports', users: 19 },
    { category: 'finance', users: 11 },
  ],
  mean_feed_ctr: 0.0412,
  mean_sample_ctr: 0.2311,
}

type ErrorReply = { errorStatus: number; body: object }
export type Reply = object | number | ErrorReply

/**
 * Stub `fetch` per endpoint: an object is a 200 JSON body, a number an `AppError` with that
 * status, `{errorStatus, body}` an exact error reply.
 */
export function stubApi(routes: { status: Reply; experiment?: Reply }) {
  const fetchMock = vi.fn(async (url: string) => {
    const reply = url === '/api/status' ? routes.status : routes.experiment
    if (reply === undefined) throw new Error(`unexpected fetch ${url}`)
    if (typeof reply === 'number') {
      return new Response(JSON.stringify({ code: 'boom', detail: `Server said ${reply}` }), {
        status: reply,
      })
    }
    if ('errorStatus' in reply) {
      const { errorStatus, body } = reply as ErrorReply
      return new Response(JSON.stringify(body), { status: errorStatus })
    }
    return new Response(JSON.stringify(reply), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
