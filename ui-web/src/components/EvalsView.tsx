import { useEffect, useState } from 'react'
import { BarChart3, RefreshCw, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface IterationResult {
  note: string
  git_commit: string
  data_checksum: string
  total_cases: number
  leaks: number
  exposed: number
  leak_total: number
  leak_rate: number
  exposure_rate: number
  task_passed: number
  task_total: number
  task_rate: number
  or_passed: number
  or_total: number
  or_rate: number
  tool_call_rate: number
  elapsed_seconds: number
  total_llm_calls: number
  timestamp: string
  leak_by_attack: Record<string, { total: number; leaked: number; exposed: number }>
}

interface EvalData {
  [iteration: string]: IterationResult
}

export function EvalsView() {
  const [data, setData] = useState<EvalData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/evals/results`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (e: any) {
      setError(e.message || 'Failed to load eval results')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  if (loading) return <div className="evals-loading"><RefreshCw className="spin" size={20} /> Loading eval results...</div>
  if (error) return <div className="evals-error"><AlertTriangle size={16} /> {error}</div>
  if (!data || Object.keys(data).length === 0) return <div className="evals-empty">No ablation results found. Run the ablation study first.</div>

  const iterations = Object.entries(data).sort(([a], [b]) => a.localeCompare(b))
  const attackTypes = iterations.length > 0
    ? Object.keys(iterations[0][1].leak_by_attack || {}).sort()
    : []

  return (
    <div className="evals-view">
      <div className="evals-header">
        <h2><BarChart3 size={20} /> Ablation Study Results</h2>
        <button className="header-btn" onClick={fetchData} title="Refresh">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Summary Table */}
      <div className="evals-section">
        <h3>Summary</h3>
        <div className="evals-table-wrap">
          <table className="evals-table">
            <thead>
              <tr>
                <th>Iteration</th>
                <th>Protections</th>
                <th>Leak Rate</th>
                <th>Exposure</th>
                <th>Task Success</th>
                <th>Over-Refusal</th>
                <th>LLM Calls</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {iterations.map(([name, r]) => (
                <tr key={name}>
                  <td className="evals-iter-name">{name}</td>
                  <td className="evals-note">{r.note}</td>
                  <td className={r.leak_rate > 0.1 ? 'evals-bad' : 'evals-good'}>
                    {(r.leak_rate * 100).toFixed(1)}% ({r.leaks}/{r.leak_total})
                  </td>
                  <td className={r.exposure_rate > 0.05 ? 'evals-bad' : 'evals-good'}>
                    {(r.exposure_rate * 100).toFixed(1)}% ({r.exposed}/{r.leak_total})
                  </td>
                  <td>{(r.task_rate * 100).toFixed(0)}% ({r.task_passed}/{r.task_total})</td>
                  <td className={r.or_rate < 0.9 ? 'evals-warn' : 'evals-good'}>
                    {(r.or_rate * 100).toFixed(0)}% ({r.or_passed}/{r.or_total})
                  </td>
                  <td>{r.total_llm_calls}</td>
                  <td>{Math.round(r.elapsed_seconds / 60)}m</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Leaks by Attack Type */}
      <div className="evals-section">
        <h3>Leaks by Attack Type</h3>
        <div className="evals-table-wrap">
          <table className="evals-table">
            <thead>
              <tr>
                <th>Attack Type</th>
                {iterations.map(([name]) => (
                  <th key={name}>{name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {attackTypes.map(attack => (
                <tr key={attack}>
                  <td>{attack.replace(/_/g, ' ')}</td>
                  {iterations.map(([name, r]) => {
                    const a = r.leak_by_attack?.[attack]
                    if (!a) return <td key={name}>-</td>
                    return (
                      <td key={name} className={a.leaked > 0 ? 'evals-bad' : 'evals-good'}>
                        {a.leaked}/{a.total}
                        {a.leaked === 0 && <CheckCircle size={12} style={{ marginLeft: 4 }} />}
                        {a.leaked > 0 && <XCircle size={12} style={{ marginLeft: 4 }} />}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Metadata */}
      <div className="evals-section evals-meta">
        <h3>Run Metadata</h3>
        {iterations.length > 0 && (
          <div className="evals-meta-grid">
            <div><strong>Git Commit:</strong> {iterations[0][1].git_commit}</div>
            <div><strong>Data Checksum:</strong> {iterations[0][1].data_checksum}</div>
            <div><strong>Last Updated:</strong> {iterations[iterations.length - 1][1].timestamp}</div>
            <div><strong>Total Cases:</strong> {iterations[0][1].total_cases} per iteration</div>
          </div>
        )}
      </div>
    </div>
  )
}
