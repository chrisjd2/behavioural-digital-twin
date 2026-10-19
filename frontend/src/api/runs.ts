import { requestJson } from './client'
import type { CategoryCount } from './experiment'

/** Mirrors `backend.run_views.RunSummary`. */
export type RunSummary = {
  run_id: string
  created: string
  population: string
  arms: string[]
  model: string
  mock: boolean
  data_source: string
  is_result: boolean
  n_users: number
}

/** Mirrors `backend.run_views.RunProblem`. */
export type RunProblem = {
  run_id: string
  problem: 'unreadable' | 'incompatible'
  detail: string
}

/** Mirrors `backend.run_views.RunList`. */
export type RunList = {
  runs: RunSummary[] // newest first
  problems: RunProblem[]
}

/** Mirrors `backend.run_views.CategoryLink`. */
export type CategoryLink = { category: string; clicks: number }

/** Mirrors `backend.run_views.AgentNode`. */
export type AgentNode = {
  user_id: string
  n_history: number
  categories: CategoryLink[] // most-clicked first
}

/** Mirrors `backend.run_views.RunPopulation`. */
export type RunPopulation = {
  run_id: string
  population: string
  data_source: string
  mock: boolean
  is_result: boolean
  agents: AgentNode[]
  categories: CategoryCount[]
}

/** Mirrors `backend.run_views.Headline`. `null` fields: the item is not in the run's news.tsv. */
export type Headline = {
  news_id: string
  category: string | null
  subcategory: string | null
  title: string | null
}

/** Mirrors `backend.run_views.Persona`. */
export type Persona = {
  name: string
  life_stage: string
  age: number
  job: string
  location: string
  big_five: Record<string, string>
  values: string[]
  news_habit: string
}

/** Mirrors `backend.run_views.MemoryView`. */
export type Memory = {
  news_id: string
  headline: string
  category: string
  reason: string
}

/** Mirrors `backend.run_views.IdentityHit`. */
export type IdentityHit = { kind: string; term: string; text: string }

/** Mirrors `backend.run_views.ProfileView` (with `ProfileField` and `ProfileItem`). */
export type Profile = {
  ok: boolean
  fields: { field: string; items: { text: string; evidence: Headline[] }[] }[]
  identity_hits: IdentityHit[]
  dropped_items: number
  word_count: number
}

/** Mirrors `backend.run_views.WrongTwin`. */
export type WrongTwin = { control: true; donor: string; shared_history: number | null }

/** Mirrors `backend.run_views.ArmKnowledge`: KnowsNothing | KnowsPersona | KnowsMemories | KnowsProfile. */
export type ArmKnowledge =
  | { arm: string; kind: 'nothing' }
  | { arm: string; kind: 'persona'; invented: true; persona: Persona }
  | { arm: string; kind: 'memories'; memories: Memory[] }
  | {
      arm: string
      kind: 'profile'
      profile: Profile
      memories: Memory[]
      wrong_twin: WrongTwin | null
    }

/** Mirrors `backend.run_views.AgentDetail`. No labels: the reveal belongs to Simulation and Report. */
export type AgentDetail = {
  run_id: string
  user_id: string
  mock: boolean
  data_source: string
  history: Headline[] // oldest first
  candidates: Headline[] // display order
  arms: ArmKnowledge[]
}

export function fetchRuns(): Promise<RunList> {
  return requestJson<RunList>('/api/runs')
}

export function fetchRun(runId: string): Promise<RunSummary> {
  return requestJson<RunSummary>(`/api/run/${encodeURIComponent(runId)}`)
}

export function fetchPopulation(runId: string): Promise<RunPopulation> {
  return requestJson<RunPopulation>(`/api/run/${encodeURIComponent(runId)}/population`)
}

export function fetchAgent(runId: string, userId: string): Promise<AgentDetail> {
  return requestJson<AgentDetail>(
    `/api/run/${encodeURIComponent(runId)}/agent/${encodeURIComponent(userId)}`,
  )
}

/** What a run may be read as (ADR-0001): only a frozen test run on real data is a result. */
export function runKind(run: RunSummary): 'Result' | 'MOCK' | 'Unfrozen test' | 'Dev' {
  if (run.is_result) return 'Result'
  if (run.mock) return 'MOCK'
  return run.population === 'test' ? 'Unfrozen test' : 'Dev'
}

/** Steps 2-4 open on the newest result run, otherwise the newest run (PRD-03). */
export function defaultRunId(runs: RunSummary[]): string | undefined {
  return (runs.find((r) => r.is_result) ?? runs[0])?.run_id
}
