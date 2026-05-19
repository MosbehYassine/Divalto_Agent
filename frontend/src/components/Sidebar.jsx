import { useMemo, useState } from 'react'
import { formatMessageTime } from '../utils/formatTime'

function truncate(text, max) {
  const t = (text || '').trim().replace(/\s+/g, ' ')
  if (!t) return ''
  return t.length > max ? `${t.slice(0, max)}…` : t
}

export function Sidebar({
  apiBaseUrl,
  conversations,
  activeConversationId,
  collapsed,
  onToggleCollapse,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onClearHistory,
}) {
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return conversations
    return conversations.filter((conv) => {
      const title = (conv.title || '').toLowerCase()
      const preview = [...conv.messages]
        .reverse()
        .find((m) => m.role === 'user')
      const body = (preview?.content || '').toLowerCase()
      return title.includes(q) || body.includes(q)
    })
  }, [conversations, filter])

  return (
    <aside className={`sidebar${collapsed ? ' sidebar--collapsed' : ''}`}>
      <div className="sidebar-top">
        <div className="brand">
          <div className="brand-mark" aria-hidden>
            D
          </div>
          {!collapsed ? (
            <div className="brand-text">
              <h1>Divalto Agent</h1>
              <p>Assistant analytique · Projet 4</p>
            </div>
          ) : null}
        </div>
        <button
          type="button"
          className="sidebar-toggle"
          onClick={onToggleCollapse}
          aria-label={collapsed ? 'Déplier le menu' : 'Replier le menu'}
          title={collapsed ? 'Déplier' : 'Replier'}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      <button
        type="button"
        className="btn-primary btn-new-chat"
        onClick={onNewConversation}
        title="Nouvelle conversation"
      >
        {collapsed ? '+' : '+ Nouvelle conversation'}
      </button>

      {!collapsed ? (
        <>
          <div className="sidebar-section sidebar-section--history">
            <div className="sidebar-section-head">
              <h2 className="sidebar-label">Historique</h2>
              <span className="sidebar-count">{conversations.length}</span>
            </div>
            <p className="sidebar-hint">Enregistré localement sur cet appareil</p>

            <label className="sidebar-search">
              <span className="visually-hidden">Rechercher</span>
              <input
                type="search"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Rechercher une conversation…"
                autoComplete="off"
              />
            </label>

            <ul className="conversation-list" role="list">
              {filtered.length === 0 ? (
                <li className="conversation-empty">Aucune conversation trouvée</li>
              ) : (
                filtered.map((conv) => {
                  const active = conv.id === activeConversationId
                  const lastUser = [...conv.messages].reverse().find((m) => m.role === 'user')
                  const preview = truncate(lastUser?.content || conv.messages.at(-1)?.content, 52)
                  return (
                    <li
                      key={conv.id}
                      className={active ? 'conversation-item active' : 'conversation-item'}
                    >
                      <button
                        type="button"
                        className="conversation-btn"
                        onClick={() => onSelectConversation(conv.id)}
                        title={conv.title}
                      >
                        <span className="conversation-title">{conv.title}</span>
                        {preview ? (
                          <span className="conversation-preview">{preview}</span>
                        ) : null}
                        <span className="conversation-meta">
                          {formatMessageTime(conv.updatedAt)}
                        </span>
                      </button>
                      {conversations.length > 1 ? (
                        <button
                          type="button"
                          className="conversation-delete"
                          aria-label="Supprimer la conversation"
                          onClick={() => onDeleteConversation(conv.id)}
                        >
                          ×
                        </button>
                      ) : null}
                    </li>
                  )
                })
              )}
            </ul>

            <button type="button" className="btn-ghost btn-sm btn-clear-history" onClick={onClearHistory}>
              Effacer tout l&apos;historique
            </button>
          </div>

          <div className="status-card">
            <div className="status-card-row">
              <span className="status-dot" aria-hidden />
              <p className="status-card-label">API connectée</p>
            </div>
            <code className="status-card-url">{apiBaseUrl}</code>
          </div>
        </>
      ) : null}
    </aside>
  )
}
