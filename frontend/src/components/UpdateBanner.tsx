import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getUpdateCheck, installUpdate } from '../api/client'

// Remember which version the user dismissed so we don't nag for the same
// release — but a newer release (different string) shows the prompt again.
const DISMISS_KEY = 'chess_review_dismissed_update'

export default function UpdateBanner() {
  const { data } = useQuery({
    queryKey: ['updateCheck'],
    queryFn: getUpdateCheck,
    staleTime: 6 * 3600 * 1000, // matches the backend's 6h cache
    refetchOnWindowFocus: false,
    retry: false,
  })

  const [dismissed, setDismissed] = useState<string | null>(() =>
    localStorage.getItem(DISMISS_KEY),
  )
  const [installing, setInstalling] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  if (!data || !data.update_available || !data.latest) return null
  if (dismissed === data.latest) return null

  const dismiss = () => {
    if (data.latest) {
      localStorage.setItem(DISMISS_KEY, data.latest)
      setDismissed(data.latest)
    }
  }

  const openExternal = (url: string | null) => {
    if (url) window.open(url, '_blank')
  }

  const update = async () => {
    if (!data.can_self_install) {
      // Dev build, or the release has no installer asset — fall back to the
      // download/release page so the user can grab the installer manually.
      openExternal(data.download_url ?? data.release_url)
      return
    }
    setInstalling(true)
    setMessage('Downloading update…')
    try {
      const res = await installUpdate()
      if (res.started) {
        setMessage('Update downloaded — the app will close and reopen on the new version.')
      } else {
        setInstalling(false)
        setMessage(null)
        openExternal(res.download_url ?? res.release_url)
      }
    } catch {
      setInstalling(false)
      setMessage(null)
      openExternal(data.download_url ?? data.release_url)
    }
  }

  return (
    <div
      className="fixed bottom-4 right-4 w-80 rounded-lg border shadow-xl p-3 z-50 space-y-2"
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          ⬆ Update available
        </div>
        {!installing && (
          <button
            onClick={dismiss}
            title="Dismiss"
            className="text-xs hover:opacity-80"
            style={{ color: 'var(--text-secondary)' }}
          >
            ✕
          </button>
        )}
      </div>

      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
        {message ?? (
          <>
            Version <span className="font-mono">{data.latest}</span> is out — you have{' '}
            <span className="font-mono">{data.current}</span>.
          </>
        )}
      </p>

      {!installing ? (
        <div className="flex items-center gap-2">
          <button
            onClick={update}
            className="px-2.5 py-1 rounded text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white"
          >
            {data.can_self_install ? 'Update now' : 'Download'}
          </button>
          {data.release_url && (
            <button
              onClick={() => openExternal(data.release_url)}
              className="px-2.5 py-1 rounded text-xs hover:opacity-80"
              style={{ color: 'var(--text-secondary)' }}
            >
              What&apos;s new
            </button>
          )}
          <button
            onClick={dismiss}
            className="px-2.5 py-1 rounded text-xs hover:opacity-80 ml-auto"
            style={{ color: 'var(--text-secondary)' }}
          >
            Later
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span className="inline-block w-3 h-3 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          Updating…
        </div>
      )}
    </div>
  )
}
