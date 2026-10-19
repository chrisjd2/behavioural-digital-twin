/** A non-2xx reply: the backend's detail as the message, and its `code` when it sent one. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | undefined

  constructor(message: string, status: number, code: string | undefined) {
    super(message)
    this.status = status
    this.code = code
  }
}

/** Fetch JSON; a non-2xx reply throws an `ApiError` with the backend's detail when there is one. */
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const code = (body as { code?: unknown } | null)?.code
    throw new ApiError(
      errorDetail(body) ?? `${url} failed with ${response.status}`,
      response.status,
      typeof code === 'string' ? code : undefined,
    )
  }
  return (await response.json()) as T
}

/** `AppError` sends a string detail; FastAPI validation sends a list of `{loc, msg}`. */
function errorDetail(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null) return undefined
  const { detail } = body as Record<string, unknown>
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return undefined
  const messages = detail.map((item: unknown) => {
    const { loc, msg } = (item ?? {}) as Record<string, unknown>
    const field = Array.isArray(loc) ? loc.at(-1) : undefined
    return field ? `${String(field)}: ${String(msg)}` : String(msg)
  })
  return messages.length ? messages.join('; ') : undefined
}
