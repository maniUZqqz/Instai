import { currentLang, translate } from '../i18n'

/** Error from the API (`{"error": {"code", "message", "details"}}`) or from the network (`code: 'network'`). */
export class ApiError extends Error {
  code: string
  status: number
  details: unknown
  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message)
    this.code = code
    this.status = status
    this.details = details
  }
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch('/api' + path, {
      method,
      headers: { 'X-Lang': currentLang(), ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') throw e
    throw new ApiError('network', translate('error.network'), 0)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error
    throw new ApiError(err?.code ?? 'error', err?.message ?? translate('error.generic'), res.status, err?.details)
  }
  return data as T
}

export const api = {
  get: <T,>(path: string, signal?: AbortSignal) => request<T>('GET', path, undefined, signal),
  post: <T,>(path: string, body: unknown = {}) => request<T>('POST', path, body),
  put: <T,>(path: string, body: unknown = {}) => request<T>('PUT', path, body),
  patch: <T,>(path: string, body: unknown = {}) => request<T>('PATCH', path, body),
  del: <T = void,>(path: string) => request<T>('DELETE', path),
}

/** Field names from a validation error, e.g. "name, handle" (the server text for each field is English, so only names are shown). */
export function detailFields(err: unknown): string {
  if (!(err instanceof ApiError) || !err.details || typeof err.details !== 'object') return ''
  const keys = Object.keys(err.details as object)
  return keys.length ? keys.join('، ') : ''
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const f = e.code === 'validation_error' ? detailFields(e) : ''
    return f ? `${e.message} (${f})` : e.message
  }
  return translate('error.generic')
}
