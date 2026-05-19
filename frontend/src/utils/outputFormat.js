/**
 * Resolve how assistant answers should be rendered (table vs chart).
 * Priority: explicit user message > saved preference > auto.
 */

const TABLE_HINTS = [
  'tableau',
  'en table',
  'sous forme de table',
  'format table',
  'tabulaire',
  'in table',
  'as a table',
  'as table',
  'table format',
  'afficher en tableau',
  'présente en tableau',
  'presente en tableau',
]

const CHART_HINTS = [
  'graphique',
  'chart',
  'courbe',
  'diagramme',
  'histogramme',
  'camembert',
  'en graph',
  'barres',
]

export function detectFormatFromQuery(query) {
  if (!query || typeof query !== 'string') return null
  const q = query.toLowerCase()
  if (TABLE_HINTS.some((h) => q.includes(h))) return 'table'
  if (CHART_HINTS.some((h) => q.includes(h))) return 'chart'
  return null
}

/**
 * @param {'auto'|'table'|'chart'} preference
 * @param {string|null} queryHint from detectFormatFromQuery
 */
export function resolveDisplayMode(preference, queryHint) {
  if (queryHint === 'table' || queryHint === 'chart') return queryHint
  if (preference === 'table' || preference === 'chart') return preference
  return 'auto'
}

export function shouldShowChart(displayMode, hasChartableTable) {
  if (displayMode === 'table') return false
  if (displayMode === 'chart') return hasChartableTable
  return false
}

export function shouldEmphasizeTable(displayMode, hasTable) {
  if (!hasTable) return false
  return displayMode === 'table' || displayMode === 'auto'
}
