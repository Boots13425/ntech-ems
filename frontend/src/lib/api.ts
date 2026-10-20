export class ApiError extends Error {
  constructor(public status: number, message: string, public errors?: { field: string; message: string }[]) { super(message) }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const csrf = document.cookie.split('; ').find(c => c.startsWith('ntech_csrf='))?.split('=')[1]
  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...options, credentials: 'include', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}), ...options.headers } })
  } catch { throw new ApiError(0, 'Unable to reach the server. Check your connection and try again.') }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    if (response.status === 401 && !['/auth/login', '/auth/me'].includes(path)) window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(response.status, typeof body.detail === 'string' ? body.detail : 'The request could not be completed.', body.errors)
  }
  return response.status === 204 ? undefined as T : response.json()
}
export const send = <T>(path: string, body?: unknown, method = 'POST') => api<T>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
