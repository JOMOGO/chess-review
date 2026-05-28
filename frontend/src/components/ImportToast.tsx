import { useEffect, useState, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getImportStatus, getHealth } from '../api/client'
import { getStoredImport, setStoredImport, onImportChanged, isToastVisible, setToastVisible } from '../lib/storage'
import type { StoredImport } from '../lib/storage'

export default function ImportToast() {
  const [stored, setStored] = useState<StoredImport | null>(getStoredImport)
  const [visible, setVisible] = useState(isToastVisible)
  const queryClient = useQueryClient()
  const prevPositions = useRef(0)
  const prevTime = useRef(0)
  // Tracks which job the baseline above belongs to. When stored.jobId
  // changes, the speed-calc effect notices and re-anchors the baseline
  // to "now" so the first measurement of a new job isn't computed
  // against the previous job's time window.
  const trackedJobId = useRef<string | null>(null)

  useEffect(() => onImportChanged(() => {
    setStored(getStoredImport())
    setVisible(isToastVisible())
  }), [])

  const query = useQuery({
    queryKey: ['importStatus', stored?.playerId],
    queryFn: () => getImportStatus(stored!.playerId),
    enabled: !!stored,
    refetchInterval: (q) => {
      const s = q.state.data?.status
      if (s === 'done' || s === 'failed') return false
      return 1000
    },
  })

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 10000,
  })

  const status = query.data
  const health = healthQuery.data

  const isDone = status?.status === 'done'
  const isFailed = status?.status === 'failed'
  const isActive = stored && status && !isDone && !isFailed

  useEffect(() => {
    if (!stored || !status) return
    queryClient.invalidateQueries({ queryKey: ['player', stored.playerId] })
    queryClient.invalidateQueries({ queryKey: ['games', stored.playerId] })
  }, [status?.imported_games, status?.analyzed_positions, stored?.playerId, queryClient])

  useEffect(() => {
    if (isDone) {
      const t = setTimeout(() => setStoredImport(null), 8000)
      return () => clearTimeout(t)
    }
  }, [isDone])

  // Calculate speed (positions/sec). Single effect handles both
  // "anchor baseline on a new job" and "compute delta on each tick" so we
  // never accidentally measure against the wrong job's window — that bug
  // showed up as ~0.2 pos/s when the app had been open for a long time
  // before the import was kicked off.
  const [speed, setSpeed] = useState(0)
  useEffect(() => {
    if (!status || !status.analyzed_positions) return
    const now = Date.now()
    const jobId = stored?.jobId ?? null
    if (trackedJobId.current !== jobId) {
      trackedJobId.current = jobId
      prevTime.current = now
      prevPositions.current = status.analyzed_positions
      return
    }
    const dt = (now - prevTime.current) / 1000
    const dp = status.analyzed_positions - prevPositions.current
    if (dt > 0 && dp > 0) {
      setSpeed(Math.round(dp / dt * 10) / 10)
    }
    prevPositions.current = status.analyzed_positions
    prevTime.current = now
  }, [status?.analyzed_positions, stored?.jobId])

  const importing = status && status.total_games > 0 && status.imported_games < status.total_games
  const analyzing = status && status.analyzed_positions > 0 || (status && status.analyzed_games > 0)

  // Overall progress: weighted average of import (30%) and analysis (70%)
  const importPct = status && status.total_games > 0
    ? status.imported_games / status.total_games : 0
  const analysisPct = status && status.total_positions > 0
    ? status.analyzed_positions / status.total_positions : 0
  const progress = status && status.total_games > 0
    ? Math.round((importing ? importPct * 30 + analysisPct * 70 : analysisPct * 100))
    : status && status.total_games > 0
      ? Math.round((status.imported_games / status.total_games) * 100)
      : 0

  // ETA calculation
  const remaining = analyzing && speed > 0 && status
    ? Math.round((status.total_positions - status.analyzed_positions) / speed)
    : 0
  const etaStr = remaining > 0
    ? remaining > 3600
      ? `~${Math.round(remaining / 3600)}h left`
      : remaining > 60
        ? `~${Math.round(remaining / 60)}m left`
        : `~${remaining}s left`
    : ''

  const engineOk = health?.engine && health.engine !== 'unavailable'

  // Nothing to show
  if (!stored && engineOk) return null
  if (!stored && !health) return null

  // Minimized — don't render (navbar icon handles reopening)
  if (!visible && stored) return null

  return (
    <div className="fixed top-16 right-4 bg-[#16162a] border border-gray-700 rounded-lg shadow-xl p-3 w-80 z-50 space-y-2">
      {/* Engine status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full ${engineOk ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-gray-400">
            {engineOk ? health!.engine : 'Engine unavailable'}
          </span>
        </div>
        {stored && (
          <button onClick={() => setToastVisible(false)}
            className="text-gray-500 hover:text-white text-xs" title="Minimize">✕</button>
        )}
      </div>

      {/* Pending */}
      {stored && !status && (
        <div className="text-white text-sm font-medium flex items-center gap-1.5">
          ♟ Connecting to chess.com...
        </div>
      )}

      {/* Active job */}
      {isActive && (
        <>
          {/* Step 1: Download games from chess.com */}
          <StepBlock
            icon="♟"
            title="Download games"
            subtitle="Fetching from chess.com"
            current={status!.imported_games}
            total={status!.total_games}
            active={!!importing}
            done={!importing}
          />

          {/* Step 2: Stockfish analysis (runs concurrently).
              Once every imported game has entered analysis, switch to a
              "Finalizing..." label — analyzed_games + 1 would otherwise
              read "Game N+1 / N" which is nonsense, and the last in-flight
              tasks can take a minute to drain after the counter saturates.
            */}
          <StepBlock
            icon="♛"
            title="Stockfish analysis"
            subtitle={(() => {
              const speedSuffix = speed > 0 ? ` · ${speed} pos/s` : ''
              const finished =
                status!.imported_games > 0
                && status!.analyzed_games >= status!.imported_games
              if (finished) return `Finalizing${speedSuffix}`
              if (status!.analyzed_games > 0 || status!.analyzed_positions > 0) {
                const slash = status!.imported_games > 0
                  ? ' / ' + status!.imported_games : ''
                return `Game ${status!.analyzed_games + 1}${slash}${speedSuffix}`
              }
              return importing ? 'Starting soon...' : 'Starting...'
            })()}
            current={status!.analyzed_positions}
            total={status!.total_positions || 0}
            active={!isDone}
            done={isDone}
          />

          {/* Source breakdown */}
          {analyzing && status!.analyzed_positions > 0 && (
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] pl-5">
              {status!.cache_hits > 0 && (
                <span className="text-green-400/80" title="Already in local database">
                  ⚡ {status!.cache_hits.toLocaleString()} cached
                </span>
              )}
              {status!.cloud_hits > 0 && (
                <span className="text-blue-400/80" title="Lichess cloud eval">
                  ☁ {status!.cloud_hits.toLocaleString()} cloud
                </span>
              )}
              {status!.tablebase_hits > 0 && (
                <span className="text-purple-400/80" title="Perfect endgame eval (≤7 pieces)">
                  ♚ {status!.tablebase_hits.toLocaleString()} tablebase
                </span>
              )}
              {status!.engine_hits > 0 && (
                <span className="text-orange-400/80" title="Computed by local Stockfish">
                  ♜ {status!.engine_hits.toLocaleString()} Stockfish
                </span>
              )}
            </div>
          )}

          {/* Progress bar + ETA */}
          <div>
            <div className="w-full bg-gray-700 rounded-full h-1.5">
              <div className="bg-indigo-500 h-1.5 rounded-full transition-all"
                style={{ width: `${progress}%` }} />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[10px] text-gray-500">{progress}%</span>
              {etaStr && <span className="text-[10px] text-gray-500">{etaStr}</span>}
            </div>
          </div>
        </>
      )}

      {stored && isFailed && status?.error && (
        <p className="text-red-400 text-xs line-clamp-2">✕ {status.error}</p>
      )}

      {stored && isDone && (
        <div className="bg-green-900/20 border border-green-800/30 rounded p-2">
          <div className="flex items-center gap-1.5 text-green-400 text-sm font-medium">
            <span>✓</span> Analysis complete
          </div>
          <p className="text-green-400/70 text-xs mt-0.5">
            {status!.imported_games} games · {status!.analyzed_positions.toLocaleString()} positions
          </p>
          <div className="flex flex-wrap gap-x-3 text-[10px] mt-1">
            {status!.cache_hits > 0 && <span className="text-green-400/60">⚡ {status!.cache_hits.toLocaleString()} cached</span>}
            {status!.cloud_hits > 0 && <span className="text-green-400/60">☁ {status!.cloud_hits.toLocaleString()} cloud</span>}
            {status!.tablebase_hits > 0 && <span className="text-green-400/60">♚ {status!.tablebase_hits.toLocaleString()} tablebase</span>}
            <span className="text-green-400/60">♜ {status!.engine_hits.toLocaleString()} Stockfish</span>
          </div>
        </div>
      )}
    </div>
  )
}

function StepBlock({ icon, title, subtitle, current, total, active, done }: {
  icon: string
  title: string
  subtitle: string
  current: number
  total: number
  active: boolean
  done: boolean
}) {
  const stateColor = done ? 'text-green-400' : active ? 'text-white' : 'text-gray-600'
  const subColor = done ? 'text-green-400/60' : active ? 'text-gray-400' : 'text-gray-600'

  return (
    <div className={`flex gap-2 ${done ? 'opacity-60' : ''}`}>
      <span className={`text-sm mt-0.5 ${stateColor}`}>
        {done ? '✓' : icon}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className={`text-sm font-medium ${stateColor}`}>{title}</span>
          {total > 0 && (
            <span className={`text-xs font-mono ${active ? 'text-indigo-400' : 'text-gray-500'}`}>
              {current.toLocaleString()} / {total.toLocaleString()}
            </span>
          )}
        </div>
        <p className={`text-[11px] ${subColor}`}>{subtitle}</p>
      </div>
    </div>
  )
}
