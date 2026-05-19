import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const STORAGE_KEY = 'motiondivalto-chat-v1'

const WELCOME_MESSAGE = {
  role: 'assistant',
  content:
    'Bienvenue. Posez vos questions sur les ventes, stocks, facturation, clients ou la analytique. Vos conversations sont enregistrées sur cet appareil.',
}

function newId() {
  return crypto.randomUUID()
}

function nowIso() {
  return new Date().toISOString()
}

function titleFromMessage(text) {
  const t = text.trim().replace(/\s+/g, ' ')
  if (!t) return 'Nouvelle conversation'
  return t.length > 42 ? `${t.slice(0, 40)}…` : t
}

function createConversation(withWelcome = true) {
  const id = newId()
  const ts = nowIso()
  return {
    id,
    title: 'Nouvelle conversation',
    createdAt: ts,
    updatedAt: ts,
    messages: withWelcome
      ? [{ id: newId(), ...WELCOME_MESSAGE, createdAt: ts }]
      : [],
  }
}

function defaultState() {
  const conv = createConversation(true)
  return {
    preferences: {
      theme: 'light',
      chartType: 'bar',
      displayFormat: 'auto',
      useRealPlanner: true,
    },
    activeConversationId: conv.id,
    conversations: [conv],
  }
}

function normalizeState(raw) {
  if (!raw || typeof raw !== 'object') return defaultState()
  const preferences = {
    theme: raw.preferences?.theme === 'light' ? 'light' : 'dark',
    chartType: ['bar', 'line', 'pie'].includes(raw.preferences?.chartType)
      ? raw.preferences.chartType
      : 'bar',
    displayFormat: ['auto', 'table', 'chart'].includes(raw.preferences?.displayFormat)
      ? raw.preferences.displayFormat
      : 'auto',
    useRealPlanner: raw.preferences?.useRealPlanner !== false,
  }
  let conversations = Array.isArray(raw.conversations) ? raw.conversations : []
  conversations = conversations
    .filter((c) => c && typeof c.id === 'string')
    .map((c) => ({
      id: c.id,
      title: typeof c.title === 'string' ? c.title : 'Conversation',
      createdAt: c.createdAt || nowIso(),
      updatedAt: c.updatedAt || nowIso(),
      messages: Array.isArray(c.messages)
        ? c.messages
            .filter((m) => m && (m.role === 'user' || m.role === 'assistant'))
            .map((m) => ({
              id: typeof m.id === 'string' ? m.id : newId(),
              role: m.role,
              content: typeof m.content === 'string' ? m.content : '',
              createdAt: m.createdAt || nowIso(),
              mode: typeof m.mode === 'string' ? m.mode : undefined,
              displayFormat: ['auto', 'table', 'chart'].includes(m.displayFormat)
                ? m.displayFormat
                : undefined,
              feedbackRating:
                m.feedbackRating === 'up' || m.feedbackRating === 'down'
                  ? m.feedbackRating
                  : undefined,
            }))
        : [],
    }))

  if (conversations.length === 0) {
    const conv = createConversation(true)
    conversations = [conv]
  }

  const activeConversationId = conversations.some((c) => c.id === raw.activeConversationId)
    ? raw.activeConversationId
    : conversations[0].id

  return { preferences, activeConversationId, conversations }
}

export function loadPersistedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultState()
    return normalizeState(JSON.parse(raw))
  } catch {
    return defaultState()
  }
}

export function usePersistedApp() {
  const [state, setState] = useState(() => loadPersistedState())
  const saveTimer = useRef(null)

  const activeConversation = useMemo(
    () =>
      state.conversations.find((c) => c.id === state.activeConversationId) ||
      state.conversations[0],
    [state.conversations, state.activeConversationId],
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', state.preferences.theme)
  }, [state.preferences.theme])

  useEffect(() => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
      } catch {
        /* quota exceeded — keep in memory only */
      }
    }, 280)
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
    }
  }, [state])

  const setPreference = useCallback((key, value) => {
    setState((prev) => ({
      ...prev,
      preferences: { ...prev.preferences, [key]: value },
    }))
  }, [])

  const selectConversation = useCallback((id) => {
    setState((prev) => ({ ...prev, activeConversationId: id }))
  }, [])

  const newConversation = useCallback(() => {
    const conv = createConversation(true)
    setState((prev) => ({
      ...prev,
      activeConversationId: conv.id,
      conversations: [conv, ...prev.conversations],
    }))
    return conv.id
  }, [])

  const deleteConversation = useCallback((id) => {
    setState((prev) => {
      let conversations = prev.conversations.filter((c) => c.id !== id)
      if (conversations.length === 0) {
        const conv = createConversation(true)
        conversations = [conv]
        return { ...prev, conversations, activeConversationId: conv.id }
      }
      const activeConversationId =
        prev.activeConversationId === id ? conversations[0].id : prev.activeConversationId
      return { ...prev, conversations, activeConversationId }
    })
  }, [])

  const clearActiveConversation = useCallback(() => {
    setState((prev) => {
      const ts = nowIso()
      const conversations = prev.conversations.map((c) => {
        if (c.id !== prev.activeConversationId) return c
        return {
          ...c,
          title: 'Nouvelle conversation',
          updatedAt: ts,
          messages: [{ id: newId(), ...WELCOME_MESSAGE, createdAt: ts }],
        }
      })
      return { ...prev, conversations }
    })
  }, [])

  const appendMessages = useCallback((incoming) => {
    setState((prev) => {
      const activeId = prev.activeConversationId
      const ts = nowIso()
      const conversations = prev.conversations.map((c) => {
        if (c.id !== activeId) return c
        const nextMessages = [
          ...c.messages,
          ...incoming.map((m) => ({
            id: newId(),
            role: m.role,
            content: m.content,
            createdAt: ts,
            mode: m.mode,
            displayFormat: m.displayFormat,
            feedbackRating: m.feedbackRating,
          })),
        ]
        const firstUser = incoming.find((m) => m.role === 'user')
        const title =
          c.title === 'Nouvelle conversation' && firstUser
            ? titleFromMessage(firstUser.content)
            : c.title
        return {
          ...c,
          title,
          updatedAt: ts,
          messages: nextMessages,
        }
      })
      return { ...prev, conversations }
    })
  }, [])

  const setMessageFeedback = useCallback((messageId, rating) => {
    setState((prev) => ({
      ...prev,
      conversations: prev.conversations.map((c) => ({
        ...c,
        messages: c.messages.map((m) =>
          m.id === messageId ? { ...m, feedbackRating: rating } : m,
        ),
      })),
    }))
  }, [])

  const clearAllHistory = useCallback(() => {
    const conv = createConversation(true)
    setState((prev) => ({
      ...prev,
      activeConversationId: conv.id,
      conversations: [conv],
    }))
  }, [])

  return {
    preferences: state.preferences,
    setPreference,
    conversations: state.conversations,
    activeConversation,
    selectConversation,
    newConversation,
    deleteConversation,
    clearActiveConversation,
    clearAllHistory,
    appendMessages,
    setMessageFeedback,
  }
}
