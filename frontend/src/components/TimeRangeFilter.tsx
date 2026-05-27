import type { TimeRange } from '../api/client'

const OPTIONS: { value: TimeRange; label: string }[] = [
  { value: 'day', label: 'Last day' },
  { value: 'week', label: 'Last week' },
  { value: 'month', label: 'Last month' },
  { value: 'year', label: 'Last year' },
  { value: 'all', label: 'All time' },
]

export default function TimeRangeFilter({
  value,
  onChange,
}: {
  value: TimeRange
  onChange: (v: TimeRange) => void
}) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {OPTIONS.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
              active
                ? 'bg-indigo-600/30 border-indigo-500 text-indigo-200'
                : 'border-transparent hover:border-current'
            }`}
            style={
              active
                ? undefined
                : { color: 'var(--text-secondary)', background: 'var(--bg-card)' }
            }
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
