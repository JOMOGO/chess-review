import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { BookOpen, Clock, Crown, Hourglass, List, Sparkles, Target, Trophy, Zap, type LucideIcon } from 'lucide-react'
import {
  getPlayer, listGames, startImport, getImportStatus,
  getAccuracyTrend,
  type TimeRange,
} from '../api/client'
import { setStoredPlayer, setStoredImport, getStoredImport } from '../lib/storage'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'
import { CPL_EXPLANATION } from '../lib/explanations'

export default function PlayerDashboard() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<TimeRange>('all')

  const activeImportRunning = !!getStoredImport()

  const playerQuery = useQuery({
    queryKey: ['player', id],
    queryFn: async () => {
      const p = await getPlayer(id!)
      setStoredPlayer({ id: p.id, username: p.username })
      return p
    },
    enabled: !!id,
    staleTime: activeImportRunning ? 0 : 5 * 60 * 1000,
  })

  const gamesQuery = useQuery({
    queryKey: ['games', id, { limit: 5 }],
    queryFn: () => listGames(id!, { limit: 5 }),
    enabled: !!id,
    staleTime: activeImportRunning ? 0 : 5 * 60 * 1000,
  })

  const trendQuery = useQuery({
    queryKey: ['accuracyTrend', id, range],
    queryFn: () => getAccuracyTrend(id!, undefined, range),
    enabled: !!id,
  })

  const reimportMutation = useMutation({
    mutationFn: async () => {
      const { job_id } = await startImport(id!)
      setStoredImport({ playerId: id!, jobId: job_id })
    },
  })

  const importQuery = useQuery({
    queryKey: ['importStatus', id],
    queryFn: () => getImportStatus(id!),
    enabled: !!id && activeImportRunning,
    refetchInterval: 2000,
  })

  const player = playerQuery.data
  const games = gamesQuery.data
  const trend = trendQuery.data ?? []

  if (playerQuery.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
  if (!player) return <p className="text-red-400">Player not found</p>

  const totalGames = importQuery.data?.imported_games ?? player.total_games_imported

  const avgAccuracy = trend.length > 0
    ? Math.round((trend.reduce((s, d) => s + d.accuracy, 0) / trend.length) * 10) / 10
    : null
  const avgCpl = trend.length > 0
    ? Math.round((trend.reduce((s, d) => s + d.avg_cpl, 0) / trend.length) * 10) / 10
    : null
  const wins = trend.filter((d) => d.user_result === 'win').length
  const draws = trend.filter((d) => d.user_result === 'draw').length
  const losses = trend.filter((d) => d.user_result === 'loss').length
  const scoreRate = trend.length > 0
    ? Math.round(((wins + 0.5 * draws) / trend.length) * 1000) / 10
    : null

  return (
    <div>
      <div className="flex items-center justify-between mb-6 flex-wrap gap-2">
        <div>
          <h1 className="text-3xl font-bold" style={{ color: 'var(--text-primary)' }}>
            {player.username}
          </h1>
        </div>
        <button
          onClick={() => reimportMutation.mutate()}
          disabled={reimportMutation.isPending || activeImportRunning}
          className="px-4 py-2 border rounded-lg text-sm
                     hover:border-indigo-500 disabled:opacity-40 transition-colors"
          style={{
            background: 'var(--bg-card)',
            borderColor: 'var(--border)',
            color: 'var(--text-secondary)',
          }}
        >
          ↻ Re-import
        </button>
      </div>

      <div className="mb-4 flex items-center gap-3 flex-wrap">
        <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Range
        </span>
        <TimeRangeFilter value={range} onChange={setRange} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <SummaryCard
          label="Avg accuracy"
          value={avgAccuracy != null ? `${avgAccuracy}%` : '—'}
          info={
            <>
              Mean per-game accuracy across the selected range. Each game is
              0-100 based on how much win probability you gave up per move.
            </>
          }
        />
        <SummaryCard
          label="Avg CPL"
          value={avgCpl != null ? avgCpl.toFixed(1) : '—'}
          info={CPL_EXPLANATION}
        />
        <SummaryCard
          label="Score"
          value={scoreRate != null ? `${scoreRate}%` : '—'}
          sub={trend.length > 0 ? `${wins}W ${draws}D ${losses}L` : undefined}
          info={
            <>
              Tournament score: wins count 1, draws 0.5, losses 0. Includes
              every analyzed game in the range.
            </>
          }
        />
        <SummaryCard
          label="Analyzed games"
          value={
            totalGames > 0 && totalGames !== trend.length
              ? `${trend.length} / ${totalGames}`
              : trend.length
          }
          info={
            <>
              The first number is how many games had enough user moves to
              score accuracy. The second is the total finished engine
              analysis in the selected range. They differ when you have
              extremely short games (instant resignations, 0-ply abandons)
              — those still get analyzed but there&apos;s nothing to score.
            </>
          }
        />
      </div>

      <Link
        to={`/players/${id}/recommendations`}
        className="block rounded-lg p-4 border mb-3 transition-colors hover:border-indigo-500"
        style={{
          background:
            'linear-gradient(135deg, color-mix(in srgb, var(--bg-card) 92%, #6366f1) 0%, var(--bg-card) 100%)',
          borderColor: 'var(--border)',
        }}
      >
        <div className="flex items-center gap-3">
          <Sparkles className="w-6 h-6 text-indigo-400" strokeWidth={1.75} />
          <div>
            <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              What should you train?
            </p>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              Ranked weaknesses with concrete next steps.
            </p>
          </div>
        </div>
      </Link>

      <div className="grid grid-cols-3 gap-3 mb-8">
        <NavCard to={`/players/${id}/games`} Icon={List} label="Games" desc={`${totalGames} games`} />
        <NavCard to={`/players/${id}/accuracy`} Icon={Target} label="Accuracy" desc="Trend over time" />
        <NavCard to={`/players/${id}/opening-stats`} Icon={BookOpen} label="Openings" desc="Win rates & leaks" />
        <NavCard to={`/players/${id}/phases`} Icon={Hourglass} label="Phases" desc="Opening / Middle / End" />
        <NavCard to={`/players/${id}/time`} Icon={Clock} label="Time Pressure" desc="CPL vs clock" />
        <NavCard to={`/players/${id}/ratings`} Icon={Trophy} label="By Rating" desc="vs opponent strength" />
        <NavCard to={`/players/${id}/tactics`} Icon={Zap} label="Tactics" desc="Forks, pins, missed mates" />
        <NavCard to={`/players/${id}/endgames`} Icon={Crown} label="Endgames" desc="Conversion of won endgames" />
      </div>

      {games && games.games.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
              Recent Games
            </h2>
            <Link to={`/players/${id}/games`} className="text-sm text-indigo-400 hover:text-indigo-300">
              View all →
            </Link>
          </div>
          <div className="space-y-1.5">
            {games.games.map((g) => (
              <Link
                key={g.id}
                to={`/games/${g.id}`}
                state={{ from: `/players/${id}` }}
                className="block bg-[#16162a] border border-gray-700 rounded-lg p-3
                           hover:border-indigo-500 transition-colors"
              >
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span>{g.user_color === 'white' ? '♔' : '♚'}</span>
                    <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                      {g.white_username} vs {g.black_username}
                    </span>
                  </div>
                  <span
                    className={`text-sm ${
                      g.user_result === 'win'
                        ? 'text-green-400'
                        : g.user_result === 'loss'
                          ? 'text-red-400'
                          : 'text-gray-400'
                    }`}
                  >
                    {g.user_result === 'win' ? '✓ Win' : g.user_result === 'loss' ? '✕ Loss' : '½ Draw'}
                  </span>
                </div>
                <div className="flex justify-between text-xs mt-1 ml-6" style={{ color: 'var(--text-muted)' }}>
                  <span>{g.opening_name || g.eco || '?'} &middot; {g.time_class}</span>
                  <span>{new Date(g.played_at).toLocaleDateString()}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SummaryCard({
  label,
  value,
  sub,
  info,
}: {
  label: string
  value: string | number
  sub?: string
  info?: React.ReactNode
}) {
  return (
    <div
      className="rounded-lg p-4 border"
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
    >
      <p className="text-xs inline-flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
        {label}
        {info && <InfoTip label={`About ${label}`}>{info}</InfoTip>}
      </p>
      <p className="text-2xl font-bold text-indigo-400 mt-0.5">{value}</p>
      {sub && (
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{sub}</p>
      )}
    </div>
  )
}

function NavCard({ to, Icon, label, desc }: { to: string; Icon: LucideIcon; label: string; desc: string }) {
  return (
    <Link
      to={to}
      className="rounded-lg p-4 border hover:border-indigo-500 transition-colors group"
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
    >
      <Icon className="w-6 h-6 mb-1 text-indigo-400 group-hover:scale-110 transition-transform" strokeWidth={1.75} />
      <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>{label}</p>
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{desc}</p>
    </Link>
  )
}
