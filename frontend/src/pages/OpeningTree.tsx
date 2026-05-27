import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getOpeningTree, type TimeRange } from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'
import { CPL_EXPLANATION } from '../lib/explanations'
import type { OpeningTreeNode } from '../api/client'

export default function OpeningTree() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<TimeRange>('all')

  const query = useQuery({
    queryKey: ['openingTree', id, range],
    queryFn: () => getOpeningTree(id!, 5, 24, range),
    enabled: !!id,
  })

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>

  const nodes = query.data?.nodes ?? []

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        Opening Tree
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        Positions you reach frequently, ranked by average centipawn loss.
        High CPL + high visit count = a leak in your repertoire.
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

      {nodes.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          No opening data in this range. Import and analyze games first.
        </p>
      ) : (
        <div className="space-y-1">
          {nodes.map((node) => (
            <TreeNode key={node.fen_key} node={node} depth={0} />
          ))}
        </div>
      )}
    </div>
  )
}

function TreeNode({ node, depth }: { node: OpeningTreeNode; depth: number }) {
  const cplColor =
    node.avg_cp_loss >= 100
      ? 'text-red-400'
      : node.avg_cp_loss >= 50
        ? 'text-orange-400'
        : node.avg_cp_loss >= 20
          ? 'text-yellow-400'
          : 'text-green-400'

  return (
    <div style={{ paddingLeft: depth * 24 }}>
      <div
        className="flex items-center gap-3 rounded px-3 py-2 border"
        style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
      >
        <span className="font-mono" style={{ color: 'var(--text-primary)' }}>{node.san}</span>
        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {node.visit_count} games
        </span>
        <span className={`text-sm font-medium ${cplColor}`}>
          {node.avg_cp_loss.toFixed(0)} avg CPL
        </span>
      </div>
      {node.children.map((child) => (
        <TreeNode key={child.fen_key} node={child} depth={depth + 1} />
      ))}
    </div>
  )
}
