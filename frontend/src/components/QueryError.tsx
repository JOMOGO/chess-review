/**
 * Inline error state for failed data queries. Used as a top-level early
 * return on analytics pages: `if (query.isError) return <QueryError ... />`.
 *
 * Keeps the user out of a blank-screen failure mode when the backend is down
 * or a route returns 4xx/5xx.
 */
export default function QueryError({
  message,
  error,
}: {
  message?: string
  error?: unknown
}) {
  const detail = error instanceof Error ? error.message : null
  return (
    <div
      className="rounded-lg border p-4 my-4"
      style={{
        background: 'var(--bg-card)',
        borderColor: 'var(--danger, #b91c1c)',
        color: 'var(--text-primary)',
      }}
    >
      <p className="font-semibold mb-1">
        {message ?? 'Something went wrong loading this view.'}
      </p>
      {detail && (
        <p className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
          {detail}
        </p>
      )}
      <p className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
        Check the backend is running and the player has finished importing.
      </p>
    </div>
  )
}
