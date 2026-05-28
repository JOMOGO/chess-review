import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import {
  getEndgames, getEndgameExamples,
  type EndgameBucket, type TimeRange,
} from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'

function bucketLabel(bucket: string): string {
  // KRPvKR -> "K+R+P vs K+R" for readability
  const [mine, theirs] = bucket.split('v')
  const fmt = (s: string) =>
    s.split('').reduce<string[]>((acc, ch) => {
      if (acc.length && acc[acc.length - 1].slice(-1) === ch) {
        acc[acc.length - 1] = acc[acc.length - 1] + ch
      } else {
        acc.push(ch)
      }
      return acc
    }, []).join('+')
  return `${fmt(mine)} vs ${fmt(theirs)}`
}

function conversionColor(rate: number): string {
  if (rate >= 0.85) return '#22c55e'  // green — converting well
  if (rate >= 0.6) return '#84cc16'   // lime
  if (rate >= 0.4) return '#f59e0b'   // amber
  return '#ef4444'                    // red — leaking won games
}

export default function EndgameConversion() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<TimeRange>('all')
  const [selected, setSelected] = useState<string | null>(null)

  const summaryQuery = useQuery({
    queryKey: ['endgames', id, range],
    queryFn: () => getEndgames(id!, 1, range),
    enabled: !!id,
  })

  const examplesQuery = useQuery({
    queryKey: ['endgameExamples', id, selected, range],
    queryFn: () => getEndgameExamples(id!, selected!, 20, range),
    enabled: !!id && !!selected,
  })

  const data: EndgameBucket[] = summaryQuery.data ?? []
  const totalReached = data.reduce((s, d) => s + d.reached, 0)
  const totalConverted = data.reduce((s, d) => s + d.converted, 0)
  const overallRate = totalReached > 0 ? totalConverted / totalReached : 0

  const chartData = data.map((d) => ({
    label: bucketLabel(d.bucket),
    bucket: d.bucket,
    'Conversion %': Math.round(d.conversion_rate * 100),
    fill: conversionColor(d.conversion_rate),
  }))

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        Endgame Conversion
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        When you reach a won endgame &mdash; eval &ge; +200cp for at least 4
        consecutive plies in the endgame phase &mdash; how often do you
        actually win it?
      </p>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Range
        </span>
        <TimeRangeFilter value={range} onChange={setRange} />
        <span className="ml-auto text-xs inline-flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
          How is this detected?
          <InfoTip>
            We scan every analyzed game for the first ply where you have a
            sustained &ge;+200cp advantage in the endgame phase (4
            consecutive plies). The material on the board at that ply
            becomes the bucket. We then check whether you actually won
            the game.
          </InfoTip>
        </span>
      </div>

      {summaryQuery.isLoading ? (
        <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
      ) : data.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          No won endgames detected yet. Either no game in this range hit the
          threshold, or analysis is still running.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div
              className="rounded-lg p-4 border"
              style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
            >
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Won endgames reached</p>
              <p className="text-2xl font-bold text-indigo-400">{totalReached}</p>
            </div>
            <div
              className="rounded-lg p-4 border"
              style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
            >
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Converted to win</p>
              <p className="text-2xl font-bold text-indigo-400">{totalConverted}</p>
            </div>
            <div
              className="rounded-lg p-4 border col-span-2"
              style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
            >
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Overall conversion rate</p>
              <p className="text-2xl font-bold" style={{ color: conversionColor(overallRate) }}>
                {Math.round(overallRate * 100)}%
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                {totalReached - totalConverted} game{totalReached - totalConverted === 1 ? '' : 's'} where you had a +2 endgame and didn&apos;t win
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
            {data.map((d) => (
              <button
                key={d.bucket}
                onClick={() => setSelected(selected === d.bucket ? null : d.bucket)}
                className={`text-left rounded-lg p-4 border transition-colors ${
                  selected === d.bucket ? 'border-indigo-500' : 'hover:border-indigo-500'
                }`}
                style={{
                  background: 'var(--bg-card)',
                  borderColor: selected === d.bucket ? '#6366f1' : 'var(--border)',
                }}
              >
                <p className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
                  {bucketLabel(d.bucket)}
                </p>
                <p
                  className="text-2xl font-bold mt-0.5"
                  style={{ color: conversionColor(d.conversion_rate) }}
                >
                  {Math.round(d.conversion_rate * 100)}%
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  {d.converted} / {d.reached} won
                </p>
              </button>
            ))}
          </div>

          <div
            className="rounded-lg p-4 border mb-6"
            style={{ background: 'var(--bg-card)', borderColor: 'var(--border)', height: 280 }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 30 }}>
                <XAxis
                  dataKey="label"
                  tick={{ fill: 'var(--chart-axis)', fontSize: 11 }}
                  angle={-20}
                  textAnchor="end"
                  height={50}
                />
                <YAxis
                  tick={{ fill: 'var(--chart-axis)' }}
                  domain={[0, 100]}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--tooltip-bg)',
                    border: '1px solid var(--tooltip-border)',
                    color: 'var(--text-primary)',
                  }}
                  cursor={{ fill: 'rgba(99, 102, 241, 0.1)' }}
                  formatter={(v) => [`${v}%`, 'Converted']}
                />
                <Bar dataKey="Conversion %" radius={[4, 4, 0, 0]}>
                  {chartData.map((d) => (
                    <Cell key={d.bucket} fill={d.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {selected && (
            <div>
              <h2 className="text-lg font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                {bucketLabel(selected)} &mdash; recent games
              </h2>
              {examplesQuery.isLoading ? (
                <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
              ) : (examplesQuery.data ?? []).length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>No examples in this range.</p>
              ) : (
                <div className="space-y-1.5">
                  {(examplesQuery.data ?? []).map((ex) => (
                    <Link
                      key={ex.reach_id}
                      to={`/games/${ex.game_id}?ply=${Math.max(0, ex.entry_ply - 1)}`}
                      state={{ from: `/players/${id}/endgames` }}
                      className="block rounded-lg p-3 border hover:border-indigo-500 transition-colors"
                      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
                    >
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-3">
                          <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                            {ex.user_color === 'white' ? '♔' : '♚'} ply {ex.entry_ply}
                          </span>
                          <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                            +{(ex.user_cp_at_entry / 100).toFixed(1)} at entry
                          </span>
                          {ex.converted ? (
                            <span className="text-xs px-2 py-0.5 rounded bg-green-500/20 text-green-400">
                              ✓ converted
                            </span>
                          ) : (
                            <span className="text-xs px-2 py-0.5 rounded bg-red-500/20 text-red-400">
                              ✕ {ex.user_result}
                            </span>
                          )}
                        </div>
                        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                          {ex.time_class}
                        </span>
                      </div>
                      <div className="flex justify-between text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                        <span>{ex.opening_name ?? '?'}</span>
                        <span>{new Date(ex.played_at).toLocaleDateString()}</span>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
