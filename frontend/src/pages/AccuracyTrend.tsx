import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine,
} from 'recharts'
import { getAccuracyTrend } from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'
import QueryError from '../components/QueryError'
import { CPL_EXPLANATION } from '../lib/explanations'
import { useTimeRange } from '../lib/useTimeRange'

export default function AccuracyTrend() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useTimeRange()

  const query = useQuery({
    queryKey: ['accuracyTrend', id, range],
    queryFn: () => getAccuracyTrend(id!, undefined, range),
    enabled: !!id,
  })

  const data = query.data ?? []

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
  if (query.isError) return <QueryError error={query.error} />


  const withRolling = data.map((d, i) => {
    const window = data.slice(Math.max(0, i - 19), i + 1)
    const avg = window.reduce((s, p) => s + p.accuracy, 0) / window.length
    return { ...d, rollingAccuracy: Math.round(avg * 10) / 10, date: d.played_at?.slice(0, 10) }
  })

  const avgAccuracy = data.length > 0
    ? Math.round(data.reduce((s, d) => s + d.accuracy, 0) / data.length * 10) / 10
    : 0
  const avgCpl = data.length > 0
    ? Math.round(data.reduce((s, d) => s + d.avg_cpl, 0) / data.length * 10) / 10
    : 0

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        ♛ Accuracy Trend
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        Your accuracy over time. Higher is better. The line shows a 20-game rolling average.
      </p>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Range
        </span>
        <TimeRangeFilter value={range} onChange={setRange} />
        <span className="ml-auto text-xs inline-flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
          How is accuracy calculated?
          <InfoTip>
            Each move is scored 0-100 based on how much win probability you gave up vs
            the engine's best line. The game's accuracy is the mean of those per-move scores.
            Same formula as chess.com / Lichess.
          </InfoTip>
        </span>
      </div>

      {data.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>No analyzed games in this range yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard
              label="Average accuracy"
              value={`${avgAccuracy}%`}
              info="Mean of per-game accuracy in this range."
            />
            <StatCard
              label="Best game"
              value={`${Math.max(...data.map(d => d.accuracy))}%`}
              info="Highest single-game accuracy."
            />
            <StatCard
              label="Average CPL"
              value={`${avgCpl}`}
              info={CPL_EXPLANATION}
            />
            <StatCard label="Games" value={data.length} info="Games analyzed in this range." />
          </div>

          <div
            className="rounded-lg p-4 border"
            style={{ background: 'var(--bg-card)', borderColor: 'var(--border)', height: 400 }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={withRolling}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--chart-axis)', fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis domain={[0, 100]} tick={{ fill: 'var(--chart-axis)' }} />
                <ReferenceLine y={avgAccuracy} stroke="#6366f1" strokeDasharray="5 5" />
                <Tooltip
                  contentStyle={{
                    background: 'var(--tooltip-bg)',
                    border: '1px solid var(--tooltip-border)',
                    color: 'var(--text-primary)',
                  }}
                  formatter={(v, name) => [
                    `${v}%`,
                    name === 'rollingAccuracy' ? 'Rolling Avg' : 'Game Accuracy',
                  ]}
                />
                <Line type="monotone" dataKey="accuracy" stroke="#4b556340" dot={false} strokeWidth={1} />
                <Line type="monotone" dataKey="rollingAccuracy" stroke="#818cf8" dot={false} strokeWidth={2.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, info }: { label: string; value: string | number; info?: React.ReactNode }) {
  return (
    <div
      className="rounded-lg p-4 border"
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
    >
      <p className="text-sm inline-flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
        {label}
        {info && <InfoTip label={label}>{info}</InfoTip>}
      </p>
      <p className="text-2xl font-bold text-indigo-400">{value}</p>
    </div>
  )
}
