import { useEffect, useRef, useState } from 'react'
import { Columns3, Loader, Send, Clock } from 'lucide-react'
import { login, streamChat } from '../api'
import type { Source, SSEEvent, ToolStep } from '../types'
import { ROLE_COLORS } from '../theme'

interface ColumnState {
  role: string
  userKey: string
  token: string | null
  content: string
  steps: ToolStep[]
  sources: Source[]
  loading: boolean
  waiting: boolean
  blocked: boolean
  error: string | null
  retrying: boolean
}

const COMPARE_USERS = [
  { key: 'contractor', label: 'Contractor', role: 'contractor' },
  { key: 'ops_manager', label: 'Manager', role: 'manager' },
  { key: 'ceo', label: 'Executive', role: 'executive' },
]

interface Props {
  visible: boolean
}

export function CompareMode({ visible }: Props) {
  const [question, setQuestion] = useState('')
  const [columns, setColumns] = useState<ColumnState[]>(
    COMPARE_USERS.map((u) => ({
      role: u.role,
      userKey: u.key,
      token: null,
      content: '',
      steps: [],
      sources: [],
      loading: false,
      waiting: false,
      blocked: false,
      error: null,
      retrying: false,
    })),
  )
  const [sent, setSent] = useState(false)
  const tokensRef = useRef<Record<string, string>>({})

  useEffect(() => {
    // Pre-authenticate all 3 users
    COMPARE_USERS.forEach(async (u) => {
      try {
        const result = await login(u.key)
        tokensRef.current[u.key] = result.token
        setColumns((prev) => prev.map((c) => (c.userKey === u.key ? { ...c, token: result.token } : c)))
      } catch {
        // will show error when sending
      }
    })
  }, [])

  async function runColumn(u: typeof COMPARE_USERS[number], q: string) {
    const token = tokensRef.current[u.key]
    if (!token) {
      setColumns((prev) => prev.map((c) => (c.userKey === u.key ? { ...c, loading: false, waiting: false, error: 'Not authenticated' } : c)))
      return
    }

    // Mark as loading (no longer waiting)
    setColumns((prev) => prev.map((c) => (c.userKey === u.key ? { ...c, loading: true, waiting: false } : c)))

    const steps: ToolStep[] = []
    const sources: Source[] = []
    let content = ''
    let blocked = false

    try {
      await streamChat(token, q, '', (event: SSEEvent) => {
        switch (event.type) {
          case 'tool_start':
            steps.push({ tool: event.tool as string, arguments: {}, status: 'running' })
            break
          case 'tool_result': {
            const s = steps.find((s) => s.tool === event.tool && s.status === 'running')
            if (s) {
              s.status = event.success ? 'done' : 'denied'
              s.success = event.success as boolean
            }
            break
          }
          case 'sources':
            if (event.sources) sources.push(...(event.sources as Source[]))
            break
          case 'response':
            content = event.text as string
            break
          case 'blocked':
            blocked = true
            content = event.reason as string
            break
          case 'error':
            content = event.message as string
            break
        }
        setColumns((prev) =>
          prev.map((c) => (c.userKey === u.key ? { ...c, content, steps: [...steps], sources: [...sources], blocked } : c)),
        )
      })
    } catch (err) {
      content = err instanceof Error ? err.message : 'Something went wrong'
    }

    setColumns((prev) =>
      prev.map((c) =>
        c.userKey === u.key ? { ...c, content, steps: [...steps], sources: [...sources], blocked, loading: false, waiting: false } : c,
      ),
    )
  }

  async function handleSend() {
    if (!question.trim()) return
    const q = question.trim()
    setSent(true)

    // Reset all columns: first is loading, rest are waiting
    setColumns((prev) =>
      prev.map((c, i) => ({
        ...c,
        content: '',
        steps: [],
        sources: [],
        loading: i === 0,
        waiting: i > 0,
        blocked: false,
        error: null,
        retrying: false,
      })),
    )

    // Run columns sequentially to avoid rate limit bursts
    for (const u of COMPARE_USERS) {
      await runColumn(u, q)
    }
  }

  if (!visible) return null

  return (
    <div className="compare-mode">
      <div className="compare-input">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask the same question as 3 different roles..."
          className="compare-input-field"
        />
        <button className="send-btn" onClick={handleSend} disabled={!question.trim()}>
          <Send size={18} />
        </button>
      </div>

      <div className="compare-columns">
        {columns.map((col, i) => (
          <div key={COMPARE_USERS[i].key} className="compare-column">
            <div className="compare-column-header" style={{ borderBottomColor: ROLE_COLORS[col.role] || '#6b7280' }}>
              <Columns3 size={14} />
              <span>{COMPARE_USERS[i].label}</span>
              <span className="role-badge" style={{ background: ROLE_COLORS[col.role] }}>
                {col.role}
              </span>
            </div>

            <div className="compare-column-body">
              {col.waiting && (
                <div className="compare-waiting">
                  <Clock size={16} />
                  <span>Waiting...</span>
                </div>
              )}

              {col.loading && (
                <div className="compare-loading">
                  <Loader size={16} className="spin" />
                  <span>Thinking...</span>
                </div>
              )}

              {col.retrying && (
                <div className="compare-loading retrying">
                  <Loader size={16} className="spin" />
                  <span>Model is busy, retrying...</span>
                </div>
              )}

              {col.steps.length > 0 && (
                <div className="tool-steps compact">
                  {col.steps.map((s, j) => (
                    <div key={j} className={`tool-step ${s.status}`}>
                      <span className="tool-step-name">{s.tool}</span>
                      <span className={`tool-step-pill ${s.status}`}>
                        {s.status === 'denied' ? 'denied' : s.status === 'done' ? 'ok' : '...'}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {col.blocked && <div className="blocked-warning compact">Blocked by security filter</div>}

              {col.content && <div className="compare-content">{col.content}</div>}

              {!sent && !col.loading && !col.waiting && <p className="hint">Response will appear here</p>}

              {col.error && <p className="error-text">{col.error}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
