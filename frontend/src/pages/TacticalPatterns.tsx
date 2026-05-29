import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import {
  getMotifs, getMotifExamples,
  type MotifSummary,
} from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'
import { resultIcon } from '../lib/format'
import { useTimeRange } from '../lib/useTimeRange'

const MOTIF_LABEL: Record<string, string> = {
  fork: 'Forks',
  pin: 'Pins',
  skewer: 'Skewers',
  discovered_attack: 'Discovered Attacks',
  removal_of_defender: 'Removal of Defender',
  back_rank_mate: 'Back-Rank Mates',
  smothered_mate: 'Smothered Mates',
  trapped_piece: 'Trapped Pieces',
  deflection: 'Deflections',
  pawn_promotion: 'Pawn Promotions',
}

const MOTIF_DESCRIPTION: Record<string, string> = {
  fork: 'Engine could have moved a piece to attack two enemy targets at once. You played something else.',
  pin: 'Engine could have pinned an enemy piece against a more valuable piece behind it. You played something else.',
  skewer: 'Engine could have attacked a valuable enemy piece, forcing it to move and exposing a less valuable piece behind. You played something else.',
  discovered_attack: 'Engine could have moved a piece that, by moving, uncovered an attack from a second piece behind it. You played something else.',
  removal_of_defender: 'Engine could have captured a piece whose only job was defending another piece, leaving that piece hanging. You played something else.',
  back_rank_mate: 'Engine had a short forced mate on the back rank. You played something else.',
  smothered_mate: 'Engine had a knight checkmate where the enemy king was blocked in by its own pieces. You played something else.',
  trapped_piece: 'Engine could have captured an enemy piece that had no safe square to escape to. You played something else.',
  deflection: 'Engine could have played a check that forced an enemy piece away from a key defensive duty, winning material on the follow-up. You played something else.',
  pawn_promotion: 'Engine could have pushed a pawn to promotion. You played something else.',
}

const MOTIF_COLOR: Record<string, string> = {
  back_rank_mate: '#dc2626',     // red
  fork: '#f97316',               // orange
  smothered_mate: '#eab308',     // yellow
  removal_of_defender: '#84cc16', // lime
  pawn_promotion: '#10b981',     // emerald
  discovered_attack: '#06b6d4',  // cyan
  trapped_piece: '#3b82f6',      // blue
  deflection: '#8b5cf6',         // violet
  pin: '#d946ef',                // fuchsia
  skewer: '#ec4899',             // pink
}

export default function TacticalPatterns() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useTimeRange()
  const [selected, setSelected] = useState<string | null>(null)

  const summaryQuery = useQuery({
    queryKey: ['motifs', id, range],
    queryFn: () => getMotifs(id!, range),
    enabled: !!id,
  })

  const examplesQuery = useQuery({
    queryKey: ['motifExamples', id, selected, range],
    queryFn: () => getMotifExamples(id!, selected!, 20, range),
    enabled: !!id && !!selected,
  })

  const data: MotifSummary[] = summaryQuery.data ?? []
  const total = data.reduce((s, d) => s + d.count, 0)
  const chartData = data.map((d) => ({
    label: MOTIF_LABEL[d.motif] ?? d.motif,
    motif: d.motif,
    count: d.count,
    fill: MOTIF_COLOR[d.motif] ?? '#818cf8',
  }))

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        Tactical Patterns
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        Tactics the engine spotted that you didn&apos;t play. Detected on user
        moves classified as mistake, blunder, or miss where the engine
        recommended a different move.
      </p>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Range
        </span>
        <TimeRangeFilter value={range} onChange={setRange} />
        <span className="ml-auto text-xs inline-flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
          How are these detected?
          <InfoTip>
            Patterns are matched on the engine&apos;s preferred move and its
            principal variation using piece geometry (attack squares,
            pin/skewer rays, defender removal). No machine learning &mdash;
            so the classifier may miss exotic tactics but rarely
            mislabels what it does flag.
          </InfoTip>
        </span>
      </div>

      {summaryQuery.isLoading ? (
        <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
      ) : data.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          No tactical patterns detected yet. Import and analyze games first,
          or pick a wider time range.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
            {data.map((d) => (
              <button
                key={d.motif}
                onClick={() => setSelected(selected === d.motif ? null : d.motif)}
                className={`text-left rounded-lg p-4 border transition-colors ${
                  selected === d.motif ? 'border-indigo-500' : 'hover:border-indigo-500'
                }`}
                style={{
                  background: 'var(--bg-card)',
                  borderColor: selected === d.motif ? '#6366f1' : 'var(--border)',
                }}
              >
                <p
                  className="text-sm inline-flex items-center gap-1"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {MOTIF_LABEL[d.motif] ?? d.motif}
                  <InfoTip label={`About ${MOTIF_LABEL[d.motif] ?? d.motif}`}>
                    {MOTIF_DESCRIPTION[d.motif] ??
                      'A tactical pattern detected on the engine’s preferred move.'}
                  </InfoTip>
                </p>
                <p className="text-2xl font-bold mt-0.5" style={{ color: MOTIF_COLOR[d.motif] ?? '#818cf8' }}>
                  {d.count}
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  in {d.games} game{d.games === 1 ? '' : 's'}
                  {d.blunders > 0 && ` · ${d.blunders} blunder${d.blunders === 1 ? '' : 's'}`}
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
                  tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
                  angle={-20}
                  textAnchor="end"
                  height={50}
                />
                <YAxis tick={{ fill: 'var(--chart-axis)' }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--tooltip-bg)',
                    border: '1px solid var(--tooltip-border)',
                    color: 'var(--text-primary)',
                  }}
                  cursor={{ fill: 'rgba(99, 102, 241, 0.1)' }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {chartData.map((d) => (
                    <Cell key={d.motif} fill={d.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {selected && (
            <div>
              <h2 className="text-lg font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                Recent {MOTIF_LABEL[selected] ?? selected}
              </h2>
              {examplesQuery.isLoading ? (
                <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
              ) : (examplesQuery.data ?? []).length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>No examples in this range.</p>
              ) : (
                <div className="space-y-1.5">
                  {(examplesQuery.data ?? []).map((ex) => (
                    <Link
                      key={ex.tactic_id}
                      to={`/games/${ex.game_id}?ply=${Math.max(0, ex.ply - 1)}`}
                      state={{ from: `/players/${id}/tactics` }}
                      className="block rounded-lg p-3 border hover:border-indigo-500 transition-colors"
                      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
                    >
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                            {Math.floor((ex.ply + 1) / 2)}
                            {ex.ply % 2 === 1 ? '.' : '...'} {ex.san}
                          </span>
                          {ex.classification && (
                            <span
                              className={`text-xs px-2 py-0.5 rounded ${
                                ex.classification === 'blunder' || ex.classification === 'miss'
                                  ? 'bg-red-500/20 text-red-400'
                                  : 'bg-orange-500/20 text-orange-400'
                              }`}
                            >
                              {ex.classification}
                            </span>
                          )}
                          {ex.cp_loss != null && (
                            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                              -{(ex.cp_loss / 100).toFixed(1)}
                            </span>
                          )}
                        </div>
                        <span
                          className={`text-sm ${
                            ex.user_result === 'win'
                              ? 'text-green-400'
                              : ex.user_result === 'loss'
                                ? 'text-red-400'
                                : 'text-gray-400'
                          }`}
                        >
                          {resultIcon(ex.user_result)}
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

          <p className="mt-6 text-xs" style={{ color: 'var(--text-muted)' }}>
            {total} tactical opportunity{total === 1 ? '' : 'ies'} missed across the selected range.
          </p>
        </>
      )}
    </div>
  )
}
