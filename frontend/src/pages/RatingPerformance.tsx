import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import {
  getRatingPerformance, listGames,
  type RatingBucket, type TimeRange,
} from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import { rangeToPlayedFrom } from '../lib/timeRange'
import { useTimeRange } from '../lib/useTimeRange'
import InfoTip from '../components/InfoTip'
import { CPL_EXPLANATION } from '../lib/explanations'
import { colorIcon, resultIcon } from '../lib/format'
import QueryError from '../components/QueryError'

export default function RatingPerformance() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useTimeRange()
  const [openBucket, setOpenBucket] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['ratingPerformance', id, range],
    queryFn: () => getRatingPerformance(id!, range),
    enabled: !!id,
  })

  const data = query.data ?? []

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
  if (query.isError) return <QueryError error={query.error} />


  const chartData = data.map((d) => ({
    bucket: d.bucket,
    'Win %': Math.round(d.win_rate * 100),
    'Avg CPL': d.avg_cpl,
    Games: d.games,
  }))

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        ♜ Performance by Rating
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        How you perform against opponents of different strengths. Click a bucket to drill into those games.
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
        <p style={{ color: 'var(--text-muted)' }}>No analyzed games yet.</p>
      ) : (
        <>
          <div
            className="rounded-lg p-4 mb-6 border"
            style={{ background: 'var(--bg-card)', borderColor: 'var(--border)', height: 350 }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <XAxis dataKey="bucket" tick={{ fill: 'var(--chart-axis)' }} />
                <YAxis tick={{ fill: 'var(--chart-axis)' }} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--tooltip-bg)',
                    border: '1px solid var(--tooltip-border)',
                    color: 'var(--text-primary)',
                  }}
                />
                <Legend />
                <Bar dataKey="Win %" fill="#22c55e" />
                <Bar dataKey="Avg CPL" fill="#818cf8" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {data.map((d) => {
              const isOpen = openBucket === d.bucket
              return (
                <div
                  key={d.bucket}
                  className="rounded-lg border overflow-hidden"
                  style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
                >
                  <button
                    onClick={() => setOpenBucket(isOpen ? null : d.bucket)}
                    className="w-full p-3 text-left"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        {d.bucket}
                      </p>
                      <span style={{ color: 'var(--text-muted)' }} aria-hidden>
                        {isOpen ? '▴' : '▾'}
                      </span>
                    </div>
                    <p
                      className={`text-xl font-bold ${
                        d.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'
                      }`}
                    >
                      {Math.round(d.win_rate * 100)}%
                    </p>
                    <div className="text-xs mt-1 space-y-0.5" style={{ color: 'var(--text-secondary)' }}>
                      <p className="inline-flex items-center gap-1">
                        {d.games} games &middot; {d.avg_cpl} CPL
                        <InfoTip label="CPL in this bucket">
                          Average centipawn loss across your moves in games against opponents in
                          this rating range.
                        </InfoTip>
                      </p>
                      <p className="font-mono">
                        <span className="text-green-400">+{d.wins}</span>{' '}
                        <span style={{ color: 'var(--text-muted)' }}>={d.draws}</span>{' '}
                        <span className="text-red-400">-{d.losses}</span>
                      </p>
                    </div>
                  </button>
                  {isOpen && (
                    <BucketGames playerId={id!} bucket={d} range={range} />
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

function BucketGames({
  playerId,
  bucket,
  range,
}: {
  playerId: string
  bucket: RatingBucket
  range: TimeRange
}) {
  // Mirror the analytics filter so the drill-down count matches the header:
  // analyzed games only, restricted to the active time range.
  const q = useQuery({
    queryKey: ['games', playerId, 'rating', bucket.bucket, range],
    queryFn: () =>
      listGames(playerId, {
        opp_rating_min: bucket.low,
        opp_rating_max: bucket.high,
        analyzed: true,
        played_from: rangeToPlayedFrom(range),
        limit: 100,
      }),
  })

  if (q.isLoading) {
    return (
      <div className="px-3 pb-3 text-xs" style={{ color: 'var(--text-muted)' }}>
        Loading…
      </div>
    )
  }

  const games = q.data?.games ?? []
  if (games.length === 0) {
    return (
      <div className="px-3 pb-3 text-xs" style={{ color: 'var(--text-muted)' }}>
        No games.
      </div>
    )
  }

  return (
    <div
      className="px-3 pb-3 border-t pt-2 space-y-1 max-h-64 overflow-y-auto"
      style={{ borderColor: 'var(--border)' }}
    >
      {games.map((g) => {
        const oppRating =
          g.user_color === 'white' ? g.black_rating : g.white_rating
        return (
          <Link
            key={g.id}
            to={`/games/${g.id}`}
            state={{ from: `/players/${playerId}/ratings` }}
            className="block rounded px-2 py-1.5 text-xs flex items-center justify-between hover:bg-gray-700/50"
            style={{ color: 'var(--text-secondary)' }}
          >
            <span>
              {colorIcon(g.user_color)} vs{' '}
              {g.user_color === 'white' ? g.black_username : g.white_username}
              {oppRating ? ` (${oppRating})` : ''}
            </span>
            <span className="flex items-center gap-2">
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
                {resultIcon(g.user_result)}
              </span>
            </span>
          </Link>
        )
      })}
    </div>
  )
}
