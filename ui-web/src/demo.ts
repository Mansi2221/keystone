/**
 * Demo mode: serves pre-recorded fixture data when no backend is available.
 * Activated by ?mode=demo in the URL, or automatically when /api is unreachable.
 */

import type { DemoUser, Principal, SSEEvent } from './types'

// Fixture scenario keywords -> fixture file prefix mapping
const SCENARIO_MATCHERS: Array<{ keywords: string[]; prefix: string }> = [
  { keywords: ['my salary', 'what is my salary', 'my compensation'], prefix: 'salary_own' },
  { keywords: ['salary for employee', 'salary for emp', "show me the salary", "employee 44"], prefix: 'salary_other' },
  { keywords: ['org chart', 'organization', 'who reports', 'team structure'], prefix: 'org_chart' },
  { keywords: ['ticket', 'p1', 'open ticket', 'incident'], prefix: 'ticket_search' },
  { keywords: ['deal', 'renewing', 'pipeline', 'crm', 'sales'], prefix: 'deal_search' },
  { keywords: ['message', 'chat', 'channel', '#ops', 'slack'], prefix: 'chat_search' },
  { keywords: ['complaint', 'hr complaint', 'harassment', 'investigation'], prefix: 'hr_complaint' },
]

// Persona key -> fixture suffix mapping
const PERSONA_MAP: Record<string, string> = {
  ceo: 'ceo',
  hr_partner: 'hr_partner',
  ops_manager: 'ceo',
  engineer: 'engineer',
  contractor: 'contractor',
  sales_rep: 'ceo',
  finance_director: 'ceo',
}

const DEMO_USERS: DemoUser[] = [
  {
    key: 'ceo',
    employee_id: 1,
    role: 'executive',
    department: 'Operations',
    name: 'Danielle Johnson',
    title: 'Chief Executive Officer',
    description: 'Full access to all systems',
    groups: ['leadership', 'all-employees'],
  },
  {
    key: 'hr_partner',
    employee_id: 5,
    role: 'hr',
    department: 'Human Resources',
    name: 'John Wheeler',
    title: 'HR Business Partner',
    description: 'HR data access, salary visibility',
    groups: ['hr-team', 'all-employees'],
  },
  {
    key: 'ops_manager',
    employee_id: 9,
    role: 'manager',
    department: 'Operations',
    name: 'Jose Richards',
    title: 'Operations Manager',
    description: 'Manages ops team, sees direct reports',
    groups: ['operations', 'all-employees'],
  },
  {
    key: 'engineer',
    employee_id: 12,
    role: 'ic',
    department: 'Engineering',
    name: 'Marcus Thompson',
    title: 'Senior Software Engineer',
    description: 'Engineering team, own data only',
    groups: ['engineering', 'all-employees'],
  },
  {
    key: 'contractor',
    employee_id: 61,
    role: 'contractor',
    department: 'Operations',
    name: 'Michelle Rasmussen',
    title: 'External Contractor',
    description: 'Limited access, no HR or salary',
    groups: ['contractors'],
  },
]

const PRINCIPALS: Record<string, Principal> = {
  ceo: {
    user_id: 1,
    employee_id: '1',
    role: 'executive',
    department: 'Operations',
    groups: ['leadership', 'all-employees'],
    manager_id: null,
    report_count: 8,
    name: 'Danielle Johnson',
    title: 'Chief Executive Officer',
  },
  hr_partner: {
    user_id: 5,
    employee_id: '5',
    role: 'hr',
    department: 'Human Resources',
    groups: ['hr-team', 'all-employees'],
    manager_id: 1,
    report_count: 3,
    name: 'John Wheeler',
    title: 'HR Business Partner',
  },
  ops_manager: {
    user_id: 9,
    employee_id: '9',
    role: 'manager',
    department: 'Operations',
    groups: ['operations', 'all-employees'],
    manager_id: 1,
    report_count: 5,
    name: 'Jose Richards',
    title: 'Operations Manager',
  },
  engineer: {
    user_id: 12,
    employee_id: '12',
    role: 'ic',
    department: 'Engineering',
    groups: ['engineering', 'all-employees'],
    manager_id: 8,
    report_count: 0,
    name: 'Marcus Thompson',
    title: 'Senior Software Engineer',
  },
  contractor: {
    user_id: 61,
    employee_id: '61',
    role: 'contractor',
    department: 'Operations',
    groups: ['contractors'],
    manager_id: 9,
    report_count: 0,
    name: 'Michelle Rasmussen',
    title: 'External Contractor',
  },
}

const _fixtureCache: Record<string, unknown> = {}

async function loadFixture(name: string): Promise<{ events: SSEEvent[] } | null> {
  if (_fixtureCache[name]) return _fixtureCache[name] as { events: SSEEvent[] }
  try {
    const res = await fetch(`/fixtures/${name}.json`)
    if (!res.ok) return null
    const data = await res.json()
    _fixtureCache[name] = data
    return data
  } catch {
    return null
  }
}

function matchScenario(message: string): string {
  const lower = message.toLowerCase()
  for (const matcher of SCENARIO_MATCHERS) {
    if (matcher.keywords.some((kw) => lower.includes(kw))) {
      return matcher.prefix
    }
  }
  return 'salary_own'
}

function getPersonaSuffix(userKey: string): string {
  return PERSONA_MAP[userKey] || 'ceo'
}

// --- Public demo API ---

export function isDemoMode(): boolean {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  if (params.get('mode') === 'demo') return true
  // Auto-detect: if hosted on vercel.app, always use demo mode (no backend)
  if (window.location.hostname.includes('vercel.app')) return true
  return false
}

let _autoDetected: boolean | null = null

export async function shouldUseDemoMode(): Promise<boolean> {
  if (isDemoMode()) return true
  if (_autoDetected !== null) return _autoDetected
  try {
    const res = await fetch('/api/auth/demo-users', { signal: AbortSignal.timeout(1500) })
    _autoDetected = !res.ok
  } catch {
    _autoDetected = true
  }
  return _autoDetected
}

export function demoDemoUsers(): DemoUser[] {
  return DEMO_USERS
}

export function demoLogin(userKey: string): { token: string; employee_id: number; role: string; name: string } {
  const user = DEMO_USERS.find((u) => u.key === userKey) || DEMO_USERS[0]
  return {
    token: `demo-token-${userKey}`,
    employee_id: user.employee_id,
    role: user.role,
    name: user.name,
  }
}

export function demoFetchMe(userKey: string): Principal {
  return PRINCIPALS[userKey] || PRINCIPALS.ceo
}

export async function demoStreamChat(
  userKey: string,
  message: string,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const scenario = matchScenario(message)
  const suffix = getPersonaSuffix(userKey)
  const fixtureName = `${scenario}_${suffix}`

  const fixture = await loadFixture(fixtureName)
  if (!fixture || !fixture.events) {
    onEvent({ type: 'response', text: `[Demo mode] No fixture for "${message}" as ${userKey}. Try: "What is my salary?" or "Show me the salary for employee 44"` })
    onEvent({ type: 'done', trace_id: 'demo-trace' })
    return
  }

  for (const event of fixture.events) {
    const delay = event.type === 'tool_start' ? 300 : event.type === 'tool_result' ? 800 : event.type === 'response' ? 500 : 100
    await new Promise((r) => setTimeout(r, delay))
    onEvent(event as SSEEvent)
  }
}

export function demoUserKeyFromToken(token: string): string {
  if (typeof token === 'string' && token.startsWith('demo-token-')) {
    return token.replace('demo-token-', '')
  }
  return 'ceo'
}
