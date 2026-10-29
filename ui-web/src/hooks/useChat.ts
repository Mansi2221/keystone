import { useCallback, useRef, useState } from 'react'
import { streamChat } from '../api'
import type { ChatMessage, Source, SSEEvent, ToolStep } from '../types'

let msgCounter = 0
function nextId() {
  return `msg-${++msgCounter}-${Date.now()}`
}

export function useChat(token: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentSteps, setCurrentSteps] = useState<ToolStep[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(
    async (text: string) => {
      if (!token || !text.trim() || isLoading) return

      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        content: text.trim(),
        timestamp: Date.now(),
      }

      const assistantId = nextId()
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        tool_steps: [],
        sources: [],
        timestamp: Date.now(),
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsLoading(true)
      setCurrentSteps([])

      const steps: ToolStep[] = []
      const sources: Source[] = []
      let responseText = ''
      let traceId = ''
      let blocked = false

      try {
        await streamChat(token, text.trim(), '', (event: SSEEvent) => {
          switch (event.type) {
            case 'node': {
              // Node progress — no visible change needed
              break
            }
            case 'tool_start': {
              const step: ToolStep = {
                tool: event.tool as string,
                arguments: (event.arguments as Record<string, unknown>) || {},
                status: 'running',
              }
              steps.push(step)
              setCurrentSteps([...steps])
              updateAssistant()
              break
            }
            case 'tool_result': {
              const last = steps.find((s) => s.tool === event.tool && s.status === 'running')
              if (last) {
                last.status = event.success ? 'done' : 'denied'
                last.success = event.success as boolean
                last.data = event.data
              }
              setCurrentSteps([...steps])
              updateAssistant()
              break
            }
            case 'sources': {
              const evtSources = event.sources as Source[]
              if (evtSources) sources.push(...evtSources)
              updateAssistant()
              break
            }
            case 'response': {
              responseText = event.text as string
              updateAssistant()
              break
            }
            case 'blocked': {
              blocked = true
              responseText = event.reason as string
              updateAssistant()
              break
            }
            case 'done': {
              traceId = (event.trace_id as string) || ''
              updateAssistant()
              break
            }
            case 'error': {
              responseText = `Error: ${event.message}`
              updateAssistant()
              break
            }
          }
        })
      } catch (err) {
        responseText = `Connection error: ${err instanceof Error ? err.message : 'unknown'}`
      }

      // Final update
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: responseText, tool_steps: [...steps], sources: [...sources], trace_id: traceId, blocked }
            : m,
        ),
      )
      setIsLoading(false)
      setCurrentSteps([])

      function updateAssistant() {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: responseText, tool_steps: [...steps], sources: [...sources], trace_id: traceId, blocked }
              : m,
          ),
        )
      }
    },
    [token, isLoading],
  )

  const clearMessages = useCallback(() => {
    setMessages([])
    setCurrentSteps([])
  }, [])

  return { messages, sendMessage, isLoading, currentSteps, clearMessages }
}
