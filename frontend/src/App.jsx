import { useEffect, useRef, useState } from 'react'
import { AssistantMessageToolbar } from './components/AssistantMessageToolbar'
import { getFirstChartContainerId, MessageContent } from './components/MessageContent'
import { PreferencesBar } from './components/PreferencesBar'
import { Sidebar } from './components/Sidebar'
import { usePersistedApp } from './hooks/usePersistedApp'
import { formatMessageTime } from './utils/formatTime'
import { detectFormatFromQuery, resolveDisplayMode } from './utils/outputFormat'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const CHAT_TIMEOUT_REAL_MS = Number(import.meta.env.VITE_CHAT_TIMEOUT_REAL_MS) || 150000
const CHAT_TIMEOUT_MOCK_MS = Number(import.meta.env.VITE_CHAT_TIMEOUT_MOCK_MS) || 90000
const MODE = 'auto'

function buildAssistantReply(payload) {
  if (!payload) return 'No response payload received.'
  if (typeof payload.answer === 'string') return payload.answer
  if (typeof payload.message === 'string') return payload.message
  return JSON.stringify(payload, null, 2)
}

function App() {
  const {
    preferences,
    setPreference,
    conversations,
    activeConversation,
    selectConversation,
    newConversation,
    deleteConversation,
    clearAllHistory,
    appendMessages,
    setMessageFeedback,
  } = usePersistedApp()

  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [resolvedMode, setResolvedMode] = useState('auto')
  const [error, setError] = useState('')
  const [plannerReady, setPlannerReady] = useState(true)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const messagesEndRef = useRef(null)

  const useRealPlanner = preferences.useRealPlanner
  const messages = activeConversation?.messages ?? []
  const canSend = input.trim().length > 0 && !loading

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function handlePreferenceChange(key, value) {
    if (key === 'useRealPlanner' && value === false) {
      setPlannerReady(false)
    }
    setPreference(key, value)
  }

  async function warmupPlannerIfNeeded() {
    if (!useRealPlanner || plannerReady) return
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 300000)
    const response = await fetch(`${API_BASE_URL}/api/planner/warmup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({ pull_if_missing: true }),
    }).finally(() => clearTimeout(timeoutId))

    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload?.detail || payload?.error || 'Planner warmup failed')
    }
    setPlannerReady(true)
  }

  async function sendMessage() {
    if (!canSend) return
    const text = input.trim()
    setInput('')
    setLoading(true)
    setError('')

    const queryFormatHint = detectFormatFromQuery(text)
    appendMessages([{ role: 'user', content: text }])

    try {
      await warmupPlannerIfNeeded()
      const controller = new AbortController()
      const timeoutMs = useRealPlanner ? CHAT_TIMEOUT_REAL_MS : CHAT_TIMEOUT_MOCK_MS
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          query: text,
          mode: MODE,
          real_planner: useRealPlanner,
        }),
      }).finally(() => clearTimeout(timeoutId))

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload?.detail || payload?.error || 'Request failed')
      }
      setResolvedMode(typeof payload?.mode === 'string' ? payload.mode : 'auto')
      appendMessages([
        {
          role: 'assistant',
          content: buildAssistantReply(payload),
          mode: typeof payload?.mode === 'string' ? payload.mode : resolvedMode,
          displayFormat: resolveDisplayMode(preferences.displayFormat, queryFormatHint),
        },
      ])
    } catch (err) {
      const message =
        err instanceof Error && err.name === 'AbortError'
          ? `Délai dépassé (${Math.round((useRealPlanner ? CHAT_TIMEOUT_REAL_MS : CHAT_TIMEOUT_MOCK_MS) / 1000)} s).`
          : err instanceof Error
            ? err.message
            : 'Erreur inconnue'
      setError(message)
      appendMessages([
        { role: 'assistant', content: `Je n'ai pas pu terminer la requête : ${message}` },
      ])
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(event) {
    event.preventDefault()
    void sendMessage()
  }

  function onComposerKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendMessage()
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        apiBaseUrl={API_BASE_URL}
        conversations={conversations}
        activeConversationId={activeConversation.id}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
        onSelectConversation={selectConversation}
        onNewConversation={newConversation}
        onDeleteConversation={deleteConversation}
        onClearHistory={() => {
          if (window.confirm('Supprimer toutes les conversations enregistrées ?')) {
            clearAllHistory()
          }
        }}
      />

      <main className="chat-panel">
        <header className="chat-header">
          <div className="chat-header-top">
            <h2>{activeConversation.title}</h2>
            <p className="chat-subtitle">
              Pipeline {resolvedMode} · affichage{' '}
              {preferences.displayFormat === 'auto' ? 'automatique' : preferences.displayFormat}
            </p>
          </div>
          <PreferencesBar
            preferences={preferences}
            plannerReady={plannerReady}
            onPreferenceChange={handlePreferenceChange}
          />
        </header>

        <section className="messages" aria-live="polite">
          <div className="messages-inner">
            {messages.map((msg, msgIndex) => {
              const precedingUser =
                msg.role === 'assistant'
                  ? [...messages]
                      .slice(0, msgIndex)
                      .reverse()
                      .find((m) => m.role === 'user')
                  : null
              const isWelcomeOnly =
                msg.role === 'assistant' && msgIndex === 0 && messages.length === 1
              const chartContainerId =
                msg.role === 'assistant'
                  ? getFirstChartContainerId(msg.id, msg.content)
                  : null

              return (
              <article key={msg.id} className={`message-row ${msg.role}`}>
                <div className={`avatar ${msg.role}`} aria-hidden>
                  {msg.role === 'user' ? 'V' : 'AI'}
                </div>
                <div className={`bubble ${msg.role}`}>
                  <header className="bubble-header">
                    <span className="bubble-role">
                      {msg.role === 'user' ? 'Vous' : 'Assistant'}
                    </span>
                    <time className="bubble-time" dateTime={msg.createdAt}>
                      {formatMessageTime(msg.createdAt)}
                    </time>
                  </header>
                  {msg.role === 'assistant' ? (
                    <>
                      <MessageContent
                        content={msg.content}
                        chartType={preferences.chartType}
                        messageId={msg.id}
                        displayMode={
                          msg.displayFormat ||
                          resolveDisplayMode(
                            preferences.displayFormat,
                            precedingUser ? detectFormatFromQuery(precedingUser.content) : null,
                          )
                        }
                      />
                      {!isWelcomeOnly ? (
                        <AssistantMessageToolbar
                          messageId={msg.id}
                          content={msg.content}
                          userQuery={precedingUser?.content || ''}
                          conversationId={activeConversation.id}
                          mode={msg.mode || resolvedMode}
                          chartType={preferences.chartType}
                          realPlanner={useRealPlanner}
                          apiBaseUrl={API_BASE_URL}
                          feedbackRating={msg.feedbackRating}
                          chartContainerId={chartContainerId}
                          onFeedback={setMessageFeedback}
                        />
                      ) : null}
                    </>
                  ) : (
                    <p className="text-segment">{msg.content}</p>
                  )}
                </div>
              </article>
              )
            })}
            {loading ? (
              <article className="message-row assistant">
                <div className="avatar assistant" aria-hidden>
                  AI
                </div>
                <div className="bubble assistant loading-bubble">
                  <span className="typing">
                    <span />
                    <span />
                    <span />
                  </span>
                  Analyse en cours…
                </div>
              </article>
            ) : null}
            <div ref={messagesEndRef} />
          </div>
        </section>

        <form className="composer" onSubmit={onSubmit}>
          <div className="composer-inner">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onComposerKeyDown}
              placeholder="Ex. Chiffre d'affaires par ville en tableau… (Entrée pour envoyer)"
              rows={2}
              disabled={loading}
            />
            <button type="submit" className="btn-primary" disabled={!canSend}>
              Envoyer
            </button>
          </div>
          {error ? <p className="error">{error}</p> : null}
        </form>
      </main>
    </div>
  )
}

export default App
