/**
 * Shared helpers used by both the list view (OpeningStats) and tree view
 * (OpeningTree) of the Openings umbrella page.
 */

/** Color a Tailwind text class by chess-standard score rate (0..1). */
export function scoreColor(score: number): string {
  if (score >= 0.6) return 'text-green-400'
  if (score >= 0.4) return 'text-yellow-400'
  return 'text-red-400'
}

/** Compact "3d ago" / "2mo ago" for an ISO timestamp. Empty string on null. */
export function relativeDate(iso: string | null): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  const now = Date.now()
  const days = Math.floor((now - then) / 86_400_000)
  if (days < 1) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  const years = Math.floor(days / 365)
  return `${years}y ago`
}
