/** Mirrors `backend.main.Status`. */
export type Status = {
  mock: boolean
  demo_mode: boolean
  model: string
  data_source: string
  call_count: number
}

export async function fetchStatus(): Promise<Status> {
  const response = await fetch('/api/status')
  if (!response.ok) {
    throw new Error(`GET /api/status failed with ${response.status}`)
  }
  return (await response.json()) as Status
}
