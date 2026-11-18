/**
 * Playwright UI tests with mocked API — no live backend or LLM required.
 *
 * Run: cd ui-web && npx playwright test
 */
import { test, expect, type Page, type Route } from '@playwright/test'

// ─── Mock data ──────────────────────────────────────────────────────────────

const DEMO_USERS = [
  { key: 'ceo', employee_id: 1, role: 'executive', department: 'Operations', name: 'Danielle Johnson', title: 'CEO', description: 'CEO', groups: ['leadership', 'board_access'] },
  { key: 'vp_sales', employee_id: 2, role: 'executive', department: 'Sales', name: 'Jeffrey Doyle', title: 'VP of Sales', description: 'VP of Sales', groups: ['sales', 'leadership'] },
  { key: 'sales_manager', employee_id: 7, role: 'manager', department: 'Sales', name: 'Lisa Smith', title: 'Sales Manager', description: 'Sales Manager', groups: ['sales', 'leadership'] },
  { key: 'ops_manager', employee_id: 28, role: 'manager', department: 'Operations', name: 'Jose Richards', title: 'Operations Manager', description: 'Operations Manager', groups: ['operations', 'leadership'] },
  { key: 'contractor', employee_id: 116, role: 'contractor', department: 'Engineering', name: 'Michelle Rasmussen', title: 'Contract Developer', description: 'Contract Developer', groups: [] },
  { key: 'hr_partner', employee_id: 80, role: 'hr_partner', department: 'HR', name: 'John Wheeler', title: 'HR Business Partner', description: 'HR Business Partner', groups: ['hr', 'hr_full_access'] },
]

const PRINCIPALS: Record<string, object> = {
  ceo: { user_id: 1, employee_id: 'MF-0001', role: 'executive', department: 'Operations', groups: ['leadership', 'board_access'], manager_id: null, report_count: 5, name: 'Danielle Johnson', title: 'CEO' },
  sales_manager: { user_id: 7, employee_id: 'MF-0007', role: 'manager', department: 'Sales', groups: ['sales', 'leadership'], manager_id: 2, report_count: 3, name: 'Lisa Smith', title: 'Sales Manager' },
  contractor: { user_id: 116, employee_id: 'MF-0116', role: 'contractor', department: 'Engineering', groups: [], manager_id: 92, report_count: 0, name: 'Michelle Rasmussen', title: 'Contract Developer' },
  ops_manager: { user_id: 28, employee_id: 'MF-0028', role: 'manager', department: 'Operations', groups: ['operations', 'leadership'], manager_id: 3, report_count: 4, name: 'Jose Richards', title: 'Operations Manager' },
}

function ssePayload(events: object[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')
}

// Standard successful chat response (CEO asking salary)
const CEO_SALARY_SSE = ssePayload([
  { type: 'node', node: 'planner' },
  { type: 'tool_start', tool: 'hr_get_salary', arguments: { employee_id: 1 } },
  { type: 'tool_result', tool: 'hr_get_salary', success: true, data: { salary: 383812 } },
  { type: 'sources', sources: [{ type: 'hr', id: 'SAL-001', title: 'Salary Record' }] },
  { type: 'response', text: 'Your current salary is $383,812.00 USD.' },
  { type: 'done', trace_id: 'tr-abc12345-mock' },
])

// Manager salary query
const MANAGER_SALARY_SSE = ssePayload([
  { type: 'node', node: 'planner' },
  { type: 'tool_start', tool: 'hr_get_team_salaries', arguments: { manager_id: 7 } },
  { type: 'tool_result', tool: 'hr_get_team_salaries', success: true, data: { reports: 3 } },
  { type: 'sources', sources: [{ type: 'hr', id: 'SAL-007', title: 'Team Salaries' }] },
  { type: 'response', text: 'Here are the salaries of your 3 direct reports:\n- Rep A: $95,000\n- Rep B: $88,000\n- Rep C: $102,000' },
  { type: 'done', trace_id: 'tr-mgr-mock' },
])

// Contractor blocked response (aggregation trap)
const CONTRACTOR_BLOCKED_SSE = ssePayload([
  { type: 'node', node: 'planner' },
  { type: 'tool_start', tool: 'hr_salary_aggregate', arguments: { department: 'Engineering' } },
  { type: 'tool_result', tool: 'hr_salary_aggregate', success: false, data: null },
  { type: 'blocked', reason: 'Access denied: contractors cannot view salary aggregations.' },
  { type: 'done', trace_id: 'tr-block-mock' },
])

// Compare mode responses per role
const COMPARE_RESPONSES: Record<string, string> = {
  contractor: ssePayload([
    { type: 'tool_start', tool: 'docs_search', arguments: { query: 'Halcyon' } },
    { type: 'tool_result', tool: 'docs_search', success: false },
    { type: 'blocked', reason: 'Access denied: board minutes require executive clearance.' },
    { type: 'done', trace_id: 'tr-cmp-con' },
  ]),
  ops_manager: ssePayload([
    { type: 'tool_start', tool: 'docs_search', arguments: { query: 'Halcyon' } },
    { type: 'tool_result', tool: 'docs_search', success: false },
    { type: 'blocked', reason: 'Access denied: board minutes require executive clearance.' },
    { type: 'done', trace_id: 'tr-cmp-mgr' },
  ]),
  ceo: ssePayload([
    { type: 'tool_start', tool: 'docs_search', arguments: { query: 'Halcyon' } },
    { type: 'tool_result', tool: 'docs_search', success: true, data: { doc_id: 'DOC-BOARD-001' } },
    { type: 'sources', sources: [{ type: 'document', id: 'DOC-BOARD-001', title: 'Board Minutes - Project Halcyon' }] },
    { type: 'response', text: 'The Halcyon board minutes discuss the acquisition of Halcyon Logistics Inc. for $4.2M.' },
    { type: 'done', trace_id: 'tr-cmp-ceo' },
  ]),
}

const AUDIT_ENTRIES = [
  { id: 1, timestamp: '2026-10-26T10:00:00Z', user_id: 1, role: 'executive', tool: 'hr_get_salary', arguments: {}, policy_decision: 'allow', result_status: 'success', trace_id: 'tr-abc12345-mock' },
  { id: 2, timestamp: '2026-10-26T10:01:00Z', user_id: 12, role: 'contractor', tool: 'hr_salary_aggregate', arguments: {}, policy_decision: 'deny', result_status: 'blocked', trace_id: 'tr-block-mock' },
]

const TRACE_DATA = {
  trace_id: 'tr-abc12345-mock',
  events: [
    { node: 'planner', duration_ms: 120 },
    { node: 'tool_router', tool: 'hr_get_salary', duration_ms: 45 },
    { node: 'responder', duration_ms: 200 },
  ],
}

// ─── Route helpers ──────────────────────────────────────────────────────────

/** Install mock API routes on a page. Returns a chat response setter for dynamic SSE. */
async function mockApi(page: Page) {
  let chatResponse = CEO_SALARY_SSE
  let currentUser = 'ceo'

  // Demo users
  await page.route('**/api/auth/demo-users', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DEMO_USERS) }),
  )

  // Login
  await page.route('**/api/auth/login', async (route: Route) => {
    const body = JSON.parse((await route.request().postData()) || '{}')
    currentUser = body.username || 'ceo'
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token: `mock-token-${currentUser}`, employee_id: DEMO_USERS.find((u) => u.key === currentUser)?.employee_id ?? 1, role: currentUser, name: currentUser }),
    })
  })

  // Me
  await page.route('**/api/auth/me', (route: Route) => {
    const principal = PRINCIPALS[currentUser] || PRINCIPALS['ceo']
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(principal) })
  })

  // Chat stream
  await page.route('**/api/chat/stream', (route: Route) => {
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: chatResponse })
  })

  // Audit
  await page.route('**/api/audit*', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(AUDIT_ENTRIES) }),
  )

  // Trace
  await page.route('**/api/trace/*', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(TRACE_DATA) }),
  )

  // Approvals
  await page.route('**/api/approvals', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
  )

  return {
    setChatResponse(sse: string) {
      chatResponse = sse
    },
    get currentUser() {
      return currentUser
    },
  }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

test.describe('Keystone UI', () => {
  test('initial load shows people rail and auto-logs in as CEO', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')

    // People rail visible
    await expect(page.locator('.people-rail')).toBeVisible()
    // Identity card rendered with CEO data
    await expect(page.locator('.identity-card')).toBeVisible()
    await expect(page.locator('.identity-name')).toHaveText('Danielle Johnson')
    await expect(page.locator('.identity-title')).toHaveText('CEO')

    // Demo user list rendered
    const userCards = page.locator('.user-card')
    await expect(userCards).toHaveCount(DEMO_USERS.length)

    // Header shows name and role
    await expect(page.locator('.header-role')).toContainText('Danielle Johnson')
  })

  test('switch users updates identity card and clears chat', async ({ page }) => {
    const mock = await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    // Send a message as CEO first
    await page.fill('.chat-input', 'What is my salary?')
    await page.click('.send-btn')
    await expect(page.locator('.bubble-content').last()).toContainText('$383,812')

    // Switch to Sales Manager
    await page.locator('.user-card', { hasText: 'Sales Manager' }).click()
    await expect(page.locator('.identity-name')).toHaveText('Lisa Smith')
    await expect(page.locator('.identity-title')).toHaveText('Sales Manager')

    // Chat should be cleared — welcome screen visible
    await expect(page.locator('.chat-empty')).toBeVisible()
  })

  test('chat flow: CEO salary — shows tool steps, response, sources, trace', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    await page.fill('.chat-input', 'What is my salary?')
    await page.click('.send-btn')

    // User message appears
    await expect(page.locator('.chat-bubble.user .bubble-content')).toHaveText('What is my salary?')

    // Tool step rendered
    const toolStep = page.locator('.tool-step').first()
    await expect(toolStep).toBeVisible()
    await expect(toolStep.locator('.tool-step-name')).toHaveText('hr_get_salary')
    await expect(toolStep.locator('.tool-step-pill')).toHaveText('allowed')

    // Response text
    await expect(page.locator('.chat-bubble.assistant .bubble-content').last()).toContainText('$383,812.00')

    // Source pill
    await expect(page.locator('.source-pill')).toBeVisible()
    await expect(page.locator('.source-pill')).toContainText('SAL-001')

    // Trace link
    await expect(page.locator('.trace-link')).toBeVisible()
    await expect(page.locator('.trace-link')).toContainText('tr-abc12')
  })

  test('manager: team salaries query succeeds', async ({ page }) => {
    const mock = await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    // Switch to Sales Manager
    await page.locator('.user-card', { hasText: 'Sales Manager' }).click()
    await expect(page.locator('.identity-name')).toHaveText('Lisa Smith')

    // Set manager-specific response
    mock.setChatResponse(MANAGER_SALARY_SSE)

    await page.fill('.chat-input', 'Show me the salaries of my direct reports')
    await page.click('.send-btn')

    // Tool step
    await expect(page.locator('.tool-step-name').first()).toHaveText('hr_get_team_salaries')
    await expect(page.locator('.tool-step-pill').first()).toHaveText('allowed')

    // Response mentions direct reports
    await expect(page.locator('.chat-bubble.assistant .bubble-content').last()).toContainText('3 direct reports')
  })

  test('contractor aggregation trap: blocked response', async ({ page }) => {
    const mock = await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    // Switch to contractor
    await page.locator('.user-card', { hasText: 'Contract Developer' }).click()
    await expect(page.locator('.identity-name')).toHaveText('Michelle Rasmussen')

    mock.setChatResponse(CONTRACTOR_BLOCKED_SSE)

    await page.fill('.chat-input', 'What is the average salary in the Engineering department?')
    await page.click('.send-btn')

    // Denied tool step
    const step = page.locator('.tool-step').first()
    await expect(step.locator('.tool-step-pill')).toHaveText('denied')

    // Blocked warning banner
    await expect(page.locator('.blocked-warning')).toBeVisible()
  })

  test('compare mode: 3-column layout with per-role responses', async ({ page }) => {
    // For compare mode, we need to mock login per user and return different SSE per token
    await page.route('**/api/auth/demo-users', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DEMO_USERS) }),
    )

    const tokens: Record<string, string> = {}
    await page.route('**/api/auth/login', async (route) => {
      const body = JSON.parse((await route.request().postData()) || '{}')
      const key = body.username || 'ceo'
      tokens[`mock-token-${key}`] = key
      const principal = PRINCIPALS[key] || PRINCIPALS['ceo']
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: `mock-token-${key}`, employee_id: (principal as any).user_id, role: key, name: key }),
      })
    })

    let lastMeToken = ''
    await page.route('**/api/auth/me', (route) => {
      const auth = route.request().headers()['authorization'] || ''
      const token = auth.replace('Bearer ', '')
      lastMeToken = token
      const key = tokens[token] || 'ceo'
      const principal = PRINCIPALS[key] || PRINCIPALS['ceo']
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(principal) })
    })

    await page.route('**/api/chat/stream', (route) => {
      const auth = route.request().headers()['authorization'] || ''
      const token = auth.replace('Bearer ', '')
      const key = tokens[token] || 'ceo'
      const sse = COMPARE_RESPONSES[key] || COMPARE_RESPONSES['ceo']
      route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse })
    })

    await page.route('**/api/audit*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
    await page.route('**/api/approvals', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
    await page.route('**/api/trace/*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))

    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    // Toggle compare mode via left rail switch
    await page.locator('.compare-switch').click()
    await expect(page.locator('.compare-mode')).toBeVisible()

    // 3 columns exist
    await expect(page.locator('.compare-column')).toHaveCount(3)

    // Type and send question
    await page.fill('.compare-input-field', 'What are the Halcyon board minutes about?')
    await page.locator('.compare-mode .send-btn').click()

    // Wait for responses
    await page.waitForTimeout(500)

    // CEO column has actual response content
    const ceoColumn = page.locator('.compare-column').nth(2) // executive is 3rd
    await expect(ceoColumn.locator('.compare-content')).toContainText('Halcyon Logistics')

    // Contractor and manager columns should show blocked content
    const contractorColumn = page.locator('.compare-column').nth(0)
    await expect(contractorColumn.locator('.blocked-warning')).toBeVisible()

    const mgrColumn = page.locator('.compare-column').nth(1)
    await expect(mgrColumn.locator('.blocked-warning')).toBeVisible()
  })

  test('dark mode toggle', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    // Default is light
    const html = page.locator('html')
    await expect(html).toHaveAttribute('data-theme', 'light')

    // Click theme toggle (1st header button now)
    await page.locator('.header-btn').nth(0).click()
    await expect(html).toHaveAttribute('data-theme', 'dark')

    // Toggle back
    await page.locator('.header-btn').nth(0).click()
    await expect(html).toHaveAttribute('data-theme', 'light')
  })

  test('right panel: audit tab shows entries', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    // Audit tab should be visible (default active)
    await expect(page.locator('.panel-tab.active')).toContainText('Audit')

    // Table should have our mock entries
    const rows = page.locator('.audit-table tbody tr')
    await expect(rows).toHaveCount(2)

    // Check decision pills
    await expect(rows.nth(0).locator('.decision-pill')).toHaveText('allow')
    await expect(rows.nth(1).locator('.decision-pill')).toHaveText('deny')
  })

  test('right panel: trace view loads on click', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    // Send a message to get a trace link
    await page.fill('.chat-input', 'What is my salary?')
    await page.click('.send-btn')
    await expect(page.locator('.trace-link')).toBeVisible()

    // Click trace link
    await page.locator('.trace-link').click()

    // Trace tab should be active
    await expect(page.locator('.panel-tab.active')).toContainText('Trace')

    // Trace JSON should be visible
    await expect(page.locator('.trace-json')).toBeVisible()
    await expect(page.locator('.trace-json')).toContainText('tr-abc12345-mock')
  })

  test('right panel: toggle panel visibility', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    // Panel is visible by default
    await expect(page.locator('.right-panel')).toBeVisible()

    // Click the panel toggle (2nd header button now)
    await page.locator('.header-btn').nth(1).click()

    // Panel should be hidden
    await expect(page.locator('.right-panel')).not.toBeVisible()

    // Toggle back
    await page.locator('.header-btn').nth(1).click()
    await expect(page.locator('.right-panel')).toBeVisible()
  })

  test('suggested questions populate chat input', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.chat-empty')).toBeVisible()

    // Click first suggested question chip
    const suggestedBtn = page.locator('.suggested-chip').first()
    await suggestedBtn.click()

    // A message should appear (the suggested question triggers sendMessage directly)
    await expect(page.locator('.chat-bubble.user')).toBeVisible()
  })

  test('chat input: Enter sends, Shift+Enter adds newline', async ({ page }) => {
    await mockApi(page)
    await page.goto('/')
    await expect(page.locator('.identity-card')).toBeVisible()

    const input = page.locator('.chat-input')
    await input.fill('Hello')

    // Shift+Enter should not send
    await input.press('Shift+Enter')
    await expect(page.locator('.chat-bubble')).toHaveCount(0)

    // Clear and type again, Enter should send
    await input.fill('Test message')
    await input.press('Enter')
    await expect(page.locator('.chat-bubble.user')).toBeVisible()
  })
})
