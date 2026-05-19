/**
 * Extract tabular blocks from assistant answer text (markdown, pipe, ASCII series, numbered lists).
 */

const MARKDOWN_ROW = /^\s*\|(.+)\|\s*$/
const MARKDOWN_SEP = /^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/
const PIPE_ROW = /^.+\u2502.+$/
const PIPE_SEP = /^[-+\u2500\u2502\s]+$/
const ASCII_SERIES =
  /^\s*(.+?)\s*\u2502\s*[#\u00b7.\s]+\s+(-?[\d.,]+(?:e[-+]?\d+)?)\s*$/i
const NUMBERED_METRIC =
  /^\s*\d+\.\s+(.+?)\s*:\s*([\d.,\s]+)\s*(€|unité\(s\)|unités?)?\s*$/i

export function parseNumeric(value) {
  if (value == null) return null
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const cleaned = String(value)
    .replace(/\u20ac/g, '')
    .replace(/\s/g, '')
    .replace(/,/g, '.')
    .replace(/[^\d.-]/g, '')
  if (!cleaned || cleaned === '-' || cleaned === '.') return null
  const n = Number(cleaned)
  return Number.isFinite(n) ? n : null
}

function splitPipeCells(line) {
  return line
    .split('\u2502')
    .map((c) => c.trim())
    .filter((c, i, arr) => !(i === 0 && c === '') && !(i === arr.length - 1 && c === ''))
}

function splitMarkdownCells(line) {
  return line
    .replace(/^\s*\|/, '')
    .replace(/\|\s*$/, '')
    .split('|')
    .map((c) => c.trim())
}

function looksLikeDate(value) {
  const s = String(value).trim()
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return true
  if (/^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}/.test(s)) return true
  return false
}

function numericColumnIndices(headers, rows) {
  const indices = []
  for (let col = 0; col < headers.length; col += 1) {
    let numericCount = 0
    for (const row of rows) {
      if (parseNumeric(row[col]) != null) numericCount += 1
    }
    if (numericCount > 0 && numericCount >= Math.ceil(rows.length * 0.5)) {
      indices.push(col)
    }
  }
  return indices
}

function labelColumnIndex(headers, numericCols) {
  const nonNumeric = headers.map((_, i) => i).filter((i) => !numericCols.includes(i))
  if (nonNumeric.length === 0) return 0
  const rankCol = headers.findIndex((h) => /^#$/i.test(String(h).trim()))
  if (rankCol >= 0 && nonNumeric.includes(rankCol)) {
    const other = nonNumeric.find((i) => i !== rankCol)
    return other ?? rankCol
  }
  return nonNumeric[0]
}

export function chartSpecFromTable(headers, rows) {
  if (!headers?.length || !rows?.length) return null

  const numericCols = numericColumnIndices(headers, rows)
  if (numericCols.length === 0) return null

  const labelCol = labelColumnIndex(headers, numericCols)
  const valueCol = numericCols[numericCols.length - 1]
  const labels = rows.map((r) => String(r[labelCol] ?? ''))
  const values = rows.map((r) => parseNumeric(r[valueCol]) ?? 0)
  const dateLike =
    labels.length > 0 && labels.filter(looksLikeDate).length >= Math.ceil(labels.length * 0.6)
  const chartType =
    dateLike && rows.length >= 3 ? 'line' : rows.length > 12 ? 'line' : 'bar'

  return {
    chartType,
    labelKey: headers[labelCol],
    valueKey: headers[valueCol],
    data: labels.map((name, i) => ({
      name: name.length > 24 ? `${name.slice(0, 22)}…` : name,
      fullName: name,
      value: values[i],
    })),
  }
}

function parseMarkdownBlock(lines, start) {
  const headerCells = splitMarkdownCells(lines[start])
  if (headerCells.length < 2) return null
  if (!MARKDOWN_SEP.test(lines[start + 1] || '')) return null

  const rows = []
  let i = start + 2
  while (i < lines.length && MARKDOWN_ROW.test(lines[i])) {
    rows.push(splitMarkdownCells(lines[i]))
    i += 1
  }
  if (rows.length === 0) return null
  return { kind: 'markdown', headers: headerCells, rows, end: i }
}

function parsePipeBlock(lines, start) {
  if (!PIPE_ROW.test(lines[start])) return null
  if (!PIPE_SEP.test(lines[start + 1] || '')) return null

  const headers = splitPipeCells(lines[start])
  const rows = []
  let i = start + 2
  while (i < lines.length && PIPE_ROW.test(lines[i]) && !PIPE_SEP.test(lines[i])) {
    rows.push(splitPipeCells(lines[i]))
    i += 1
  }
  if (rows.length === 0) return null
  return { kind: 'pipe', headers, rows, end: i }
}

function parseAsciiSeriesBlock(lines, start) {
  const rows = []
  let i = start
  while (i < lines.length && ASCII_SERIES.test(lines[i])) {
    const m = lines[i].match(ASCII_SERIES)
    if (!m) break
    rows.push([m[1].trim(), m[2].trim()])
    i += 1
  }
  if (rows.length < 2) return null
  return {
    kind: 'ascii-series',
    headers: ['Période', 'Valeur'],
    rows,
    end: i,
  }
}

/** Convert "1. Paris : 1234.56 €" blocks into a table (legacy answers). */
function parseNumberedMetricBlock(lines, start) {
  if (!NUMBERED_METRIC.test(lines[start])) return null
  const rows = []
  let i = start
  while (i < lines.length && NUMBERED_METRIC.test(lines[i])) {
    const m = lines[i].match(NUMBERED_METRIC)
    if (!m) break
    rows.push([m[1].trim(), m[2].trim()])
    i += 1
  }
  if (rows.length < 2) return null
  return {
    kind: 'numbered',
    headers: ['Libellé', 'Valeur'],
    rows,
    end: i,
  }
}

/**
 * @returns {{ blocks: Array<{headers: string[], rows: string[][]}>, segments: Array<{type: 'text'|'table', text?: string, blockIndex?: number}> }}
 */
export function parseAnswerContent(content) {
  if (!content || typeof content !== 'string') {
    return { blocks: [], segments: [{ type: 'text', text: '' }] }
  }

  const lines = content.split('\n')
  const blocks = []
  const segments = []
  let textStart = 0
  let lineIdx = 0

  function flushText(untilLine) {
    if (untilLine <= textStart) return
    const text = lines.slice(textStart, untilLine).join('\n')
    if (text.trim()) {
      segments.push({ type: 'text', text })
    }
  }

  while (lineIdx < lines.length) {
    const md = parseMarkdownBlock(lines, lineIdx)
    const pipe = md ? null : parsePipeBlock(lines, lineIdx)
    const ascii = md || pipe ? null : parseAsciiSeriesBlock(lines, lineIdx)
    const numbered = md || pipe || ascii ? null : parseNumberedMetricBlock(lines, lineIdx)

    const parsed = md || pipe || ascii || numbered
    if (!parsed) {
      lineIdx += 1
      continue
    }

    flushText(lineIdx)
    const blockIndex = blocks.length
    blocks.push({
      kind: parsed.kind,
      headers: parsed.headers,
      rows: parsed.rows,
    })
    segments.push({ type: 'table', blockIndex })
    lineIdx = parsed.end
    textStart = lineIdx
  }

  flushText(lines.length)
  if (segments.length === 0) {
    segments.push({ type: 'text', text: content })
  }

  return { blocks, segments }
}
