import { useCallback, useEffect, useState } from 'react'
import { Moon, PanelRightClose, PanelRightOpen, Sun, BarChart3, MessageSquare, GitCompare, Play } from 'lucide-react'
import { PeopleRail } from './components/PeopleRail'
import { Chat } from './components/Chat'
import { ChatInput } from './components/ChatInput'
import { SuggestedQuestions } from './components/SuggestedQuestions'
import { RightPanel } from './components/RightPanel'
import { CompareMode } from './components/CompareMode'
import { EvalsView } from './components/EvalsView'
import { DemoBanner } from './components/DemoBanner'
import { useAuth } from './hooks/useAuth'
import { useChat } from './hooks/useChat'
import { applyTheme, getStoredTheme, storeTheme, type Theme } from './theme'

type View = 'chat' | 'compare' | 'evals'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function App() {
  const [theme, setTheme] = useState<Theme>(getStoredTheme)
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [compareMode, setCompareMode] = useState(false)
  const [currentView, setCurrentView] = useState<View>('chat')
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)
  const [replayMode, setReplayMode] = useState(false)

  const auth = useAuth()
  const chat = useChat(auth.token)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const toggleTheme = useCallback(() => {
    const next = theme === 'light' ? 'dark' : 'light'
    setTheme(next)
    storeTheme(next)
  }, [theme])

  const handleSelectUser = useCallback(
    (key: string) => {
      chat.clearMessages()
      setCompareMode(false)
      auth.login(key)
    },
    [auth, chat],
  )

  // Check if we're in replay mode
  useEffect(() => {
    fetch(`${API}/mode`).then(r => r.json()).then(d => {
      setReplayMode(d.mode === 'replay')
    }).catch(() => {})
  }, [])

  // Auto-login as CEO on first visit
  useEffect(() => {
    if (!auth.isAuthenticated && !auth.loading && auth.demoUsers.length > 0) {
      auth.login('ceo')
    }
  }, [auth.demoUsers.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleViewChange = useCallback((view: View) => {
    setCurrentView(view)
    setCompareMode(view === 'compare')
  }, [])

  return (
    <div className={`app-layout ${rightPanelOpen ? '' : 'right-collapsed'} ${compareMode ? 'compare-active' : ''}`}>
      <DemoBanner />

      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <span className="header-title">&#9670; Keystone</span>
          {auth.principal && (
            <span className="header-role">
              {auth.principal.name || auth.principal.employee_id} &middot;{' '}
              {auth.principal.title || auth.principal.role} &middot; {auth.principal.department}
            </span>
          )}
        </div>
        <nav className="header-nav">
          <button
            className={`header-nav-btn ${currentView === 'chat' ? 'active' : ''}`}
            onClick={() => handleViewChange('chat')}
          >
            <MessageSquare size={14} /> Chat
          </button>
          <button
            className={`header-nav-btn ${currentView === 'compare' ? 'active' : ''}`}
            onClick={() => handleViewChange('compare')}
          >
            <GitCompare size={14} /> Compare
          </button>
          <button
            className={`header-nav-btn ${currentView === 'evals' ? 'active' : ''}`}
            onClick={() => handleViewChange('evals')}
          >
            <BarChart3 size={14} /> Evals
          </button>
        </nav>
        <div className="header-actions">
          {replayMode && (
            <span className="replay-badge"><Play size={12} /> Replay</span>
          )}
          <button className="header-btn" onClick={toggleTheme} title="Toggle theme">
            {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
          </button>
          <button className="header-btn" onClick={() => setRightPanelOpen(!rightPanelOpen)} title="Toggle panel">
            {rightPanelOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
          </button>
        </div>
      </header>

      {/* Left Rail */}
      <PeopleRail
        demoUsers={auth.demoUsers}
        currentUserKey={auth.currentUserKey}
        principal={auth.principal}
        onSelectUser={handleSelectUser}
        compareMode={compareMode}
        onToggleCompare={() => setCompareMode(!compareMode)}
      />

      {/* Center */}
      <main className="chat-area">
        {currentView === 'evals' ? (
          <EvalsView />
        ) : currentView === 'compare' ? (
          <CompareMode visible={true} />
        ) : (
          <>
            {chat.messages.length === 0 && (
              <div className="chat-empty">
                <h2>Welcome to Keystone</h2>
                <p>Ask questions about HR data, tickets, documents, deals, or team chat. Your access is filtered by your role and permissions.</p>
                <p style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Try one of the questions below, or type your own.</p>
                <SuggestedQuestions onSelect={chat.sendMessage} />
              </div>
            )}
            <Chat messages={chat.messages} isLoading={chat.isLoading} onTraceClick={setSelectedTraceId} />
            <ChatInput onSend={chat.sendMessage} disabled={chat.isLoading || !auth.isAuthenticated} />
          </>
        )}
      </main>

      {/* Right Panel */}
      {rightPanelOpen && <RightPanel token={auth.token} selectedTraceId={selectedTraceId} />}
    </div>
  )
}
