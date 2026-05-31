import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import {
  getOpeningStats, listGames, getAccuracyTrend,
  type OpeningStat, type AccuracyPoint, type TimeRange,
} from '../api/client'
import { rangeToPlayedFrom } from '../lib/timeRange'
import { scoreColor, relativeDate } from '../lib/openings'
import { colorIcon, resultIcon, resultColor } from '../lib/format'
import WdlBar from '../components/WdlBar'
import QueryError from '../components/QueryError'

const MAX_LABEL_CHARS = 30
const CHART_TOP_N = 12
const GROUP_STORAGE_KEY = 'openingStats.groupMode'

// Mirrors the Move Tree's "min games per branch" control. Default 2 so rare
// lines aren't dropped, matching OpeningTree's default.
const MIN_GAMES_OPTIONS = [1, 2, 5, 10] as const
type MinGames = typeof MIN_GAMES_OPTIONS[number]

type GroupMode = 'flat' | 'eco' | 'name'

const ECO_FAMILY_LABELS: Record<string, string> = {
  A: 'Flank Openings',
  B: 'Semi-Open Games (1.e4 …)',
  C: 'Open Games (1.e4 e5)',
  D: 'Closed Games (1.d4 d5)',
  E: 'Indian Defenses (1.d4 Nf6)',
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

interface Aggregate {
  games: number
  wins: number
  draws: number
  losses: number
  score_rate: number
  avg_cpl: number
}

function aggregate(items: OpeningStat[]): Aggregate {
  const games = items.reduce((s, o) => s + o.games, 0)
  const wins = items.reduce((s, o) => s + o.wins, 0)
  const draws = items.reduce((s, o) => s + o.draws, 0)
  const losses = items.reduce((s, o) => s + o.losses, 0)
  const score_rate = games > 0 ? (wins + 0.5 * draws) / games : 0
  const totalCpl = items.reduce((s, o) => s + o.avg_cpl * o.games, 0)
  const avg_cpl = games > 0 ? totalCpl / games : 0
  return { games, wins, draws, losses, score_rate, avg_cpl }
}

function buildNameGroups(rows: OpeningStat[]): Array<{ key: string; label: string; items: OpeningStat[] }> {
  const grouped = new Map<string, OpeningStat[]>()
  const singletons: OpeningStat[] = []

  const prefixCount = new Map<string, number>()
  for (const row of rows) {
    const tokens = row.opening_name.split(/\s+/)
    for (let n = 2; n <= Math.min(tokens.length, 5); n++) {
      const prefix = tokens.slice(0, n).join(' ')
      prefixCount.set(prefix, (prefixCount.get(prefix) ?? 0) + 1)
    }
  }

  for (const row of rows) {
    const tokens = row.opening_name.split(/\s+/)
    let bestPrefix: string | null = null
    for (let n = Math.min(tokens.length, 5); n >= 2; n--) {
      const prefix = tokens.slice(0, n).join(' ')
      if ((prefixCount.get(prefix) ?? 0) >= 2) {
        bestPrefix = prefix
        break
      }
    }
    if (bestPrefix) {
      if (!grouped.has(bestPrefix)) grouped.set(bestPrefix, [])
      grouped.get(bestPrefix)!.push(row)
    } else {
      singletons.push(row)
    }
  }

  const groups: Array<{ key: string; label: string; items: OpeningStat[] }> = []
  for (const [prefix, items] of grouped) {
    groups.push({ key: `name:${prefix}`, label: prefix, items })
  }
  for (const s of singletons) {
    groups.push({
      key: `single:${s.opening_name}-${s.color}-${s.eco ?? ''}`,
      label: s.opening_name,
      items: [s],
    })
  }
  groups.sort((a, b) => aggregate(b.items).games - aggregate(a.items).games)
  return groups
}

function buildEcoGroups(rows: OpeningStat[]): Array<{ key: string; label: string; items: OpeningStat[] }> {
  const byEco = new Map<string, OpeningStat[]>()
  for (const row of rows) {
    const k = row.parent_eco ?? '?'
    if (!byEco.has(k)) byEco.set(k, [])
    byEco.get(k)!.push(row)
  }
  const out: Array<{ key: string; label: string; items: OpeningStat[] }> = []
  for (const [eco, items] of byEco) {
    const label = eco === '?' ? 'Unclassified' : `${eco} — ${ECO_FAMILY_LABELS[eco] ?? eco}`
    out.push({ key: `eco:${eco}`, label, items })
  }
  out.sort((a, b) => {
    const [ak, bk] = [a.key.split(':')[1], b.key.split(':')[1]]
    if (ak === '?') return 1
    if (bk === '?') return -1
    return ak.localeCompare(bk)
  })
  return out
}

/**
 * The "Win Rates" tab of the Openings umbrella page. Lives inside the
 * Openings.tsx shell — no BackButton or h1 here; the umbrella owns those
 * and supplies the active range filter via props.
 */
export default function OpeningStats({ playerId, range }: { playerId: string; range: TimeRange }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [minGames, setMinGames] = useState<MinGames>(2)
  const [groupMode, setGroupMode] = useState<GroupMode>(() => {
    const stored = localStorage.getItem(GROUP_STORAGE_KEY)
    return (stored === 'eco' || stored === 'name' || stored === 'flat') ? stored : 'flat'
  })

  useEffect(() => {
    localStorage.setItem(GROUP_STORAGE_KEY, groupMode)
  }, [groupMode])

  const query = useQuery({
    queryKey: ['openingStats', playerId, range, minGames],
    queryFn: () => getOpeningStats(playerId, minGames, undefined, range),
  })

  const trendQuery = useQuery({
    queryKey: ['accuracyTrend', playerId, range],
    queryFn: () => getAccuracyTrend(playerId, undefined, range),
  })

  const accuracyByGameId = useMemo(() => {
    const m = new Map<string, AccuracyPoint>()
    for (const p of trendQuery.data ?? []) m.set(p.game_id, p)
    return m
  }, [trendQuery.data])

  const data = query.data ?? []
  const sorted = useMemo(
    () => [...data]
      .filter((o) => o.opening_name && o.opening_name.toLowerCase() !== 'undefined')
      .sort((a, b) => b.games - a.games),
    [data],
  )

  const groups = useMemo(() => {
    if (groupMode === 'flat') return null
    if (groupMode === 'eco') return buildEcoGroups(sorted)
    return buildNameGroups(sorted)
  }, [sorted, groupMode])

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading…</p>
  if (query.isError) return <QueryError error={query.error} />


  const chartData = sorted.slice(0, CHART_TOP_N).map((o) => ({
    ...o,
    label: `${truncate(o.opening_name, MAX_LABEL_CHARS)} ${colorIcon(o.color)}`,
    barLabel: `${o.games}g · ${Math.round(o.score_rate * 100)}%`,
  }))

  const chartHeight = Math.max(240, chartData.length * 32 + 40)

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Group
        </span>
        <GroupToggle value={groupMode} onChange={setGroupMode} />

        <span className="text-xs uppercase tracking-wide ml-3" style={{ color: 'var(--text-muted)' }}>
          Min games per branch
        </span>
        <div className="inline-flex rounded border overflow-hidden text-xs" style={{ borderColor: 'var(--border)' }}>
          {MIN_GAMES_OPTIONS.map((n) => (
            <button
              key={n}
              onClick={() => setMinGames(n)}
              className={`px-2.5 py-1 transition-colors ${minGames === n ? 'font-semibold' : ''}`}
              style={{
                background: minGames === n ? 'var(--accent-bg, #4f46e5)' : 'transparent',
                color: minGames === n ? 'white' : 'var(--text-secondary)',
              }}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {sorted.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          {minGames > 1
            ? `No openings with at least ${minGames} games in this range. Try lowering the threshold.`
            : "No openings to show yet. Either no analyzed games in this range, or chess.com didn't tag the openings."}
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
                if (!o) return [`${Math.round(Number(_v) * 100)}%`, 'Score']
                return [
                  `${Math.round(o.score_rate * 100)}% · ${o.games}g (+${o.wins} =${o.draws} -${o.losses}) · ${o.avg_cpl} CPL`,
                  o.opening_name,
                ]
              }}
            />
            <Bar dataKey="score_rate" radius={[0, 4, 4, 0]}>
              {chartData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={
                    entry.score_rate >= 0.6
                      ? '#22c55e'
                      : entry.score_rate >= 0.4
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
        {groups === null
          ? sorted.map((o) => (
              <OpeningRow
                key={`${o.opening_name}-${o.color}-${o.eco ?? ''}`}
                opening={o}
                isOpen={expanded === `${o.opening_name}-${o.color}-${o.eco ?? ''}`}
                onToggle={() =>
                  setExpanded(
                    expanded === `${o.opening_name}-${o.color}-${o.eco ?? ''}`
                      ? null
                      : `${o.opening_name}-${o.color}-${o.eco ?? ''}`,
                  )
                }
                playerId={playerId}
                range={range}
                accuracyByGameId={accuracyByGameId}
              />
            ))
          : groups.map((g) => (
              <GroupBlock
                key={g.key}
                label={g.label}
                items={g.items}
                isOpen={expandedGroups.has(g.key)}
                onToggle={() => toggleGroup(g.key)}
                expandedRowKey={expanded}
                setExpandedRowKey={setExpanded}
                playerId={playerId}
                range={range}
                accuracyByGameId={accuracyByGameId}
              />
            ))}
      </div>
      </>
      )}
    </>
  )
}

function GroupToggle({ value, onChange }: { value: GroupMode; onChange: (v: GroupMode) => void }) {
  const opts: { v: GroupMode; label: string }[] = [
    { v: 'flat', label: 'Flat' },
    { v: 'eco', label: 'ECO' },
    { v: 'name', label: 'Name' },
  ]
  return (
    <div className="inline-flex rounded border overflow-hidden text-xs" style={{ borderColor: 'var(--border)' }}>
      {opts.map((o) => (
        <button
          key={o.v}
          onClick={() => onChange(o.v)}
          className={`px-2.5 py-1 transition-colors ${value === o.v ? 'font-semibold' : ''}`}
          style={{
            background: value === o.v ? 'var(--accent-bg, #4f46e5)' : 'transparent',
            color: value === o.v ? 'white' : 'var(--text-secondary)',
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function OpeningRow({
  opening,
  isOpen,
  onToggle,
  playerId,
  range,
  accuracyByGameId,
  depth = 0,
}: {
  opening: OpeningStat
  isOpen: boolean
  onToggle: () => void
  playerId: string
  range: TimeRange
  accuracyByGameId: Map<string, AccuracyPoint>
  depth?: number
}) {
  return (
    <div
      className="rounded-lg border"
      style={{
        background: 'var(--bg-card)',
        borderColor: 'var(--border)',
        marginLeft: depth * 12,
      }}
    >
      <button
        onClick={onToggle}
        className="w-full p-3 flex items-center justify-between text-left hover:opacity-90"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-lg">{colorIcon(opening.color)}</span>
          <div className="min-w-0">
            <span className="text-sm truncate" style={{ color: 'var(--text-primary)' }}>
              {opening.opening_name}
            </span>
            {opening.eco && (
              <span className="text-xs ml-2" style={{ color: 'var(--text-muted)' }}>
                {opening.eco}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span style={{ color: 'var(--text-muted)' }}>{opening.games} games</span>
          <span style={{ color: 'var(--text-muted)' }}>{opening.avg_cpl} CPL</span>
          <WdlBar wins={opening.wins} draws={opening.draws} losses={opening.losses} />
          <span className={`font-bold w-12 text-right ${scoreColor(opening.score_rate)}`}>
            {Math.round(opening.score_rate * 100)}%
          </span>
          <span className="text-xs w-16 text-right" style={{ color: 'var(--text-muted)' }}>
            {relativeDate(opening.last_played_at)}
          </span>
          <span className="w-5 text-center" style={{ color: 'var(--text-muted)' }} aria-hidden>
            {isOpen ? '▴' : '▾'}
          </span>
        </div>
      </button>
      {isOpen && (
        <OpeningGames
          playerId={playerId}
          opening={opening}
          range={range}
          accuracyByGameId={accuracyByGameId}
        />
      )}
    </div>
  )
}

function GroupBlock({
  label,
  items,
  isOpen,
  onToggle,
  expandedRowKey,
  setExpandedRowKey,
  playerId,
  range,
  accuracyByGameId,
}: {
  label: string
  items: OpeningStat[]
  isOpen: boolean
  onToggle: () => void
  expandedRowKey: string | null
  setExpandedRowKey: (k: string | null) => void
  playerId: string
  range: TimeRange
  accuracyByGameId: Map<string, AccuracyPoint>
}) {
  const agg = aggregate(items)
  if (items.length === 1) {
    const o = items[0]
    const key = `${o.opening_name}-${o.color}-${o.eco ?? ''}`
    return (
      <OpeningRow
        opening={o}
        isOpen={expandedRowKey === key}
        onToggle={() => setExpandedRowKey(expandedRowKey === key ? null : key)}
        playerId={playerId}
        range={range}
        accuracyByGameId={accuracyByGameId}
      />
    )
  }

  return (
    <div
      className="rounded-lg border"
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
    >
      <button
        onClick={onToggle}
        className="w-full p-3 flex items-center justify-between text-left hover:opacity-90"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-5 text-center" style={{ color: 'var(--text-muted)' }} aria-hidden>
            {isOpen ? '▾' : '▸'}
          </span>
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {label}
          </span>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            ({items.length} openings)
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span style={{ color: 'var(--text-muted)' }}>{agg.games} games</span>
          <span style={{ color: 'var(--text-muted)' }}>{agg.avg_cpl.toFixed(1)} CPL</span>
          <WdlBar wins={agg.wins} draws={agg.draws} losses={agg.losses} />
          <span className={`font-bold w-12 text-right ${scoreColor(agg.score_rate)}`}>
            {Math.round(agg.score_rate * 100)}%
          </span>
          <span className="w-16" />
          <span className="w-5" />
        </div>
      </button>
      {isOpen && (
        <div className="px-2 pb-2 space-y-1.5 border-t pt-2" style={{ borderColor: 'var(--border)' }}>
          {items.map((o) => {
            const key = `${o.opening_name}-${o.color}-${o.eco ?? ''}`
            return (
              <OpeningRow
                key={key}
                opening={o}
                isOpen={expandedRowKey === key}
                onToggle={() => setExpandedRowKey(expandedRowKey === key ? null : key)}
                playerId={playerId}
                range={range}
                accuracyByGameId={accuracyByGameId}
                depth={1}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function OpeningGames({
  playerId,
  opening,
  range,
  accuracyByGameId,
}: {
  playerId: string
  opening: OpeningStat
  range: TimeRange
  accuracyByGameId: Map<string, AccuracyPoint>
}) {
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
      {games.map((g) => {
        const ap = accuracyByGameId.get(g.id)
        return (
          <Link
            key={g.id}
            to={`/games/${g.id}`}
            state={{ from: `/players/${playerId}/openings?view=list` }}
            className="block rounded px-2 py-1.5 text-xs flex items-center justify-between hover:bg-gray-700/50"
            style={{ color: 'var(--text-secondary)' }}
          >
            <span className="truncate">
              {colorIcon(g.user_color)}{' '}
              {g.white_username} vs {g.black_username}
            </span>
            <span className="flex items-center gap-3 flex-shrink-0">
              {ap && (
                <>
                  <span style={{ color: 'var(--text-muted)' }}>
                    {ap.accuracy.toFixed(1)}% acc
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>
                    {ap.avg_cpl.toFixed(1)} CPL
                  </span>
                </>
              )}
              <span style={{ color: 'var(--text-muted)' }}>
                {new Date(g.played_at).toLocaleDateString()}
              </span>
              <span
                className={resultColor(g.user_result)}
                style={g.user_result === 'draw' ? { color: 'var(--text-muted)' } : undefined}
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
