import { vi } from 'vitest'
import type { PopulationSummary } from './api/experiment'
import type { AgentDetail, Headline, Profile, RunPopulation, RunSummary } from './api/runs'
import type { RunEvent, RunEvents } from './api/simulation'
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

export const runFixture: RunSummary = {
  run_id: '20261019-142703-dev-701c06',
  created: '2026-10-19T14:27:03+00:00',
  population: 'dev',
  arms: ['A', 'B', 'C', 'D', 'E', 'random'],
  model: 'gemini-test-001',
  mock: false,
  data_source: 'mind',
  is_result: false,
  n_users: 2,
}

export const runPopulationFixture: RunPopulation = {
  run_id: runFixture.run_id,
  population: 'dev',
  data_source: 'mind',
  mock: false,
  is_result: false,
  agents: [
    {
      user_id: 'U1',
      n_history: 4,
      categories: [
        { category: 'health', clicks: 3 },
        { category: 'news', clicks: 1 },
      ],
    },
    {
      user_id: 'U2',
      n_history: 2,
      categories: [{ category: 'sports', clicks: 2 }],
    },
  ],
  categories: [
    { category: 'health', users: 1 },
    { category: 'news', users: 1 },
    { category: 'sports', users: 1 },
  ],
}

const headline = (news_id: string, title: string, category = 'health'): Headline => ({
  news_id,
  category,
  subcategory: 'fitness',
  title,
})

const memory = { news_id: 'N1', headline: 'The workout that may help you live longer' }
const profile: Profile = {
  ok: true,
  fields: [
    {
      field: 'interests',
      items: [
        {
          text: 'Fitness routines and preventative health advice.',
          evidence: [headline('N1', 'The workout that may help you live longer')],
        },
      ],
    },
  ],
  identity_hits: [],
  dropped_items: 0,
  word_count: 6,
}

export const agentFixture: AgentDetail = {
  run_id: runFixture.run_id,
  user_id: 'U1',
  mock: false,
  data_source: 'mind',
  history: [
    headline('N1', 'The workout that may help you live longer'),
    headline('N2', 'Election Day 2019: races to watch', 'news'),
  ],
  candidates: [headline('N9', 'How to get a six-pack in 30 days')],
  arms: [
    { arm: 'A', kind: 'nothing' },
    {
      arm: 'B',
      kind: 'persona',
      invented: true,
      persona: {
        name: 'Tom Kim',
        life_stage: 'late career',
        age: 63,
        job: 'insurance agent',
        location: 'Omaha, Nebraska',
        big_five: { openness: 'medium', agreeableness: 'high' },
        values: ['security', 'conformity'],
        news_habit: 'You check the news at lunch and again in the evening.',
      },
    },
    {
      arm: 'C',
      kind: 'memories',
      memories: [
        { ...memory, category: 'health/fitness', reason: 'similar to: How to get a six-pack' },
        { news_id: 'N2', headline: 'Election Day 2019', category: 'news', reason: 'recent' },
      ],
    },
    {
      arm: 'D',
      kind: 'profile',
      profile,
      memories: [{ ...memory, category: 'health/fitness', reason: 'recent' }],
      wrong_twin: null,
    },
    {
      arm: 'E',
      kind: 'profile',
      profile: {
        ...profile,
        fields: [
          {
            field: 'interests',
            items: [
              {
                text: 'Celebrity news and TV personalities.',
                evidence: [headline('N7', 'Star leaves the show', 'tv')],
              },
            ],
          },
        ],
      },
      memories: [
        { news_id: 'N7', headline: 'Star leaves the show', category: 'tv', reason: 'recent' },
      ],
      wrong_twin: { control: true, donor: 'U2', shared_history: 0 },
    },
  ],
}

const REPLAY_HEADLINES: [string, string, boolean][] = [
  ['N9', 'How to get a six-pack in 30 days', true],
  ['N10', 'Stocks slip as investors wait on the Fed', false],
]

/** A recorded run in the runner's order: arms one after another, two readers each. */
export const replayEvents: RunEvent[] = (() => {
  const events: RunEvent[] = []
  const seq = () => events.length
  for (const arm of ['A', 'B']) {
    for (const [done, user_id] of ['U1', 'U2'].entries()) {
      events.push({ seq: seq(), kind: 'call_started', user_id, arm })
      for (const [news_id, headline, clicked] of REPLAY_HEADLINES) {
        events.push({
          seq: seq(),
          kind: 'reaction',
          user_id,
          arm,
          news_id,
          headline,
          reaction: `${arm} ${user_id}: I would ${clicked ? 'definitely' : 'never'} read this.`,
          p_click: clicked ? 70 : 20,
          clicked,
        })
      }
      events.push({ seq: seq(), kind: 'arm_progress', arm, done: done + 1, total: 2 })
    }
  }
  events.push({ seq: seq(), kind: 'arm_progress', arm: 'random', done: 2, total: 2 })
  events.push({ seq: seq(), kind: 'run_complete', run_id: runFixture.run_id })
  return events
})()

export const runEventsFixture: RunEvents = {
  run: { ...runFixture, arms: ['A', 'B', 'random'] },
  recorded_seconds: 894,
  events: replayEvents,
}

type ErrorReply = { errorStatus: number; body: object }
export type Reply = object | number | ErrorReply

/**
 * Stub `fetch` per endpoint: an object is a 200 JSON body, a number an `AppError` with that
 * status, `{errorStatus, body}` an exact error reply. `urls` holds any other endpoint by URL.
 */
export function stubApi(routes: {
  status: Reply
  experiment?: Reply
  runs?: Reply
  urls?: Record<string, Reply>
}) {
  const named: Record<string, Reply | undefined> = {
    '/api/status': routes.status,
    '/api/experiment': routes.experiment,
    '/api/runs': routes.runs,
  }
  const fetchMock = vi.fn(async (url: string) => {
    const reply = named[url] ?? routes.urls?.[url]
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
