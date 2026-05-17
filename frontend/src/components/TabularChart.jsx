import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const CHART_COLORS = {
  bar: '#7c3aed',
  line: '#22d3ee',
  grid: '#2b3a56',
  axis: '#93a4bf',
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  return (
    <div className="chart-tooltip">
      <strong>{row?.fullName ?? label}</strong>
      <span>{payload[0].value}</span>
    </div>
  )
}

export function TabularChart({ spec }) {
  if (!spec?.data?.length) return null

  const { chartType, data, valueKey } = spec
  const height = Math.min(420, Math.max(220, data.length * 28))

  if (chartType === 'line') {
    return (
      <div className="chart-wrap" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 48 }}>
            <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
              angle={data.length > 6 ? -35 : 0}
              textAnchor={data.length > 6 ? 'end' : 'middle'}
              height={data.length > 6 ? 64 : 32}
              interval={data.length > 20 ? Math.floor(data.length / 12) : 0}
            />
            <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} width={56} />
            <Tooltip content={<ChartTooltip />} />
            <Line
              type="monotone"
              dataKey="value"
              name={valueKey}
              stroke={CHART_COLORS.line}
              strokeWidth={2}
              dot={{ r: 3, fill: CHART_COLORS.line }}
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
          <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
            angle={data.length > 4 ? -30 : 0}
            textAnchor={data.length > 4 ? 'end' : 'middle'}
            height={data.length > 4 ? 60 : 32}
            interval={0}
          />
          <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 11 }} width={56} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(124, 58, 237, 0.12)' }} />
          <Bar dataKey="value" name={valueKey} fill={CHART_COLORS.bar} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
