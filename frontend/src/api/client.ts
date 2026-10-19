/** Fetch JSON; a non-2xx reply throws with the backend `AppError` detail when there is one. */
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    throw new Error(appErrorDetail(body) ?? `${url} failed with ${response.status}`)
  }
  return (await response.json()) as T
}

function appErrorDetail(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null) return undefined
  const { detail } = body as Record<string, unknown>
  return typeof detail === 'string' ? detail : undefined
}
