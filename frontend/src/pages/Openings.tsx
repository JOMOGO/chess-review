import { useParams, useSearchParams } from 'react-router-dom'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'
import { CPL_EXPLANATION } from '../lib/explanations'
import { useTimeRange } from '../lib/useTimeRange'
import OpeningStats from './OpeningStats'
import OpeningTree from './OpeningTree'

type View = 'list' | 'tree'

/**
 * Umbrella page for openings analysis. Owns the page header and the shared
 * controls (time range, view tabs); delegates the actual content to either
 * the win-rate list (OpeningStats) or the move tree (OpeningTree).
 *
 * The active tab is persisted to the URL via ?view=list|tree so the back
 * button works and links are shareable.
 */
export default function Openings() {
  const { id } = useParams<{ id: string }>()
  const [params, setParams] = useSearchParams()
  const view: View = params.get('view') === 'tree' ? 'tree' : 'list'
  const setView = (v: View) => {
    const next = new URLSearchParams(params)
    next.set('view', v)
    setParams(next, { replace: true })
  }
  const [range, setRange] = useTimeRange()

  if (!id) return null

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        ♝ Openings
      </h1>
      <p className="mb-4" style={{ color: 'var(--text-secondary)' }}>
        {view === 'list'
          ? 'Performance by named opening. Click a row to see those games.'
          : "Every move you've reached in the opening, stacked by shared lines. Click a node to expand."}
      </p>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <ViewTabs value={view} onChange={setView} />

        <span className="ml-4 text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Range
        </span>
        <TimeRangeFilter value={range} onChange={setRange} />

        <span className="ml-auto text-xs inline-flex items-center gap-3" style={{ color: 'var(--text-secondary)' }}>
          <span className="inline-flex items-center gap-1">
            What is CPL?
            <InfoTip>{CPL_EXPLANATION}</InfoTip>
          </span>
          <span className="inline-flex items-center gap-1">
            What is Score?
            <InfoTip label="Score rate">
              <strong>Score%</strong> = (wins + 0.5·draws) / games. Standard chess
              performance metric — a win counts 1 point, a draw 0.5, a loss 0.
              Matches FIDE, lichess, and chess.com.
            </InfoTip>
          </span>
        </span>
      </div>

      {view === 'list' ? (
        <OpeningStats playerId={id} range={range} />
      ) : (
        <OpeningTree playerId={id} range={range} />
      )}
    </div>
  )
}

function ViewTabs({ value, onChange }: { value: View; onChange: (v: View) => void }) {
  const opts: { v: View; label: string; desc: string }[] = [
    { v: 'list', label: 'Win Rates', desc: 'List by named opening' },
    { v: 'tree', label: 'Move Tree', desc: 'Tree of shared lines' },
  ]
  return (
    <div
      className="inline-flex rounded-lg border overflow-hidden"
      style={{ borderColor: 'var(--border)' }}
    >
      {opts.map((o) => (
        <button
          key={o.v}
          onClick={() => onChange(o.v)}
          className={`px-4 py-1.5 text-sm transition-colors ${value === o.v ? 'font-semibold' : ''}`}
          style={{
            background: value === o.v ? 'var(--accent-bg, #4f46e5)' : 'transparent',
            color: value === o.v ? 'white' : 'var(--text-secondary)',
          }}
          title={o.desc}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
