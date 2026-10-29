import { useEffect, useRef } from 'react'
import { AlertTriangle, CheckCircle, FileText, Loader, XCircle } from 'lucide-react'
import type { ChatMessage } from '../types'

interface Props {
  messages: ChatMessage[]
  isLoading: boolean
  onTraceClick?: (traceId: string) => void
}

export function Chat({ messages, isLoading, onTraceClick }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div className="chat-messages">
      {messages.map((msg) => (
        <div key={msg.id} className={`chat-bubble ${msg.role}`}>
          {msg.role === 'assistant' && msg.tool_steps && msg.tool_steps.length > 0 && (
            <div className="tool-steps">
              {msg.tool_steps.map((step, i) => (
                <div key={i} className={`tool-step ${step.status}`}>
                  <span className="tool-step-icon">
                    {step.status === 'running' ? (
                      <Loader size={12} className="spin" />
                    ) : step.status === 'denied' ? (
                      <XCircle size={12} />
                    ) : (
                      <CheckCircle size={12} />
                    )}
                  </span>
                  <span className="tool-step-name">{step.tool}</span>
                  <span className={`tool-step-pill ${step.status}`}>
                    {step.status === 'running' ? 'running' : step.status === 'denied' ? 'denied' : 'allowed'}
                  </span>
                </div>
              ))}
            </div>
          )}

          {msg.blocked && (
            <div className="blocked-warning">
              <AlertTriangle size={14} />
              <span>Response blocked by security filter</span>
            </div>
          )}

          <div className="bubble-content">
            {msg.content || (msg.role === 'assistant' && isLoading ? '' : '')}
          </div>

          {msg.sources && msg.sources.length > 0 && (
            <div className="source-pills">
              {msg.sources.map((s, i) => (
                <span key={i} className="source-pill">
                  <FileText size={10} />
                  {s.id}
                </span>
              ))}
            </div>
          )}

          {msg.trace_id && (
            <button className="trace-link" onClick={() => onTraceClick?.(msg.trace_id!)}>
              Trace: {msg.trace_id.slice(0, 8)}...
            </button>
          )}
        </div>
      ))}

      {isLoading && messages[messages.length - 1]?.role === 'assistant' && !messages[messages.length - 1]?.content && (
        <div className="typing-indicator">
          <span /><span /><span />
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
