import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const PIE_COLORS = ['#8b5cf6', '#22d3ee', '#6366f1', '#14b8a6', '#f59e0b', '#ec4899', '#84cc16']

function chartColors() {
  if (typeof document === 'undefined') {
    return { primary: '#8b5cf6', secondary: '#22d3ee', grid: '#334155', axis: '#94a3b8' }
  }
  const s = getComputedStyle(document.documentElement)
  return {
    primary: s.getPropertyValue('--chart-1').trim() || '#8b5cf6',
    secondary: s.getPropertyValue('--chart-2').trim() || '#22d3ee',
    grid: s.getPropertyValue('--chart-grid').trim() || '#334155',
    axis: s.getPropertyValue('--chart-axis').trim() || '#94a3b8',
  }
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  return (
    <div className="chart-tooltip">
      <strong>{row?.fullName ?? label}</strong>
      <span>{Number(payload[0].value).toLocaleString('fr-FR')}</span>
    </div>
  )
}

export function TabularChart({ spec, chartType = 'bar' }) {
  const colors = useMemo(chartColors, [])
  const data = spec?.data ?? []
  if (!data.length) return null

  const height = Math.min(420, Math.max(240, data.length * 28))
  const pieData = data.length > 12 ? data.slice(0, 12) : data
  const pieNote = data.length > 12 ? ` (12 premières valeurs sur ${data.length})` : ''

  if (chartType === 'pie') {
    return (
      <div className="chart-wrap chart-wrap--pie">
        {pieNote ? <p className="chart-hint">{pieNote}</p> : null}
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={52}
              outerRadius={96}
              paddingAngle={2}
            >
              {pieData.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (chartType === 'line') {
    return (
      <div className="chart-wrap" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 48 }}>
            <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: colors.axis, fontSize: 11 }}
              angle={data.length > 6 ? -35 : 0}
              textAnchor={data.length > 6 ? 'end' : 'middle'}
              height={data.length > 6 ? 64 : 32}
              interval={data.length > 20 ? Math.floor(data.length / 12) : 0}
            />
            <YAxis tick={{ fill: colors.axis, fontSize: 11 }} width={56} />
            <Tooltip content={<ChartTooltip />} />
            <Line
              type="monotone"
              dataKey="value"
              name={spec.valueKey}
              stroke={colors.secondary}
              strokeWidth={2}
              dot={{ r: 3, fill: colors.secondary }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    )
  }

  return (
    <div className="chart-wrap" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 48 }}>
          <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: colors.axis, fontSize: 11 }}
            angle={data.length > 4 ? -30 : 0}
            textAnchor={data.length > 4 ? 'end' : 'middle'}
            height={data.length > 4 ? 60 : 32}
            interval={0}
          />
          <YAxis tick={{ fill: colors.axis, fontSize: 11 }} width={56} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--accent-soft)' }} />
          <Bar dataKey="value" name={spec.valueKey} fill={colors.primary} radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
