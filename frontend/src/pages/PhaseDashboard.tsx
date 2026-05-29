import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  getPhasePerformance, getPhaseExamples,
  type PhasePerformance, type PhaseExample, type TimeRange,
} from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'
import QueryError from '../components/QueryError'
import { CPL_EXPLANATION } from '../lib/explanations'
import { resultIcon, resultColor } from '../lib/format'
import { useTimeRange } from '../lib/useTimeRange'

const PHASE_DESCRIPTIONS: Record<string, string> = {
  opening:
    'First 20 plies with most pieces still on the board. Mostly book/principle moves; high CPL here usually means you are out of book or guessing.',
  middlegame:
    'Pieces developed, plans formed. Most decisions made here. High CPL = tactical or strategic gaps.',
  endgame:
    'Few pieces left. Technique matters most: king activity, opposition, pawn breaks, conversion. High CPL here often points to weak technique.',
}

const PHASE_LABEL: Record<string, string> = {
  opening: 'Opening',
  middlegame: 'Middlegame',
  endgame: 'Endgame',
}

// Minimum opponent moves before we trust the delta. Below this the comparison
// is noisy (one game with a wild opponent skews the average).
const DELTA_MIN_SAMPLE = 30

function deltaColor(delta: number): string {
  // Positive delta = user CPL > opponent CPL = relatively weaker. Red.
  // Negative delta = user CPL < opponent CPL = relatively stronger. Green.
  if (delta > 10) return '#ef4444'
  if (delta > 3) return '#f97316'
  if (delta < -10) return '#22c55e'
  if (delta < -3) return '#84cc16'
  return 'var(--text-secondary)'
}

export default function PhaseDashboard() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useTimeRange()
  const [expanded, setExpanded] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['phasePerformance', id, range],
    queryFn: () => getPhasePerformance(id!, range),
    enabled: !!id,
  })

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
  if (query.isError) return <QueryError error={query.error} />

  const data = query.data ?? []

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        Phase Performance
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        How you perform in the opening, middlegame, and endgame &mdash; and how
        you stack up against the opponents you face there.
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
        <div className="space-y-3">
          {data.map((d) => (
            <PhaseRow
              key={d.phase}
              row={d}
              playerId={id!}
              range={range}
              expanded={expanded === d.phase}
              onToggle={() => setExpanded(expanded === d.phase ? null : d.phase)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function PhaseRow({
  row, playerId, range, expanded, onToggle,
}: {
  row: PhasePerformance
  playerId: string
  range: TimeRange
  expanded: boolean
  onToggle: () => void
}) {
  const examplesQuery = useQuery({
    queryKey: ['phaseExamples', playerId, row.phase, range],
    queryFn: () => getPhaseExamples(playerId, row.phase, 20, range),
    enabled: expanded,
  })

  const delta = row.avg_cpl - row.opponent_avg_cpl
  const trustDelta = row.opponent_sample_size >= DELTA_MIN_SAMPLE
  const examples: PhaseExample[] = examplesQuery.data ?? []

  return (
    <div
      className="rounded-lg border"
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
    >
      <button
        onClick={onToggle}
        className="w-full text-left p-4 transition-colors hover:bg-white/[0.02]"
      >
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-1.5 min-w-[120px]">
            <span
              className="text-lg font-semibold capitalize"
              style={{ color: 'var(--text-primary)' }}
            >
              {PHASE_LABEL[row.phase] ?? row.phase}
            </span>
            <InfoTip label={`What is the ${row.phase}?`}>
              {PHASE_DESCRIPTIONS[row.phase] ??
                'A segment of the game classified by move number and remaining material.'}
            </InfoTip>
          </div>

          <Metric label="You" value={row.avg_cpl.toFixed(1)} suffix="cpl" color="#818cf8" />
          <Metric label="Opp" value={row.opponent_avg_cpl.toFixed(1)} suffix="cpl" />
          <Metric
            label="Δ"
            value={`${delta > 0 ? '+' : ''}${delta.toFixed(1)}`}
            color={trustDelta ? deltaColor(delta) : 'var(--text-muted)'}
            tip={
              trustDelta
                ? delta > 0
                  ? 'You play this phase WORSE than your opponents on average — relative weakness.'
                  : delta < 0
                    ? 'You play this phase BETTER than your opponents on average — relative strength.'
                    : 'You match your opponents in this phase.'
                : `Too few opponent moves (${row.opponent_sample_size}) to trust the comparison — need ≥ ${DELTA_MIN_SAMPLE}.`
            }
          />

          <div className="flex items-center gap-3 ml-auto text-xs" style={{ color: 'var(--text-secondary)' }}>
            <ErrorRate label="Blunder" value={row.blunder_rate} color="#ef4444" />
            <ErrorRate label="Mistake" value={row.mistake_rate} color="#f97316" />
            <ErrorRate label="Inacc" value={row.inaccuracy_rate} color="#eab308" />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {row.sample_size} moves
            </span>
            <span aria-hidden style={{ color: 'var(--text-muted)' }}>
              {expanded ? '▾' : '▸'}
            </span>
          </div>
        </div>
      </button>

      {expanded && (
        <div
          className="border-t px-4 pt-3 pb-4"
          style={{ borderColor: 'var(--border)' }}
        >
          <div className="text-xs uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>
            Worst moves in this phase
          </div>
          {examplesQuery.isLoading ? (
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Loading...</p>
          ) : examples.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              No mistakes worse than inaccuracy in this range.
            </p>
          ) : (
            <div className="space-y-1.5">
              {examples.map((ex) => (
                <Link
                  key={ex.move_id}
                  to={`/games/${ex.game_id}?ply=${Math.max(0, ex.ply - 1)}`}
                  state={{ from: `/players/${playerId}/phases` }}
                  className="block rounded-md p-2.5 border hover:border-indigo-500 transition-colors"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                      {Math.floor((ex.ply + 1) / 2)}
                      {ex.ply % 2 === 1 ? '.' : '...'} {ex.san}
                    </span>
                    {ex.classification && (
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          ex.classification === 'blunder' || ex.classification === 'miss'
                            ? 'bg-red-500/20 text-red-400'
                            : ex.classification === 'mistake'
                              ? 'bg-orange-500/20 text-orange-400'
                              : 'bg-yellow-500/20 text-yellow-400'
                        }`}
                      >
                        {ex.classification}
                      </span>
                    )}
                    {ex.cp_loss != null && (
                      <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                        -{(ex.cp_loss / 100).toFixed(2)}
                      </span>
                    )}
                    <span className="text-xs truncate flex-1" style={{ color: 'var(--text-muted)' }}>
                      {ex.opening_name ?? '?'}
                    </span>
                    <span className={`text-sm ${resultColor(ex.user_result)}`}>
                      {resultIcon(ex.user_result)}
                    </span>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {new Date(ex.played_at).toLocaleDateString()}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Metric({
  label, value, suffix, color, tip,
}: {
  label: string
  value: string
  suffix?: string
  color?: string
  tip?: string
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide inline-flex items-center gap-1"
        style={{ color: 'var(--text-muted)' }}>
        {label}
        {tip && <InfoTip label={label}>{tip}</InfoTip>}
      </span>
      <span className="text-lg font-bold leading-tight" style={{ color: color ?? 'var(--text-primary)' }}>
        {value}
        {suffix && <span className="text-xs font-normal ml-1" style={{ color: 'var(--text-muted)' }}>{suffix}</span>}
      </span>
    </div>
  )
}

function ErrorRate({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} aria-hidden />
      <span>{label} {(value * 100).toFixed(1)}%</span>
    </span>
  )
}
