import { useMemo } from 'react'
import { chartSpecFromTable, parseAnswerContent } from '../utils/parseTabularBlocks'
import { shouldShowChart, shouldEmphasizeTable } from '../utils/outputFormat'
import { TabularChart } from './TabularChart'

const CHART_LABELS = {
  bar: 'Barres',
  line: 'Courbe',
  pie: 'Secteurs',
}

function formatCell(value) {
  if (value == null || value === '') return '—'
  const raw = String(value).trim()
  const cleaned = raw.replace(/\s/g, '').replace(/,/g, '.').replace(/[^\d.-]/g, '')
  const n = Number(cleaned)
  if (Number.isFinite(n) && /^[\d.,\s€-]+$/.test(raw)) {
    return n.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
  }
  return raw
}

function isNumericCell(value) {
  if (value == null) return false
  const cleaned = String(value).replace(/\s/g, '').replace(/,/g, '.').replace(/[^\d.-]/g, '')
  return cleaned.length > 0 && Number.isFinite(Number(cleaned))
}

function DataTable({ headers, rows, emphasized }) {
  return (
    <div className={`table-scroll${emphasized ? ' table-scroll--emphasized' : ''}`}>
      <table className="data-table">
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th key={`${h}-${i}`} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {headers.map((_, ci) => (
                <td key={ci} data-numeric={isNumericCell(row[ci]) ? 'true' : undefined}>
                  {formatCell(row[ci])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function getFirstChartContainerId(messageId, content) {
  if (!messageId || !content) return null
  const { blocks, segments } = parseAnswerContent(content)
  for (const segment of segments) {
    if (segment.type !== 'table') continue
    const block = blocks[segment.blockIndex]
    if (!block) continue
    if (chartSpecFromTable(block.headers, block.rows)) {
      return `chart-${messageId}-${segment.blockIndex}`
    }
  }
  return null
}

export function MessageContent({ content, chartType, messageId, displayMode = 'auto' }) {
  const parsed = useMemo(() => parseAnswerContent(content), [content])
  const { blocks, segments } = parsed
  const hasTable = blocks.length > 0

  return (
    <div className="message-content">
      {segments.map((segment, index) => {
        if (segment.type === 'text') {
          const paragraphs = segment.text.split(/\n{2,}/).filter(Boolean)
          return (
            <div key={`t-${index}`} className="text-block">
              {paragraphs.map((para, pi) => (
                <p key={pi} className="text-segment">
                  {para}
                </p>
              ))}
            </div>
          )
        }

        const block = blocks[segment.blockIndex]
        if (!block) return null

        const chartSpec = chartSpecFromTable(block.headers, block.rows)
        const showChart = shouldShowChart(displayMode, Boolean(chartSpec))
        const emphasizeTable = shouldEmphasizeTable(displayMode, true)
        const chartContainerId =
          chartSpec && messageId ? `chart-${messageId}-${segment.blockIndex}` : null

        return (
          <div
            key={`tbl-${index}`}
            className={`tabular-block${emphasizeTable ? ' tabular-block--table-mode' : ''}`}
          >
            <div className="tabular-block-header">
              <span className="tabular-badge">Tableau</span>
              <span className="tabular-meta">
                {block.rows.length} ligne{block.rows.length > 1 ? 's' : ''}
              </span>
            </div>
            <DataTable headers={block.headers} rows={block.rows} emphasized={emphasizeTable} />
            {showChart && chartSpec ? (
              <>
                <p className="chart-caption">
                  {CHART_LABELS[chartType] || 'Graphique'} — {chartSpec.valueKey}
                </p>
                <div id={chartContainerId || undefined} className="chart-export-root">
                  <TabularChart spec={chartSpec} chartType={chartType} />
                </div>
              </>
            ) : displayMode === 'chart' && !chartSpec ? (
              <p className="chart-caption muted">
                Données non graphables — affichage tableau uniquement.
              </p>
            ) : null}
          </div>
        )
      })}
      {!hasTable && displayMode === 'table' ? (
        <p className="chart-caption muted">Aucun tableau détecté dans cette réponse.</p>
      ) : null}
    </div>
  )
}
