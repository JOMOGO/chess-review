import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { getPhasePerformance, type TimeRange } from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'
import QueryError from '../components/QueryError'
import { CPL_EXPLANATION } from '../lib/explanations'

const PHASE_DESCRIPTIONS: Record<string, string> = {
  opening:
    'First 20 plies with most pieces still on the board. Mostly book/principle moves; high CPL here usually means you are out of book or guessing.',
  middlegame:
    'Pieces developed, plans formed. Most decisions made here. High CPL = tactical or strategic gaps.',
  endgame:
    'Few pieces left. Technique matters most: king activity, opposition, pawn breaks, conversion. High CPL here often points to weak technique.',
}

export default function PhaseDashboard() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<TimeRange>('all')

  const query = useQuery({
    queryKey: ['phasePerformance', id, range],
    queryFn: () => getPhasePerformance(id!, range),
    enabled: !!id,
  })

  const data = query.data ?? []

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
  if (query.isError) return <QueryError error={query.error} />


  const chartData = data.map((d) => ({
    phase: d.phase,
    'Avg CPL': Number(d.avg_cpl.toFixed(1)),
    'Blunder %': Number((d.blunder_rate * 100).toFixed(1)),
    'Mistake %': Number((d.mistake_rate * 100).toFixed(1)),
    'Inaccuracy %': Number((d.inaccuracy_rate * 100).toFixed(1)),
    'Sample Size': d.sample_size,
  }))

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        Phase Performance
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        How you perform in the opening, middlegame, and endgame.
      </p>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Range
        </span>
        <TimeRangeFilter value={range} onChange={setRange} />
        <span className="ml-auto text-xs inline-flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
          What is CPL?
          <InfoTip>{CPL_EXPLANATION}</InfoTip>
        </span>
      </div>

      {data.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          No data yet. Import and analyze games first.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            {data.map((d) => (
              <div
                key={d.phase}
                className="rounded-lg p-4 border"
                style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
              >
                <h3
                  className="font-semibold capitalize mb-2 inline-flex items-center gap-1"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {d.phase}
                  <InfoTip label={`What is the ${d.phase}?`}>
                    {PHASE_DESCRIPTIONS[d.phase] ||
                      'A segment of the game classified by move number and remaining material.'}
                  </InfoTip>
                </h3>
                <p className="text-2xl font-bold text-indigo-400">
                  {d.avg_cpl.toFixed(1)}{' '}
                  <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                    avg CPL
                  </span>
                </p>
                <div className="mt-2 text-sm space-y-1" style={{ color: 'var(--text-secondary)' }}>
                  <p>{d.sample_size} moves</p>
                  <p>Blunders: {(d.blunder_rate * 100).toFixed(1)}%</p>
                  <p>Mistakes: {(d.mistake_rate * 100).toFixed(1)}%</p>
                  <p>Inaccuracies: {(d.inaccuracy_rate * 100).toFixed(1)}%</p>
                </div>
              </div>
            ))}
          </div>

          <div
            className="rounded-lg p-4 border"
            style={{ background: 'var(--bg-card)', borderColor: 'var(--border)', height: 350 }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <XAxis dataKey="phase" tick={{ fill: 'var(--chart-axis)' }} />
                <YAxis tick={{ fill: 'var(--chart-axis)' }} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--tooltip-bg)',
                    border: '1px solid var(--tooltip-border)',
                    color: 'var(--text-primary)',
                  }}
                />
                <Legend />
                <Bar dataKey="Avg CPL" fill="#818cf8" />
                <Bar dataKey="Blunder %" fill="#ef4444" />
                <Bar dataKey="Mistake %" fill="#f97316" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  )
}
