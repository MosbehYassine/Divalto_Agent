import { useState } from 'react'
import {
  copyTablesFromContent,
  copyTextToClipboard,
  downloadCsvFromContent,
  exportChartPngFromElement,
  openAnswerAsPdfPrint,
  tablesFromContent,
} from '../utils/exportAnswer'

export function AssistantMessageToolbar({
  messageId,
  content,
  userQuery,
  conversationId,
  mode,
  chartType,
  realPlanner,
  apiBaseUrl,
  feedbackRating,
  onFeedback,
  chartContainerId,
}) {
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const hasTables = tablesFromContent(content).length > 0

  function flash(msg) {
    setStatus(msg)
    setTimeout(() => setStatus(''), 2500)
  }

  async function run(action) {
    if (busy) return
    setBusy(true)
    try {
      await action()
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Erreur export')
    } finally {
      setBusy(false)
    }
  }

  async function submitFeedback(rating) {
    if (feedbackRating || busy) return
    setBusy(true)
    try {
      const res = await fetch(`${apiBaseUrl}/api/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rating,
          user_query: userQuery || '',
          assistant_answer: content,
          mode,
          conversation_id: conversationId,
          message_id: messageId,
          chart_type: chartType,
          real_planner: realPlanner,
        }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(payload?.detail || 'Enregistrement feedback échoué')
      }
      onFeedback?.(messageId, rating)
      flash(rating === 'up' ? 'Merci — feedback enregistré' : 'Feedback enregistré — nous améliorerons')
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Feedback impossible')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="message-toolbar">
      <div className="toolbar-actions" role="toolbar" aria-label="Actions sur la réponse">
        <button
          type="button"
          className="toolbar-btn"
          disabled={busy}
          onClick={() =>
            run(async () => {
              await copyTextToClipboard(content)
              flash('Réponse copiée')
            })
          }
        >
          Copier
        </button>
        <button
          type="button"
          className="toolbar-btn"
          disabled={busy}
          onClick={() =>
            run(async () => {
              const kind = await copyTablesFromContent(content)
              flash(kind === 'tables' ? 'Tableau(x) copié(s)' : 'Réponse copiée')
            })
          }
        >
          {hasTables ? 'Copier tableau' : 'Copier tout'}
        </button>
        <button
          type="button"
          className="toolbar-btn"
          disabled={busy}
          onClick={() =>
            run(async () => {
              const kind = downloadCsvFromContent(content)
              flash(kind === 'csv' ? 'CSV téléchargé' : 'Texte téléchargé (pas de tableau)')
            })
          }
        >
          CSV
        </button>
        <button
          type="button"
          className="toolbar-btn"
          disabled={busy}
          onClick={() =>
            run(async () => {
              openAnswerAsPdfPrint(content, 'Divalto Agent — Réponse')
              flash('Fenêtre PDF — choisir « Enregistrer en PDF »')
            })
          }
        >
          PDF
        </button>
        {chartContainerId ? (
          <button
            type="button"
            className="toolbar-btn"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const el = document.getElementById(chartContainerId)
                await exportChartPngFromElement(el, `graphique-${messageId.slice(0, 8)}.png`)
                flash('PNG du graphique téléchargé')
              })
            }
          >
            PNG graphique
          </button>
        ) : null}
        <span className="toolbar-sep" aria-hidden />
        <button
          type="button"
          className={`toolbar-btn feedback-btn ${feedbackRating === 'up' ? 'active' : ''}`}
          disabled={busy || Boolean(feedbackRating)}
          onClick={() => submitFeedback('up')}
          aria-pressed={feedbackRating === 'up'}
          title="Bonne réponse"
        >
          👍
        </button>
        <button
          type="button"
          className={`toolbar-btn feedback-btn ${feedbackRating === 'down' ? 'active' : ''}`}
          disabled={busy || Boolean(feedbackRating)}
          onClick={() => submitFeedback('down')}
          aria-pressed={feedbackRating === 'down'}
          title="Réponse à améliorer"
        >
          👎
        </button>
      </div>
      {status ? <p className="toolbar-status">{status}</p> : null}
    </div>
  )
}
