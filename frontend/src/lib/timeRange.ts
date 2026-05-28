import type { TimeRange } from '../api/client'

const RANGE_TO_DAYS: Record<Exclude<TimeRange, 'all'>, number> = {
  day: 1,
  week: 7,
  month: 30,
  year: 365,
}

/** Convert a TimeRange into an ISO ``played_from`` cutoff (undefined = no filter). */
export function rangeToPlayedFrom(range: TimeRange): string | undefined {
  if (range === 'all') return undefined
  const days = RANGE_TO_DAYS[range]
  return new Date(Date.now() - days * 86_400_000).toISOString()
}
