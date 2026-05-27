import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { createPlayer, startImport } from '../api/client'
import { setStoredPlayer, setStoredImport } from '../lib/storage'

export default function PlayerImport() {
  const [username, setUsername] = useState('')
  const navigate = useNavigate()

  const importMutation = useMutation({
    mutationFn: async (name: string) => {
      const player = await createPlayer('chesscom', name)
      setStoredPlayer({ id: player.id, username: player.username })

      const { job_id } = await startImport(player.id)
      setStoredImport({ playerId: player.id, jobId: job_id })

      return player
    },
    onSuccess: (player) => {
      navigate(`/players/${player.id}`)
    },
  })

  const submit = () => {
    if (username.trim()) importMutation.mutate(username.trim())
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh]">
      <div className="text-6xl mb-4">♚</div>
      <h1 className="text-4xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>Chess Review</h1>
      <p className="mb-8" style={{ color: 'var(--text-secondary)' }}>
        Analyze your chess.com games and find systemic weaknesses
      </p>

      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="chess.com username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          className="px-4 py-2.5 rounded-lg border focus:outline-none focus:border-indigo-500 w-72"
          style={{ background: 'var(--bg-card)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
          disabled={importMutation.isPending}
        />
        <button
          onClick={submit}
          disabled={!username.trim() || importMutation.isPending}
          className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg font-medium
                     hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {importMutation.isPending ? 'Starting...' : 'Import & Analyze'}
        </button>
      </div>

      {importMutation.isError && (
        <p className="text-red-400 text-sm">
          {(importMutation.error as Error).message}
        </p>
      )}
    </div>
  )
}
