import { useMemo } from 'react'
import { chartSpecFromTable, parseAnswerContent } from '../utils/parseTabularBlocks'
import { TabularChart } from './TabularChart'

function DataTable({ headers, rows }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {headers.map((_, ci) => (
                <td key={ci}>{row[ci] ?? ''}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function MessageContent({ content }) {
  const parsed = useMemo(() => parseAnswerContent(content), [content])
  const { blocks, segments } = parsed

  return (
    <div className="message-content">
      {segments.map((segment, index) => {
        if (segment.type === 'text') {
          return (
            <p key={`t-${index}`} className="text-segment">
              {segment.text}
            </p>
          )
        }

        const block = blocks[segment.blockIndex]
        if (!block) return null

        const chartSpec = chartSpecFromTable(block.headers, block.rows)

        return (
          <div key={`tbl-${index}`} className="tabular-block">
            <DataTable headers={block.headers} rows={block.rows} />
            {chartSpec ? (
              <>
                <p className="chart-caption">
                  {chartSpec.chartType === 'line' ? 'Évolution' : 'Comparaison'} — {chartSpec.valueKey}
                </p>
                <TabularChart spec={chartSpec} />
              </>
            ) : (
              <p className="chart-caption muted">Tableau sans colonne numérique pour graphique.</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
