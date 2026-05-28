import { Navigate, useParams } from 'react-router-dom'

/**
 * The old route /players/:id/opening-stats has been folded into the unified
 * Openings page. Redirect any stale links to the list tab.
 */
export default function OpeningsLegacyRedirect() {
  const { id } = useParams<{ id: string }>()
  if (!id) return null
  return <Navigate to={`/players/${id}/openings?view=list`} replace />
}
