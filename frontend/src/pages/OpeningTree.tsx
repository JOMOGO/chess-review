import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getOpeningTree, type TimeRange } from '../api/client'
import type { OpeningTreeNode } from '../api/client'
import { scoreColor } from '../lib/openings'
import WdlBar from '../components/WdlBar'
import QueryError from '../components/QueryError'

const MIN_VISITS_OPTIONS = [1, 2, 5, 10] as const
type MinVisits = typeof MIN_VISITS_OPTIONS[number]

type ColorFilter = 'all' | 'white' | 'black'

/**
 * The "Move Tree" tab of the Openings umbrella page. The umbrella owns the
 * page header and range filter — this component just renders the tree.
 */
export default function OpeningTree({ playerId, range }: { playerId: string; range: TimeRange }) {
  // Default is 2 so rare lines aren't pruned out of existence. 5 (the old
  // default) hid a lot of openings the user actually played, making the tree
  // look incomplete.
  const [minVisits, setMinVisits] = useState<MinVisits>(2)
  // Color filter narrows the tree to games where the user played that
  // colour. Default is 'white' because the tree is only really meaningful
  // when looking at one repertoire at a time — in 'all' mode the same node
  // can represent the user's own move (in same-color games) or the
  // opponent's (in opposite-color games), making CPL ambiguous.
  const [colorFilter, setColorFilter] = useState<ColorFilter>('white')

  const query = useQuery({
    queryKey: ['openingTree', playerId, range, minVisits, colorFilter],
    queryFn: () =>
      getOpeningTree(
        playerId,
        minVisits,
        24,
        range,
        colorFilter === 'all' ? undefined : colorFilter,
      ),
  })

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading…</p>
  if (query.isError) return <QueryError error={query.error} />


  const nodes = query.data?.nodes ?? []

  // Total games visible at root = sum of visits across top-level branches.
  // This is how many of your games made it into the tree at the current
  // threshold — handy to compare against your total analyzed-games count.
  const reachable = nodes.reduce((s, n) => s + n.visit_count, 0)

  return (
    <>
      <div className="flex items-center gap-3 mb-3 flex-wrap text-sm">
        <span style={{ color: 'var(--text-secondary)' }}>
          {nodes.length} first {nodes.length === 1 ? 'move' : 'moves'} · {reachable} games shown
          {colorFilter !== 'all' && (
            <span style={{ color: 'var(--text-muted)' }}>
              {' '}(you as {colorFilter})
            </span>
          )}
        </span>
        <span className="ml-auto inline-flex items-center gap-2 flex-wrap">
          <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
            You play
          </span>
          <ColorToggle value={colorFilter} onChange={setColorFilter} />

          <span className="text-xs uppercase tracking-wide ml-3" style={{ color: 'var(--text-muted)' }}>
            Min games per branch
          </span>
          <div className="inline-flex rounded border overflow-hidden text-xs" style={{ borderColor: 'var(--border)' }}>
            {MIN_VISITS_OPTIONS.map((n) => (
              <button
                key={n}
                onClick={() => setMinVisits(n)}
                className={`px-2.5 py-1 transition-colors ${minVisits === n ? 'font-semibold' : ''}`}
                style={{
                  background: minVisits === n ? 'var(--accent-bg, #4f46e5)' : 'transparent',
                  color: minVisits === n ? 'white' : 'var(--text-secondary)',
                }}
              >
                {n}
              </button>
            ))}
          </div>
        </span>
      </div>

      {nodes.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          No opening data in this range at min ≥ {minVisits} games. Try lowering the threshold.
        </p>
      ) : (
        <div className="space-y-1">
          {nodes.map((node) => (
            <TreeNode
              key={node.fen_key}
              node={node}
              depth={0}
              defaultExpanded
              showCpl={colorFilter !== 'all'}
            />
          ))}
        </div>
      )}
    </>
  )
}

function ColorToggle({ value, onChange }: { value: ColorFilter; onChange: (v: ColorFilter) => void }) {
  const opts: { v: ColorFilter; label: string }[] = [
    { v: 'all', label: 'All' },
    { v: 'white', label: '♔ White' },
    { v: 'black', label: '♚ Black' },
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

function cplColorClass(avg: number, hasCpl: boolean): string {
  if (!hasCpl) return ''
  if (avg >= 100) return 'text-red-400'
  if (avg >= 50) return 'text-orange-400'
  if (avg >= 20) return 'text-yellow-400'
  return 'text-green-400'
}

function TreeNode({
  node,
  depth,
  defaultExpanded = false,
  showCpl,
}: {
  node: OpeningTreeNode
  depth: number
  defaultExpanded?: boolean
  showCpl: boolean
}) {
  const [open, setOpen] = useState(defaultExpanded)
  const hasChildren = node.children.length > 0
  // CPL is only meaningful when (a) this node represents a user-played move
  // (user_move_count > 0) AND (b) we're filtered to one colour so the user's
  // role at each depth is unambiguous.
  const hasCpl = showCpl && node.user_move_count > 0

  return (
    <div style={{ paddingLeft: depth * 20 }}>
      <button
        onClick={() => hasChildren && setOpen((o) => !o)}
        className="w-full flex items-center gap-3 rounded px-3 py-2 border text-left hover:opacity-90"
        style={{
          background: 'var(--bg-card)',
          borderColor: 'var(--border)',
          cursor: hasChildren ? 'pointer' : 'default',
        }}
      >
        <span className="w-4 text-center" style={{ color: 'var(--text-muted)' }} aria-hidden>
          {hasChildren ? (open ? '▾' : '▸') : '·'}
        </span>
        <span className="font-mono w-16" style={{ color: 'var(--text-primary)' }}>
          {node.san}
        </span>
        <span className="text-sm w-20" style={{ color: 'var(--text-secondary)' }}>
          {node.visit_count} games
        </span>
        {hasCpl ? (
          <span className={`text-sm font-medium w-24 ${cplColorClass(node.avg_cp_loss, hasCpl)}`}>
            {node.avg_cp_loss.toFixed(0)} CPL
          </span>
        ) : (
          <span className="w-24" />
        )}
        <WdlBar wins={node.wins} draws={node.draws} losses={node.losses} width={80} />
        <span className={`text-sm font-bold w-12 text-right ${scoreColor(node.score_rate)}`}>
          {Math.round(node.score_rate * 100)}%
        </span>
      </button>
      {open && node.children.map((child) => (
        <TreeNode key={child.fen_key} node={child} depth={depth + 1} showCpl={showCpl} />
      ))}
    </div>
  )
}
