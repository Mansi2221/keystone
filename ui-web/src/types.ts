export interface DemoUser {
  key: string
  employee_id: number
  role: string
  department?: string
  name: string
  title?: string
  description: string
  groups?: string[]
}

export interface Principal {
  user_id: number
  employee_id: string
  role: string
  department: string
  groups: string[]
  manager_id: number | null
  report_count: number
  name?: string
  title?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  trace_id?: string
  tool_steps?: ToolStep[]
  blocked?: boolean
  timestamp: number
}

export interface Source {
  type: string
  id: string
  title: string
}

export interface ToolStep {
  tool: string
  arguments: Record<string, unknown>
  success?: boolean
  data?: unknown
  status: 'running' | 'done' | 'denied'
}

export interface AuditEntry {
  id: number
  timestamp: string
  user_id: number
  role: string
  tool: string
  arguments: Record<string, unknown>
  policy_decision: string
  result_status: string
  trace_id?: string
}

export interface ApprovalEntry {
  id: string
  tool: string
  arguments: Record<string, unknown>
  user_id: number
  status: string
  created_at: string
}

export interface SSEEvent {
  type: string
  [key: string]: unknown
}
