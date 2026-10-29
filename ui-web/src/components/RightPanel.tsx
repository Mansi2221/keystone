import { useEffect, useState } from 'react'
import { Activity, ClipboardCheck, Search } from 'lucide-react'
import { fetchAudit, fetchTrace } from '../api'
import type { AuditEntry } from '../types'

type Tab = 'approvals' | 'audit' | 'trace'

interface Props {
  token: string | null
  selectedTraceId: string | null
}

export function RightPanel({ token, selectedTraceId }: Props) {
  const [tab, setTab] = useState<Tab>('audit')
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [trace, setTrace] = useState<unknown>(null)
  const [traceLoading, setTraceLoading] = useState(false)

  useEffect(() => {
    if (token && tab === 'audit') {
      fetchAudit(token, 30).then(setAudit).catch(() => {})
    }
  }, [token, tab])

  useEffect(() => {
    if (selectedTraceId && token) {
      setTab('trace')
      setTraceLoading(true)
      fetchTrace(token, selectedTraceId)
        .then(setTrace)
        .catch(() => setTrace(null))
        .finally(() => setTraceLoading(false))
    }
  }, [selectedTraceId, token])

  return (
    <aside className="right-panel">
      <div className="panel-tabs">
        <button className={`panel-tab ${tab === 'approvals' ? 'active' : ''}`} onClick={() => setTab('approvals')}>
          <ClipboardCheck size={14} /> Approvals
        </button>
        <button className={`panel-tab ${tab === 'audit' ? 'active' : ''}`} onClick={() => setTab('audit')}>
          <Activity size={14} /> Audit
        </button>
        <button className={`panel-tab ${tab === 'trace' ? 'active' : ''}`} onClick={() => setTab('trace')}>
          <Search size={14} /> Trace
        </button>
      </div>

      <div className="panel-content">
        {tab === 'approvals' && (
          <div className="approvals-empty">
            <ClipboardCheck size={32} className="dim" />
            <p>No pending approvals</p>
            <p className="hint">Write actions will appear here for review</p>
          </div>
        )}

        {tab === 'audit' && (
          <div className="audit-list">
            {audit.length === 0 ? (
              <p className="hint">No audit entries yet</p>
            ) : (
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Tool</th>
                    <th>Decision</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id}>
                      <td className="mono">{new Date(a.timestamp).toLocaleTimeString()}</td>
                      <td className="mono">{a.tool}</td>
                      <td>
                        <span className={`decision-pill ${a.policy_decision}`}>{a.policy_decision}</span>
                      </td>
                      <td>
                        <span className={`status-pill ${a.result_status}`}>{a.result_status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {tab === 'trace' && (
          <div className="trace-view">
            {traceLoading ? (
              <p className="hint">Loading trace...</p>
            ) : !selectedTraceId ? (
              <p className="hint">Click a trace link in chat to view details</p>
            ) : trace ? (
              <pre className="trace-json">{JSON.stringify(trace, null, 2)}</pre>
            ) : (
              <p className="hint">No trace data found</p>
            )}
          </div>
        )}
      </div>
    </aside>
  )
}
