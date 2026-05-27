import { useState, useRef, useEffect, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import BackButton from '../components/BackButton'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { listGames, type GameListParams } from '../api/client'

const TIME_CLASSES = [
  { value: 'bullet', label: 'Bullet', icon: '⚡' },
  { value: 'blitz', label: 'Blitz', icon: '🔥' },
  { value: 'rapid', label: 'Rapid', icon: '⏱' },
  { value: 'classical', label: 'Classical', icon: '🏛' },
  { value: 'daily', label: 'Daily', icon: '📅' },
]

const COLORS = [
  { value: 'white', label: 'White', icon: '♔' },
  { value: 'black', label: 'Black', icon: '♚' },
]

const RESULTS = [
  { value: 'win', label: 'Win', icon: '✓', color: 'text-green-400' },
  { value: 'loss', label: 'Loss', icon: '✕', color: 'text-red-400' },
  { value: 'draw', label: 'Draw', icon: '½', color: 'text-gray-400' },
]

const PAGE_SIZE = 25

type Sort = NonNullable<GameListParams['sort']>
type Order = NonNullable<GameListParams['order']>

function dateToIso(d: string): string | undefined {
  if (!d) return undefined
  return new Date(d + 'T00:00:00').toISOString()
}

function endOfDayIso(d: string): string | undefined {
  if (!d) return undefined
  return new Date(d + 'T23:59:59.999').toISOString()
}

function parseNum(v: string): number | undefined {
  const n = parseInt(v, 10)
  return Number.isFinite(n) ? n : undefined
}

export default function GameList() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()

  // Filter state — stored in URL so refresh / share works.
  const [page, setPage] = useState<number>(() => parseInt(searchParams.get('page') || '1', 10) || 1)
  const [timeClasses, setTimeClasses] = useState<string[]>(() =>
    searchParams.get('time') ? searchParams.get('time')!.split(',') : [],
  )
  const [colors, setColors] = useState<string[]>(() =>
    searchParams.get('color') ? searchParams.get('color')!.split(',') : [],
  )
  const [results, setResults] = useState<string[]>(() =>
    searchParams.get('result') ? searchParams.get('result')!.split(',') : [],
  )
  const [opening, setOpening] = useState<string>(searchParams.get('opening') || '')
  const [oppMin, setOppMin] = useState<string>(searchParams.get('oppMin') || '')
  const [oppMax, setOppMax] = useState<string>(searchParams.get('oppMax') || '')
  const [meMin, setMeMin] = useState<string>(searchParams.get('meMin') || '')
  const [meMax, setMeMax] = useState<string>(searchParams.get('meMax') || '')
  const [from, setFrom] = useState<string>(searchParams.get('from') || '')
  const [to, setTo] = useState<string>(searchParams.get('to') || '')
  const [analyzed, setAnalyzed] = useState<'all' | 'yes' | 'no'>(
    (searchParams.get('analyzed') as 'all' | 'yes' | 'no') || 'all',
  )
  const [sort, setSort] = useState<Sort>((searchParams.get('sort') as Sort) || 'played_at')
  const [order, setOrder] = useState<Order>((searchParams.get('order') as Order) || 'desc')

  // Backend supports a single value per filter; for multi-select we fall back
  // to client-side filtering of the current page when more than one is picked.
  // For single-select we just push the value through.
  const apiTimeClass = timeClasses.length === 1 ? timeClasses[0] : undefined
  const apiColor = colors.length === 1 ? colors[0] : undefined
  const apiResult = results.length === 1 ? results[0] : undefined

  const offset = (page - 1) * PAGE_SIZE

  // Persist URL state whenever filters or page change.
  useEffect(() => {
    const next = new URLSearchParams()
    if (page > 1) next.set('page', String(page))
    if (timeClasses.length) next.set('time', timeClasses.join(','))
    if (colors.length) next.set('color', colors.join(','))
    if (results.length) next.set('result', results.join(','))
    if (opening) next.set('opening', opening)
    if (oppMin) next.set('oppMin', oppMin)
    if (oppMax) next.set('oppMax', oppMax)
    if (meMin) next.set('meMin', meMin)
    if (meMax) next.set('meMax', meMax)
    if (from) next.set('from', from)
    if (to) next.set('to', to)
    if (analyzed !== 'all') next.set('analyzed', analyzed)
    if (sort !== 'played_at') next.set('sort', sort)
    if (order !== 'desc') next.set('order', order)
    setSearchParams(next, { replace: true })
  }, [
    page, timeClasses, colors, results, opening,
    oppMin, oppMax, meMin, meMax, from, to, analyzed, sort, order,
    setSearchParams,
  ])

  const apiParams: GameListParams = useMemo(() => ({
    limit: PAGE_SIZE,
    offset,
    time_class: apiTimeClass,
    user_color: apiColor,
    user_result: apiResult,
    opening_search: opening || undefined,
    opp_rating_min: parseNum(oppMin),
    opp_rating_max: parseNum(oppMax),
    user_rating_min: parseNum(meMin),
    user_rating_max: parseNum(meMax),
    played_from: dateToIso(from),
    played_to: endOfDayIso(to),
    analyzed: analyzed === 'yes' ? true : analyzed === 'no' ? false : undefined,
    sort,
    order,
  }), [
    offset, apiTimeClass, apiColor, apiResult, opening,
    oppMin, oppMax, meMin, meMax, from, to, analyzed, sort, order,
  ])

  const query = useQuery({
    queryKey: ['games', id, apiParams],
    queryFn: () => listGames(id!, apiParams),
    enabled: !!id,
    placeholderData: keepPreviousData,
  })

  const total = query.data?.total ?? 0
  const rawGames = query.data?.games ?? []
  // Apply client-side filtering only when the user has multiple values picked
  // for a filter the API can't natively handle.
  const games = rawGames.filter((g) => {
    if (timeClasses.length > 1 && !timeClasses.includes(g.time_class)) return false
    if (colors.length > 1 && !colors.includes(g.user_color)) return false
    if (results.length > 1 && !results.includes(g.user_result)) return false
    return true
  })

  const hasMultiFilters =
    timeClasses.length > 1 || colors.length > 1 || results.length > 1
  // When multi-select is active we can't trust server total — show a hint.

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const resetPage = () => setPage(1)
  const clearAll = () => {
    setTimeClasses([]); setColors([]); setResults([])
    setOpening(''); setOppMin(''); setOppMax('')
    setMeMin(''); setMeMax(''); setFrom(''); setTo('')
    setAnalyzed('all'); setSort('played_at'); setOrder('desc')
    setPage(1)
  }

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1
        className="text-2xl font-bold mb-4 flex items-center gap-2"
        style={{ color: 'var(--text-primary)' }}
      >
        <span>♟</span> Games
      </h1>

      {/* Quick filters (multi-select chips) */}
      <div className="flex gap-2 mb-3 flex-wrap items-center">
        <MultiSelect
          label="Time"
          options={TIME_CLASSES}
          selected={timeClasses}
          onChange={(v) => { setTimeClasses(v); resetPage() }}
        />
        <MultiSelect
          label="Color"
          options={COLORS}
          selected={colors}
          onChange={(v) => { setColors(v); resetPage() }}
        />
        <MultiSelect
          label="Result"
          options={RESULTS}
          selected={results}
          onChange={(v) => { setResults(v); resetPage() }}
        />
        <Select
          label="Analyzed"
          value={analyzed}
          onChange={(v) => { setAnalyzed(v as 'all' | 'yes' | 'no'); resetPage() }}
          options={[
            { value: 'all', label: 'All' },
            { value: 'yes', label: 'Analyzed' },
            { value: 'no', label: 'Not yet' },
          ]}
        />
        <span className="text-xs ml-2" style={{ color: 'var(--text-muted)' }}>Sort by</span>
        <Select
          label=""
          value={sort}
          onChange={(v) => { setSort(v as Sort); resetPage() }}
          options={[
            { value: 'played_at', label: 'Date' },
            { value: 'opp_rating', label: 'Opp rating' },
            { value: 'user_rating', label: 'Your rating' },
            { value: 'ply_count', label: 'Length' },
          ]}
        />
        <Select
          label=""
          value={order}
          onChange={(v) => { setOrder(v as Order); resetPage() }}
          options={[
            { value: 'desc', label: '↓' },
            { value: 'asc', label: '↑' },
          ]}
        />
        <button
          onClick={clearAll}
          className="px-3 py-1.5 text-xs rounded-lg border hover:border-indigo-500"
          style={{
            background: 'var(--bg-card)',
            borderColor: 'var(--border)',
            color: 'var(--text-secondary)',
          }}
        >
          Clear all
        </button>
      </div>

      {/* Advanced filters (Elo + dates + opening) */}
      <div
        className="rounded-lg border p-3 mb-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
        style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
      >
        <RangeRow
          label="Opponent Elo"
          min={oppMin} max={oppMax}
          onMin={(v) => { setOppMin(v); resetPage() }}
          onMax={(v) => { setOppMax(v); resetPage() }}
          minPlaceholder="any" maxPlaceholder="any"
        />
        <RangeRow
          label="Your Elo"
          min={meMin} max={meMax}
          onMin={(v) => { setMeMin(v); resetPage() }}
          onMax={(v) => { setMeMax(v); resetPage() }}
          minPlaceholder="any" maxPlaceholder="any"
        />
        <DateRangeRow
          label="Date range"
          from={from} to={to}
          onFrom={(v) => { setFrom(v); resetPage() }}
          onTo={(v) => { setTo(v); resetPage() }}
        />
        <div className="sm:col-span-2 lg:col-span-3">
          <label
            className="text-xs uppercase tracking-wide block mb-1"
            style={{ color: 'var(--text-muted)' }}
          >
            Opening contains
          </label>
          <input
            value={opening}
            onChange={(e) => { setOpening(e.target.value); resetPage() }}
            placeholder="e.g. Caro-Kann, Sicilian, Catalan…"
            className="w-full px-3 py-1.5 text-sm rounded-md border"
            style={{
              background: 'var(--bg-primary)',
              borderColor: 'var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
      </div>

      {query.isLoading && !query.isPlaceholderData && (
        <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
      )}

      {query.data && (
        <>
          <div className="flex items-center justify-between mb-3 text-sm">
            <span style={{ color: 'var(--text-secondary)' }}>
              {total.toLocaleString()} game{total !== 1 ? 's' : ''} match.{' '}
              {total > 0 && (
                <>
                  Showing{' '}
                  <span style={{ color: 'var(--text-primary)' }}>
                    {(offset + 1).toLocaleString()}–
                    {Math.min(offset + games.length, total).toLocaleString()}
                  </span>
                  .
                </>
              )}
              {hasMultiFilters && (
                <span className="ml-2" style={{ color: 'var(--text-muted)' }}>
                  (extra multi-filters applied on this page)
                </span>
              )}
            </span>
            <Pagination
              page={page}
              totalPages={totalPages}
              onChange={setPage}
              compact
            />
          </div>

          <div className="space-y-1.5">
            {games.map((g) => {
              const oppRating = g.user_color === 'white' ? g.black_rating : g.white_rating
              const myRating = g.user_color === 'white' ? g.white_rating : g.black_rating
              return (
                <Link
                  key={g.id}
                  to={`/games/${g.id}`}
                  state={{ from: `/players/${id}/games?${searchParams.toString()}` }}
                  className="block rounded-lg p-3 border hover:border-indigo-500 transition-colors"
                  style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
                >
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{g.user_color === 'white' ? '♔' : '♚'}</span>
                      <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                        {g.white_username}
                        {g.white_rating ? ` (${g.white_rating})` : ''} vs{' '}
                        {g.black_username}
                        {g.black_rating ? ` (${g.black_rating})` : ''}
                      </span>
                      {!g.analyzed_at && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded ml-1"
                          style={{
                            background: 'var(--bg-hover)',
                            color: 'var(--text-muted)',
                          }}
                        >
                          not analyzed
                        </span>
                      )}
                    </div>
                    <span
                      className={`text-sm font-medium ${
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
                  <div
                    className="flex justify-between text-xs mt-1 ml-7"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    <span className="flex items-center gap-2">
                      <span>{g.opening_name || g.eco || '?'}</span>
                      <span style={{ color: 'var(--text-muted)' }}>|</span>
                      <span>
                        {TIME_CLASSES.find((t) => t.value === g.time_class)?.icon} {g.time_class} {g.time_control}
                      </span>
                      {(myRating || oppRating) && (
                        <>
                          <span style={{ color: 'var(--text-muted)' }}>|</span>
                          <span>
                            you {myRating ?? '?'} vs {oppRating ?? '?'}
                          </span>
                        </>
                      )}
                    </span>
                    <span>{new Date(g.played_at).toLocaleDateString()}</span>
                  </div>
                </Link>
              )
            })}
          </div>

          {games.length === 0 && (
            <p style={{ color: 'var(--text-muted)' }}>
              No games match the current filters.
            </p>
          )}

          {totalPages > 1 && (
            <div className="flex justify-center mt-5">
              <Pagination page={page} totalPages={totalPages} onChange={setPage} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

function MultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string
  options: { value: string; label: string; icon: string; color?: string }[]
  selected: string[]
  onChange: (values: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const toggle = (value: string) => {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value]
    )
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`px-3 py-1.5 text-sm rounded-lg border flex items-center gap-1.5
          ${selected.length > 0
            ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300'
            : ''
          } hover:border-indigo-400`}
        style={
          selected.length === 0
            ? { background: 'var(--bg-card)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }
            : undefined
        }
      >
        {label}
        {selected.length > 0 && (
          <span className="bg-indigo-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
            {selected.length}
          </span>
        )}
        <span className="text-xs ml-0.5">▾</span>
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 rounded-lg shadow-xl z-50 min-w-[140px] border"
          style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
        >
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => toggle(opt.value)}
              className="w-full px-3 py-2 text-sm text-left flex items-center gap-2 hover:bg-gray-700/50"
              style={{
                color: selected.includes(opt.value)
                  ? 'var(--text-primary)'
                  : 'var(--text-secondary)',
              }}
            >
              <span
                className="w-3.5 h-3.5 border rounded flex items-center justify-center text-[10px]"
                style={
                  selected.includes(opt.value)
                    ? { background: '#6366f1', borderColor: '#6366f1', color: 'white' }
                    : { borderColor: 'var(--border)' }
                }
              >
                {selected.includes(opt.value) ? '✓' : ''}
              </span>
              <span>{opt.icon}</span>
              <span className={opt.color}>{opt.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label?: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="inline-flex items-center gap-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="px-2 py-1 text-sm rounded-md border"
        style={{
          background: 'var(--bg-card)',
          borderColor: 'var(--border)',
          color: 'var(--text-primary)',
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  )
}

function RangeRow({
  label,
  min,
  max,
  onMin,
  onMax,
  minPlaceholder,
  maxPlaceholder,
}: {
  label: string
  min: string
  max: string
  onMin: (v: string) => void
  onMax: (v: string) => void
  minPlaceholder: string
  maxPlaceholder: string
}) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wide block mb-1" style={{ color: 'var(--text-muted)' }}>
        {label}
      </label>
      <div className="flex gap-2 items-center">
        <input
          type="number"
          inputMode="numeric"
          value={min}
          onChange={(e) => onMin(e.target.value)}
          placeholder={minPlaceholder}
          className="w-full px-2 py-1 text-sm rounded-md border"
          style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
        />
        <span style={{ color: 'var(--text-muted)' }}>—</span>
        <input
          type="number"
          inputMode="numeric"
          value={max}
          onChange={(e) => onMax(e.target.value)}
          placeholder={maxPlaceholder}
          className="w-full px-2 py-1 text-sm rounded-md border"
          style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
        />
      </div>
    </div>
  )
}

function DateRangeRow({
  label,
  from,
  to,
  onFrom,
  onTo,
}: {
  label: string
  from: string
  to: string
  onFrom: (v: string) => void
  onTo: (v: string) => void
}) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wide block mb-1" style={{ color: 'var(--text-muted)' }}>
        {label}
      </label>
      <div className="flex gap-2 items-center">
        <input
          type="date"
          value={from}
          onChange={(e) => onFrom(e.target.value)}
          className="w-full px-2 py-1 text-sm rounded-md border"
          style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
        />
        <span style={{ color: 'var(--text-muted)' }}>—</span>
        <input
          type="date"
          value={to}
          onChange={(e) => onTo(e.target.value)}
          className="w-full px-2 py-1 text-sm rounded-md border"
          style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
        />
      </div>
    </div>
  )
}

function Pagination({
  page,
  totalPages,
  onChange,
  compact = false,
}: {
  page: number
  totalPages: number
  onChange: (p: number) => void
  compact?: boolean
}) {
  if (totalPages <= 1) return null

  const go = (p: number) => onChange(Math.max(1, Math.min(totalPages, p)))

  // Build a compact window of page numbers around the current page.
  const window: (number | '…')[] = []
  const add = (n: number) => {
    if (!window.includes(n)) window.push(n)
  }
  add(1)
  for (let i = page - 1; i <= page + 1; i++) {
    if (i > 1 && i < totalPages) add(i)
  }
  if (totalPages > 1) add(totalPages)

  // Insert ellipses where there is a gap.
  const withGaps: (number | '…')[] = []
  for (let i = 0; i < window.length; i++) {
    if (i > 0) {
      const prev = window[i - 1]
      const cur = window[i]
      if (typeof prev === 'number' && typeof cur === 'number' && cur - prev > 1) {
        withGaps.push('…')
      }
    }
    withGaps.push(window[i])
  }

  const btnClass = (active: boolean, disabled: boolean) =>
    `px-2.5 py-1 text-xs rounded-md border min-w-[28px] text-center ${
      active ? 'bg-indigo-600 text-white border-indigo-500' : ''
    } ${disabled ? 'opacity-40' : 'hover:border-indigo-500'}`

  const inactiveStyle = {
    background: 'var(--bg-card)',
    borderColor: 'var(--border)',
    color: 'var(--text-secondary)',
  }

  return (
    <div className={`flex items-center gap-1 ${compact ? '' : 'flex-wrap'}`}>
      <button
        onClick={() => go(page - 1)}
        disabled={page <= 1}
        className={btnClass(false, page <= 1)}
        style={inactiveStyle}
      >
        ‹
      </button>
      {withGaps.map((p, i) =>
        p === '…' ? (
          <span key={`gap-${i}`} className="px-1" style={{ color: 'var(--text-muted)' }}>…</span>
        ) : (
          <button
            key={p}
            onClick={() => go(p)}
            className={btnClass(p === page, false)}
            style={p === page ? undefined : inactiveStyle}
          >
            {p}
          </button>
        ),
      )}
      <button
        onClick={() => go(page + 1)}
        disabled={page >= totalPages}
        className={btnClass(false, page >= totalPages)}
        style={inactiveStyle}
      >
        ›
      </button>
    </div>
  )
}
