import type { AuditEntry, DemoUser, Principal, SSEEvent } from './types'
import { shouldUseDemoMode, demoDemoUsers, demoLogin, demoFetchMe, demoStreamChat, demoUserKeyFromToken } from './demo'

const BASE = '/api'

// ─── Token management ───────────────────────────────────────────────────────

let _currentUserKey: string | null = null
let _token: string | null = null
let _tokenExpiry: number = 0 // epoch ms
let _refreshTimer: ReturnType<typeof setTimeout> | null = null

/** Listeners notified when re-login produces a new token. */
const tokenListeners: Array<(token: string) => void> = []

export function onTokenRefresh(cb: (token: string) => void) {
  tokenListeners.push(cb)
  return () => {
    const i = tokenListeners.indexOf(cb)
    if (i >= 0) tokenListeners.splice(i, 1)
  }
}

function notifyTokenRefresh(token: string) {
  for (const cb of tokenListeners) cb(token)
}

function scheduleTokenRefresh() {
  if (_refreshTimer) clearTimeout(_refreshTimer)
  const msUntilExpiry = _tokenExpiry - Date.now()
  // Refresh 2 minutes before expiry (or immediately if < 2 min left)
  const refreshIn = Math.max(msUntilExpiry - 120_000, 5_000)
  _refreshTimer = setTimeout(async () => {
    if (!_currentUserKey) return
    try {
      const result = await _rawLogin(_currentUserKey)
      _token = result.token
      _tokenExpiry = Date.now() + 55 * 60_000 // assume ~60 min, refresh at 55
      localStorage.setItem('keystone-token', result.token)
      notifyTokenRefresh(result.token)
      scheduleTokenRefresh()
    } catch {
      // login failed — will catch on next request via 401 retry
    }
  }, refreshIn)
}

export function setAuthState(userKey: string, token: string) {
  _currentUserKey = userKey
  _token = token
  _tokenExpiry = Date.now() + 55 * 60_000
  scheduleTokenRefresh()
}

export function clearAuthState() {
  _currentUserKey = null
  _token = null
  _tokenExpiry = 0
  if (_refreshTimer) clearTimeout(_refreshTimer)
}

export function getToken() { return _token }
export function getTokenExpiry() { return _tokenExpiry }

// ─── Raw API calls ──────────────────────────────────────────────────────────

async function _rawLogin(username: string): Promise<{ token: string; employee_id: number; role: string; name: string }> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
  if (!res.ok) throw new Error(`Login failed: ${res.statusText}`)
  return res.json()
}

/** Re-login the current user and retry a failed request. Returns new token or throws. */
async function reloginAndRetry(): Promise<string> {
  if (!_currentUserKey) throw new Error('Session expired. Please select a user to continue.')
  const result = await _rawLogin(_currentUserKey)
  _token = result.token
  _tokenExpiry = Date.now() + 55 * 60_000
  localStorage.setItem('keystone-token', result.token)
  notifyTokenRefresh(result.token)
  scheduleTokenRefresh()
  return result.token
}

/** Fetch wrapper that retries once on 401. Never exposes raw HTTP errors. */
async function authedFetch(url: string, init: RequestInit & { _retried?: boolean } = {}): Promise<Response> {
  const token = _token
  if (!token) throw new Error('Please log in to continue.')

  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(url, { ...init, headers })

  if (res.status === 401 && !init._retried) {
    // Token expired — re-login and retry once
    const newToken = await reloginAndRetry()
    headers.set('Authorization', `Bearer ${newToken}`)
    return fetch(url, { ...init, headers, _retried: true } as RequestInit)
  }

  return res
}

/** Convert a failed response to a friendly error message. */
function friendlyError(res: Response, context: string): Error {
  if (res.status === 401) return new Error('Session expired. Please select a user to continue.')
  if (res.status === 403) return new Error('You don\'t have permission for this action.')
  if (res.status >= 500) return new Error('Something went wrong on the server. Try again in a moment.')
  return new Error(`${context} failed. Please try again.`)
}

// ─── Public API ─────────────────────────────────────────────────────────────

export async function login(username: string): Promise<{ token: string; employee_id: number; role: string; name: string }> {
  if (await shouldUseDemoMode()) {
    const result = demoLogin(username)
    setAuthState(username, result.token)
    return result
  }
  const result = await _rawLogin(username)
  setAuthState(username, result.token)
  return result
}

export async function fetchMe(token: string): Promise<Principal> {
  if (await shouldUseDemoMode()) {
    return demoFetchMe(demoUserKeyFromToken(token))
  }
  const res = await authedFetch(`${BASE}/auth/me`)
  if (!res.ok) throw friendlyError(res, 'Loading profile')
  return res.json()
}

export async function fetchDemoUsers(): Promise<DemoUser[]> {
  if (await shouldUseDemoMode()) {
    return demoDemoUsers()
  }
  const res = await fetch(`${BASE}/auth/demo-users`)
  if (!res.ok) throw friendlyError(res, 'Loading users')
  return res.json()
}

export async function streamChat(
  token: string,
  message: string,
  conversationId: string,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  if (await shouldUseDemoMode()) {
    const userKey = demoUserKeyFromToken(token)
    await demoStreamChat(userKey, message, onEvent)
    return
  }
  // Use the explicitly-passed token (important for compare mode with per-user tokens)
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
  const body = JSON.stringify({ message, conversation_id: conversationId })

  let res = await fetch(`${BASE}/chat/stream`, { method: 'POST', headers, body })

  // Retry once on 401 (only if this is the main user's token, not compare mode)
  if (res.status === 401 && token === _token) {
    const newToken = await reloginAndRetry()
    headers.Authorization = `Bearer ${newToken}`
    res = await fetch(`${BASE}/chat/stream`, { method: 'POST', headers, body })
  }

  if (!res.ok) throw friendlyError(res, 'Sending message')

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data: ')) {
        try {
          const data = JSON.parse(trimmed.slice(6))
          onEvent(data)
        } catch {
          // skip malformed events
        }
      }
    }
  }

  if (buffer.trim().startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.trim().slice(6))
      onEvent(data)
    } catch {
      // skip
    }
  }
}

export async function chatSync(
  token: string,
  message: string,
  conversationId?: string,
): Promise<{ reply: string; sources: { type: string; id: string; title: string }[]; trace_id?: string }> {
  const res = await authedFetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  })
  if (!res.ok) throw friendlyError(res, 'Sending message')
  return res.json()
}

export async function fetchAudit(token: string, limit = 50): Promise<AuditEntry[]> {
  const res = await authedFetch(`${BASE}/audit?limit=${limit}`)
  if (!res.ok) return []
  return res.json()
}

export async function fetchTrace(token: string, traceId: string): Promise<unknown> {
  const res = await authedFetch(`${BASE}/trace/${traceId}`)
  if (!res.ok) throw friendlyError(res, 'Loading trace')
  return res.json()
}

export async function fetchApprovals(token: string): Promise<unknown[]> {
  const res = await authedFetch(`${BASE}/approvals`)
  if (!res.ok) return []
  return res.json()
}

export async function submitApproval(token: string, approvalId: string, approved: boolean): Promise<void> {
  await authedFetch(`${BASE}/approvals/${approvalId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved }),
  })
}
