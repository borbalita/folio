import { env } from '@/lib/env'
import { getAccessToken } from '@/lib/supabase'

const DEFAULT_TIMEOUT_MS = 30_000

export class ApiError extends Error {
  /** HTTP status code; 0 for network/CORS/timeout failures. */
  readonly status: number
  /** True when the request never reached the server (network, CORS, timeout). */
  readonly isNetworkError: boolean
  /** Parsed response body, when the server sent one. */
  readonly body: unknown

  constructor(message: string, status: number, isNetworkError: boolean, body: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.isNetworkError = isNetworkError
    this.body = body
  }
}

interface RequestOptions {
  body?: unknown
  signal?: AbortSignal
  timeoutMs?: number
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const { body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options

  const headers: Record<string, string> = {}
  const token = await getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  const combinedSignal = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal

  let response: Response
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: combinedSignal,
    })
  } catch {
    const message =
      timeoutSignal.aborted
        ? `Request timed out after ${timeoutMs}ms: ${method} ${path}`
        : `Network error: ${method} ${path}`
    throw new ApiError(message, 0, true, null)
  }

  const responseBody: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(
      `API error ${response.status}: ${method} ${path}`,
      response.status,
      false,
      responseBody,
    )
  }

  return responseBody as T
}

export const http = {
  get: <T>(path: string, options?: RequestOptions) => request<T>('GET', path, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('POST', path, { ...options, body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PUT', path, { ...options, body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PATCH', path, { ...options, body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>('DELETE', path, options),
}
