import { useEffect, useState } from 'react'
import type { TimeRange } from '../api/client'

const RANGE_KEY = 'chess_review_time_range'
const RANGE_EVENT = 'chess-review-range-changed'
const VALID: TimeRange[] = ['day', 'week', 'month', 'year', 'all']

function read(): TimeRange {
  try {
    const raw = localStorage.getItem(RANGE_KEY)
    if (raw && (VALID as string[]).includes(raw)) return raw as TimeRange
  } catch {
    // ignore
  }
  return 'all'
}

export function useTimeRange(): [TimeRange, (v: TimeRange) => void] {
  const [range, setRangeState] = useState<TimeRange>(read)

  useEffect(() => {
    const sync = () => setRangeState(read())
    window.addEventListener(RANGE_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(RANGE_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  const setRange = (v: TimeRange) => {
    localStorage.setItem(RANGE_KEY, v)
    setRangeState(v)
    window.dispatchEvent(new Event(RANGE_EVENT))
  }

  return [range, setRange]
}
