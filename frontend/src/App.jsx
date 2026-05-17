import { useMemo, useState } from 'react'
import { MessageContent } from './components/MessageContent'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
// Align with backend Ollama: DIVALTO_OLLAMA_TIMEOUT_SECONDS * (DIVALTO_OLLAMA_RETRIES + 1) + margin for ERP/mock steps.
const CHAT_TIMEOUT_REAL_MS = Number(import.meta.env.VITE_CHAT_TIMEOUT_REAL_MS) || 150000
// Mock planner skips backend Ollama for classic/phase5; keep headroom for slow SQLite / network.
const CHAT_TIMEOUT_MOCK_MS = Number(import.meta.env.VITE_CHAT_TIMEOUT_MOCK_MS) || 90000

function buildAssistantReply(payload) {
  if (!payload) return 'No response payload received.'
  if (typeof payload.answer === 'string') return payload.answer
  if (typeof payload.message === 'string') return payload.message
  return JSON.stringify(payload, null, 2)
}

function App() {
  const [messages, setMessages] = useState([
    {
      id: crypto.randomUUID(),
      role: 'assistant',
      content:
        'Welcome. Ask me anything about sales, stock, billing, clients, or analytics. I will route through your Divalto pipeline.',
      createdAt: new Date().toISOString(),
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const mode = 'auto'
  const [resolvedMode, setResolvedMode] = useState('auto')
  const [useRealPlanner, setUseRealPlanner] = useState(true)
  const [error, setError] = useState('')
  const [plannerReady, setPlannerReady] = useState(true)

  const canSend = input.trim().length > 0 && !loading
  const sortedMessages = useMemo(() => messages.slice(), [messages])

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
    const userMsg = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setError('')

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
          mode,
          real_planner: useRealPlanner,
        }),
      }).finally(() => clearTimeout(timeoutId))

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload?.detail || payload?.error || 'Request failed')
      }
      setResolvedMode(typeof payload?.mode === 'string' ? payload.mode : 'auto')

      const assistantMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: buildAssistantReply(payload),
        createdAt: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (err) {
      const message =
        err instanceof Error && err.name === 'AbortError'
          ? `Request timed out after ${Math.round((useRealPlanner ? CHAT_TIMEOUT_REAL_MS : CHAT_TIMEOUT_MOCK_MS) / 1000)} seconds.`
          : err instanceof Error
            ? err.message
            : 'Unknown error'
      setError(message)
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `I could not complete the request: ${message}`,
          createdAt: new Date().toISOString(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(event) {
    event.preventDefault()
    void sendMessage()
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-dot" />
          <div>
            <h1>Divalto AI</h1>
            <p>Professional assistant workspace</p>
          </div>
        </div>
        <div className="controls">
          <label>
            Mode
            <input value="auto (inferred from question)" disabled readOnly />
          </label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={useRealPlanner}
              onChange={(e) => {
                const enabled = e.target.checked
                setUseRealPlanner(enabled)
                if (!enabled) {
                  setPlannerReady(false)
                }
              }}
            />
            <span>Use real planner (Ollama)</span>
          </label>
        </div>
        <div className="status-card">
          <p>API</p>
          <code>{API_BASE_URL}</code>
          <p style={{ marginTop: 8 }}>
            Planner: {useRealPlanner ? (plannerReady ? 'real (warmed)' : 'real (warmup pending)') : 'mock'}
          </p>
        </div>
      </aside>

      <main className="chat-panel">
        <header className="chat-header">
          <h2>Assistant</h2>
          <div className="badges">
            <span>{`auto -> ${resolvedMode}`}</span>
            <span>{useRealPlanner ? 'real planner' : 'mock planner'}</span>
          </div>
        </header>

        <section className="messages" aria-live="polite">
          {sortedMessages.map((msg) => (
            <article key={msg.id} className={`bubble ${msg.role}`}>
              {msg.role === 'assistant' ? (
                <MessageContent content={msg.content} />
              ) : (
                <p className="text-segment">{msg.content}</p>
              )}
            </article>
          ))}
          {loading ? <article className="bubble assistant"><p>Thinking...</p></article> : null}
        </section>

        <form className="composer" onSubmit={onSubmit}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask your business question..."
            rows={2}
          />
          <button type="submit" disabled={!canSend}>
            Send
          </button>
        </form>
        {error ? <p className="error">{error}</p> : null}
      </main>
    </div>
  )
}

export default App
