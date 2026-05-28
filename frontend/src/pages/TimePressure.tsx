import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { getTimePressure, type TimeRange } from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'
import QueryError from '../components/QueryError'
import { CPL_EXPLANATION } from '../lib/explanations'

const TIME_CLASSES = ['bullet', 'blitz', 'rapid', 'classical']

export default function TimePressure() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<TimeRange>('all')
  const [timeClass, setTimeClass] = useState<string>('blitz')

  const query = useQuery({
    queryKey: ['timePressure', id, timeClass, range],
    queryFn: () => getTimePressure(id!, timeClass, range),
    enabled: !!id,
  })

  const data = query.data ?? []

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
  if (query.isError) return <QueryError error={query.error} />


  const chartData = data.map((d) => ({
    bucket: d.bucket,
    'Avg CPL': Number(d.avg_cpl.toFixed(1)),
    'Blunder %': Number((d.blunder_rate * 100).toFixed(1)),
    'Sample Size': d.sample_size,
  }))

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        Time Pressure
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        How your play degrades as the clock runs down, bucketed by clock remaining when you moved.
      </p>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Range
        </span>
        <TimeRangeFilter value={range} onChange={setRange} />
        <span className="text-xs uppercase tracking-wide ml-2" style={{ color: 'var(--text-muted)' }}>
          Time class
        </span>
        <select
          value={timeClass}
          onChange={(e) => setTimeClass(e.target.value)}
          className="px-2 py-1 text-xs rounded-md border"
          style={{
            background: 'var(--bg-card)',
            borderColor: 'var(--border)',
            color: 'var(--text-primary)',
          }}
        >
          {TIME_CLASSES.map((tc) => (
            <option key={tc} value={tc}>{tc}</option>
          ))}
        </select>
        <span className="ml-auto text-xs inline-flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
          What is CPL?
          <InfoTip>{CPL_EXPLANATION}</InfoTip>
        </span>
      </div>

      {data.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>No data for this filter yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
            {data.map((d) => (
              <div
                key={d.bucket}
                className="rounded-lg p-3 text-center border"
                style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
              >
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{d.bucket}</p>
                <p className="text-xl font-bold text-indigo-400">{d.avg_cpl.toFixed(0)}</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {d.sample_size} moves
                </p>
              </div>
            ))}
          </div>

          <div
            className="rounded-lg p-4 border"
            style={{ background: 'var(--bg-card)', borderColor: 'var(--border)', height: 350 }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="bucket" tick={{ fill: 'var(--chart-axis)', fontSize: 12 }} />
                <YAxis tick={{ fill: 'var(--chart-axis)' }} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--tooltip-bg)',
                    border: '1px solid var(--tooltip-border)',
                    color: 'var(--text-primary)',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="Avg CPL"
                  stroke="#818cf8"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="Blunder %"
                  stroke="#ef4444"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  )
}
