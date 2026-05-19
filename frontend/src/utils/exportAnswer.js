import { parseAnswerContent } from './parseTabularBlocks'

function escapeCsvCell(value) {
  const s = String(value ?? '')
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`
  }
  return s
}

export function tablesFromContent(content) {
  const { blocks } = parseAnswerContent(content)
  return blocks
}

export function tableToTsv(headers, rows) {
  const lines = [headers.join('\t'), ...rows.map((r) => headers.map((_, i) => r[i] ?? '').join('\t'))]
  return lines.join('\n')
}

export function tableToCsv(headers, rows) {
  const lines = [
    headers.map(escapeCsvCell).join(','),
    ...rows.map((r) => headers.map((_, i) => escapeCsvCell(r[i])).join(',')),
  ]
  return lines.join('\n')
}

export function allTablesCsv(content) {
  const blocks = tablesFromContent(content)
  if (!blocks.length) return null
  return blocks
    .map((b, i) => {
      const head = blocks.length > 1 ? `# Table ${i + 1}\n` : ''
      return head + tableToCsv(b.headers, b.rows)
    })
    .join('\n\n')
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function downloadTextFile(text, filename, mime = 'text/plain;charset=utf-8') {
  downloadBlob(new Blob([text], { type: mime }), filename)
}

export function downloadCsvFromContent(content, filename = 'divalto-export.csv') {
  const csv = allTablesCsv(content)
  if (!csv) {
    downloadTextFile(content, 'divalto-reponse.txt')
    return 'text'
  }
  downloadTextFile(csv, filename, 'text/csv;charset=utf-8')
  return 'csv'
}

export async function copyTextToClipboard(text) {
  await navigator.clipboard.writeText(text)
}

export async function copyTablesFromContent(content) {
  const blocks = tablesFromContent(content)
  if (!blocks.length) {
    await copyTextToClipboard(content)
    return 'answer'
  }
  const tsv = blocks
    .map((b, i) => {
      const head = blocks.length > 1 ? `Table ${i + 1}\n` : ''
      return head + tableToTsv(b.headers, b.rows)
    })
    .join('\n\n')
  await copyTextToClipboard(tsv)
  return 'tables'
}

export function openAnswerAsPdfPrint(content, title = 'Divalto Agent') {
  const blocks = tablesFromContent(content)
  const tableHtml = blocks
    .map(
      (b, i) => `
    <h3>Tableau ${blocks.length > 1 ? i + 1 : ''}</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:12px;">
      <thead><tr>${b.headers.map((h) => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
      <tbody>
        ${b.rows.map((row) => `<tr>${row.map((c) => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('')}
      </tbody>
    </table>`,
    )
    .join('')

  const html = `<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"/><title>${escapeHtml(title)}</title>
<style>
  body { font-family: Segoe UI, sans-serif; padding: 24px; color: #111; }
  pre { white-space: pre-wrap; font-size: 13px; line-height: 1.5; }
  h1 { font-size: 18px; } h3 { margin-top: 20px; }
  th { background: #f1f5f9; text-align: left; }
</style></head><body>
  <h1>${escapeHtml(title)}</h1>
  <p style="color:#64748b;font-size:12px;">Exporté depuis Divalto Agent — ${new Date().toLocaleString('fr-FR')}</p>
  <pre>${escapeHtml(content)}</pre>
  ${tableHtml}
</body></html>`

  const win = window.open('', '_blank', 'noopener,noreferrer')
  if (!win) {
    throw new Error('Popup bloquée — autorisez les fenêtres pour exporter en PDF.')
  }
  win.document.write(html)
  win.document.close()
  win.focus()
  setTimeout(() => win.print(), 400)
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export async function exportChartPngFromElement(chartRoot, filename = 'graphique.png') {
  if (!chartRoot) throw new Error('Graphique introuvable.')
  const svg = chartRoot.querySelector('svg.recharts-surface') || chartRoot.querySelector('svg')
  if (!svg) throw new Error('SVG du graphique introuvable.')

  const cloned = svg.cloneNode(true)
  const box = svg.getBoundingClientRect()
  const w = Math.max(1, Math.round(box.width || 800))
  const h = Math.max(1, Math.round(box.height || 320))
  cloned.setAttribute('width', String(w))
  cloned.setAttribute('height', String(h))

  const bg =
    getComputedStyle(document.documentElement).getPropertyValue('--bg-surface').trim() || '#ffffff'
  const svgData = new XMLSerializer().serializeToString(cloned)
  const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(svgBlob)

  await new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d')
        ctx.fillStyle = bg
        ctx.fillRect(0, 0, w, h)
        ctx.drawImage(img, 0, 0)
        canvas.toBlob((blob) => {
          URL.revokeObjectURL(url)
          if (!blob) {
            reject(new Error('Export PNG impossible.'))
            return
          }
          downloadBlob(blob, filename)
          resolve()
        }, 'image/png')
      } catch (err) {
        URL.revokeObjectURL(url)
        reject(err)
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Chargement SVG échoué.'))
    }
    img.src = url
  })
}
