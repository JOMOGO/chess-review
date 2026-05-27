import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import {
  getOpeningStats, listGames,
  type OpeningStat, type TimeRange,
} from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import { rangeToPlayedFrom } from '../lib/timeRange'
import InfoTip from '../components/InfoTip'
import { CPL_EXPLANATION } from '../lib/explanations'

const MAX_LABEL_CHARS = 30
const CHART_TOP_N = 12

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

function colorIcon(color: string): string {
  return color === 'white' ? '♔' : '♚'
}

export default function OpeningStats() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<TimeRange>('all')
  const [expanded, setExpanded] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['openingStats', id, range],
    queryFn: () => getOpeningStats(id!, 2, undefined, range),
    enabled: !!id,
  })

  const data = query.data ?? []

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>

  const sorted = [...data]
    .filter((o) => o.opening_name && o.opening_name.toLowerCase() !== 'undefined')
    .sort((a, b) => b.games - a.games)

  // Build chart rows with unique Y categories. Two rows that share an
  // opening_name (e.g. same opening played as white AND black) would
  // otherwise stack into a single bar.
  const chartData = sorted.slice(0, CHART_TOP_N).map((o) => ({
    ...o,
    label: `${truncate(o.opening_name, MAX_LABEL_CHARS)} ${colorIcon(o.color)}`,
    barLabel: `${o.games}g · ${Math.round(o.win_rate * 100)}%`,
  }))

  // Recharts gives every category equal vertical space; tall enough to label.
  const chartHeight = Math.max(240, chartData.length * 32 + 40)

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        ♝ Opening Win Rates
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        Your performance in each opening. Sorted by frequency. Click a row to see those games.
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

      {sorted.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          No openings to show yet. Either no analyzed games in this range, or chess.com
          didn't tag the openings.
        </p>
      ) : (
        <>
          <div
            className="rounded-lg p-4 mb-6 border"
            style={{
              background: 'var(--bg-card)',
              borderColor: 'var(--border)',
              height: chartHeight,
            }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 8, right: 60, left: 4, bottom: 12 }}
              >
                <XAxis
                  type="number"
                  domain={[0, 1]}
                  tickFormatter={(v) => `${Math.round(v * 100)}%`}
                  tick={{ fill: 'var(--chart-axis)' }}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={220}
                  tick={{ fill: 'var(--chart-axis)', fontSize: 11 }}
                  interval={0}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--tooltip-bg)',
                    border: '1px solid var(--tooltip-border)',
                    color: 'var(--text-primary)',
                  }}
                  formatter={(_v, _name, item) => {
                    const o = item?.payload as OpeningStat | undefined
                    if (!o) return [`${Math.round(Number(_v) * 100)}%`, 'Win Rate']
                    return [
                      `${Math.round(o.win_rate * 100)}% · ${o.games}g (+${o.wins} =${o.draws} -${o.losses}) · ${o.avg_cpl} CPL`,
                      o.opening_name,
                    ]
                  }}
                />
                <Bar dataKey="win_rate" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={
                        entry.win_rate >= 0.6
                          ? '#22c55e'
                          : entry.win_rate >= 0.4
                            ? '#eab308'
                            : '#ef4444'
                      }
                    />
                  ))}
                  <LabelList
                    dataKey="barLabel"
                    position="right"
                    style={{
                      fill: 'var(--text-primary)',
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-1.5">
            {sorted.map((o) => {
              const key = `${o.opening_name}-${o.color}-${o.eco ?? ''}`
              const isOpen = expanded === key
              return (
                <div
                  key={key}
                  className="rounded-lg border"
                  style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
                >
                  <button
                    onClick={() => setExpanded(isOpen ? null : key)}
                    className="w-full p-3 flex items-center justify-between text-left hover:opacity-90"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{colorIcon(o.color)}</span>
                      <div>
                        <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                          {o.opening_name}
                        </span>
                        {o.eco && (
                          <span className="text-xs ml-2" style={{ color: 'var(--text-muted)' }}>
                            {o.eco}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <span style={{ color: 'var(--text-muted)' }}>{o.games} games</span>
                      <span style={{ color: 'var(--text-muted)' }}>{o.avg_cpl} CPL</span>
                      <div className="flex gap-1.5 font-mono text-xs">
                        <span className="text-green-400">+{o.wins}</span>
                        <span style={{ color: 'var(--text-muted)' }}>=</span>
                        <span style={{ color: 'var(--text-muted)' }}>{o.draws}</span>
                        <span style={{ color: 'var(--text-muted)' }}>=</span>
                        <span className="text-red-400">-{o.losses}</span>
                      </div>
                      <span
                        className={`font-bold ${
                          o.win_rate >= 0.6
                            ? 'text-green-400'
                            : o.win_rate >= 0.4
                              ? 'text-yellow-400'
                              : 'text-red-400'
                        }`}
                      >
                        {Math.round(o.win_rate * 100)}%
                      </span>
                      <span
                        className="w-5 text-center"
                        style={{ color: 'var(--text-muted)' }}
                        aria-hidden
                      >
                        {isOpen ? '▴' : '▾'}
                      </span>
                    </div>
                  </button>
                  {isOpen && (
                    <OpeningGames
                      playerId={id!}
                      opening={o}
                      range={range}
                    />
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function OpeningGames({
  playerId,
  opening,
  range,
}: {
  playerId: string
  opening: OpeningStat
  range: TimeRange
}) {
  // Drill-down must match the row's count, which is computed over analyzed
  // games in the active time range — otherwise unanalyzed or out-of-range
  // games leak in and the "N games" header disagrees with the list below.
  const q = useQuery({
    queryKey: ['games', playerId, 'opening', opening.opening_name, opening.color, range],
    queryFn: () =>
      listGames(playerId, {
        opening_name: opening.opening_name,
        user_color: opening.color,
        analyzed: true,
        played_from: rangeToPlayedFrom(range),
        limit: 100,
      }),
    enabled: true,
  })

  if (q.isLoading) {
    return (
      <div className="px-3 pb-3 text-xs" style={{ color: 'var(--text-muted)' }}>
        Loading games…
      </div>
    )
  }

  const games = q.data?.games ?? []
  if (games.length === 0) {
    return (
      <div className="px-3 pb-3 text-xs" style={{ color: 'var(--text-muted)' }}>
        No matching games found.
      </div>
    )
  }

  return (
    <div className="px-3 pb-3 space-y-1 border-t pt-2" style={{ borderColor: 'var(--border)' }}>
      {games.map((g) => (
        <Link
          key={g.id}
          to={`/games/${g.id}`}
          state={{ from: `/players/${playerId}/opening-stats` }}
          className="block rounded px-2 py-1.5 text-xs flex items-center justify-between hover:bg-gray-700/50"
          style={{ color: 'var(--text-secondary)' }}
        >
          <span>
            {colorIcon(g.user_color)}{' '}
            {g.white_username} vs {g.black_username}
          </span>
          <span className="flex items-center gap-3">
            <span style={{ color: 'var(--text-muted)' }}>
              {new Date(g.played_at).toLocaleDateString()}
            </span>
            <span
              className={
                g.user_result === 'win'
                  ? 'text-green-400'
                  : g.user_result === 'loss'
                    ? 'text-red-400'
                    : ''
              }
              style={
                g.user_result === 'draw' ? { color: 'var(--text-muted)' } : undefined
              }
            >
              {g.user_result === 'win' ? '✓' : g.user_result === 'loss' ? '✕' : '½'}
            </span>
          </span>
        </Link>
      ))}
    </div>
  )
}
