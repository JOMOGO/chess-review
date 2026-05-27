import { useState, useMemo, useEffect } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Chessboard } from 'react-chessboard'
import { Chess } from 'chess.js'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { getGame } from '../api/client'
import BackButton from '../components/BackButton'
import InfoTip from '../components/InfoTip'
import { CPL_EXPLANATION } from '../lib/explanations'

const CLASS_COLORS: Record<string, string> = {
  best: '#22c55e',
  good: '#86efac',
  inaccuracy: '#eab308',
  mistake: '#f97316',
  blunder: '#ef4444',
  brilliant: '#06b6d4',
  miss: '#a855f7',
}

const CLASS_ICONS: Record<string, string> = {
  best: '✓',
  good: '○',
  inaccuracy: '?!',
  mistake: '?',
  blunder: '??',
  brilliant: '!!',
  miss: '⨯',
}

const CLASS_DESCRIPTIONS: Record<string, string> = {
  brilliant: 'A top move that meaningfully improved your eval — finding the resource in a tactical position.',
  best: 'Matches the engine\'s top move (CPL < 10).',
  good: 'Reasonable move, gives up <40 centipawns.',
  inaccuracy: 'Suboptimal move (40-100 CPL). Cost you a small edge.',
  mistake: 'Significant error (100-300 CPL). Changed the evaluation.',
  blunder: 'Critical error (>300 CPL). Often loses material or the game.',
  miss: 'You were winning, played a non-top move, and the winning advantage evaporated. Same severity as a blunder, but specifically a "missed conversion."',
}

export default function GameReview() {
  const { id } = useParams<{ id: string }>()
  const [currentPly, setCurrentPly] = useState(0)
  const location = useLocation()

  // Determine back destination
  const backTo = location.state?.from || '/'

  const query = useQuery({
    queryKey: ['game', id],
    queryFn: () => getGame(id!),
    enabled: !!id,
  })

  const game = query.data

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') setCurrentPly((p) => Math.max(0, p - 1))
      else if (e.key === 'ArrowRight') setCurrentPly((p) => Math.min((game?.moves.length ?? 0), p + 1))
      else if (e.key === 'Home') setCurrentPly(0)
      else if (e.key === 'End') setCurrentPly(game?.moves.length ?? 0)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [game])

  const positions = useMemo(() => {
    if (!game) return []
    const chess = new Chess()
    const fens = [chess.fen()]
    for (const move of game.moves) {
      chess.move(move.san)
      fens.push(chess.fen())
    }
    return fens
  }, [game])

  const evalData = useMemo(() => {
    if (!game) return []
    return game.moves.map((m, i) => ({
      ply: i + 1,
      eval: m.eval_after_cp != null ? Math.max(-5, Math.min(5, m.eval_after_cp / 100)) : null,
    }))
  }, [game])

  const accuracy = useMemo(() => {
    if (!game) return null
    const userMoves = game.moves.filter(
      (m) => m.is_user_move && m.eval_before_cp != null && m.eval_after_cp != null,
    )
    if (userMoves.length === 0) return null
    const clamp = (cp: number) => Math.max(-1000, Math.min(1000, cp))
    const winPercent = (cp: number) =>
      50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1)
    const perMove = userMoves.map((m) => {
      const cb = clamp(m.eval_before_cp!)
      const ca = clamp(m.eval_after_cp!)
      const moverIsWhite = m.ply % 2 === 1
      const wpB = moverIsWhite ? winPercent(cb) : 100 - winPercent(cb)
      const wpA = moverIsWhite ? winPercent(ca) : 100 - winPercent(ca)
      const drop = Math.max(0, wpB - wpA)
      const a = 103.1668 * Math.exp(-0.04354 * drop) - 3.1668
      return Math.max(0, Math.min(100, a))
    })
    // Lichess-style volatility-weighted mean: moves near blunders count more
    // than moves in quiet stretches, so a single missed mate isn't diluted
    // away by 30 calm developing moves.
    const n = perMove.length
    if (n === 1) return Math.round(perMove[0] * 10) / 10
    const window = Math.max(2, Math.ceil(n / 10))
    let total = 0
    let weightSum = 0
    for (let i = 0; i < n; i++) {
      const lo = Math.max(0, i - window)
      const hi = Math.min(n, i + window + 1)
      const slice = perMove.slice(lo, hi)
      const mean = slice.reduce((s, v) => s + v, 0) / slice.length
      const variance = slice.reduce((s, v) => s + (v - mean) ** 2, 0) / slice.length
      const w = Math.max(0.5, Math.sqrt(variance))
      total += perMove[i] * w
      weightSum += w
    }
    const acc = total / weightSum
    return Math.round(acc * 10) / 10
  }, [game])

  const classCounts = useMemo(() => {
    if (!game) return {}
    const counts: Record<string, number> = {}
    for (const m of game.moves) {
      if (m.is_user_move && m.classification) {
        counts[m.classification] = (counts[m.classification] || 0) + 1
      }
    }
    return counts
  }, [game])

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
  if (!game) return <p className="text-red-400">Game not found</p>

  const currentFen = positions[currentPly] || 'start'
  const boardOrientation = game.user_color === 'black' ? 'black' : 'white'
  const currentMove = currentPly > 0 ? game.moves[currentPly - 1] : null
  const evalPct = currentMove?.eval_after_cp != null
    ? Math.max(5, Math.min(95, 50 + currentMove.eval_after_cp / 20))
    : 50

  return (
    <div>
      <BackButton to={backTo} label="Back" />

      {/* Game header */}
      <div className="bg-[#16162a] border border-gray-700 rounded-lg p-4 mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="text-center">
              <div className="text-white font-semibold">{game.white_username}</div>
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{game.white_rating || '?'}</div>
            </div>
            <div className="text-lg font-bold" style={{ color: 'var(--text-muted)' }}>vs</div>
            <div className="text-center">
              <div className="text-white font-semibold">{game.black_username}</div>
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{game.black_rating || '?'}</div>
            </div>
            <span className={`ml-2 px-2 py-0.5 rounded text-sm font-medium ${
              game.user_result === 'win' ? 'bg-green-900/50 text-green-400'
              : game.user_result === 'loss' ? 'bg-red-900/50 text-red-400'
              : 'bg-gray-700/50 text-gray-400'
            }`}>
              {game.result}
            </span>
          </div>
          <div className="text-right text-sm" style={{ color: 'var(--text-secondary)' }}>
            <div>{game.opening_name || game.eco || 'Unknown opening'}</div>
            <div>{game.time_class} {game.time_control} &middot; {new Date(game.played_at).toLocaleDateString()}</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-4">
        {/* Left: board + eval graph */}
        <div>
          <div className="flex gap-1">
            {/* Eval bar */}
            <div className="w-5 rounded overflow-hidden relative flex-shrink-0" style={{ background: '#333' }}>
              <div className="absolute bottom-0 left-0 right-0 bg-white transition-all duration-300"
                style={{ height: `${evalPct}%` }} />
            </div>

            {/* Board */}
            <div className="flex-1 aspect-square max-w-[600px]">
              <Chessboard options={{
                position: currentFen,
                boardOrientation: boardOrientation,
                allowDragging: false,
              }} />
            </div>
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-center gap-2 mt-3">
            <NavBtn onClick={() => setCurrentPly(0)} label="⟨⟨" />
            <NavBtn onClick={() => setCurrentPly(Math.max(0, currentPly - 1))} label="⟨" />
            <span className="text-sm px-3 font-mono" style={{ color: 'var(--text-secondary)' }}>
              {currentPly > 0 ? `${Math.ceil(currentPly / 2)}.${currentPly % 2 === 1 ? '..' : ''}` : 'Start'}
            </span>
            <NavBtn onClick={() => setCurrentPly(Math.min(positions.length - 1, currentPly + 1))} label="⟩" />
            <NavBtn onClick={() => setCurrentPly(positions.length - 1)} label="⟩⟩" />
          </div>

          {/* Eval graph */}
          <div className="bg-[#16162a] border border-gray-700 rounded-lg p-3 mt-3" style={{ height: 120 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={evalData} onClick={(e) => {
                if (e?.activeLabel) setCurrentPly(Number(e.activeLabel))
              }}>
                <defs>
                  <linearGradient id="evalGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#ffffff" stopOpacity={0.3} />
                    <stop offset="50%" stopColor="#ffffff" stopOpacity={0} />
                    <stop offset="50%" stopColor="#000000" stopOpacity={0} />
                    <stop offset="100%" stopColor="#000000" stopOpacity={0.3} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="ply" hide />
                <YAxis domain={[-5, 5]} hide />
                <ReferenceLine y={0} stroke="#4b5563" />
                <Tooltip contentStyle={{ background: '#16162a', border: '1px solid #374151', fontSize: 12 }}
                  formatter={(v) => [`${Number(v) > 0 ? '+' : ''}${v}`, 'Eval']} />
                <Area type="monotone" dataKey="eval" stroke="#818cf8" fill="url(#evalGrad)" strokeWidth={1.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right panel */}
        <div className="space-y-3">
          {/* Accuracy & classification summary */}
          <div className="bg-[#16162a] border border-gray-700 rounded-lg p-4">
            <div className="text-center mb-3">
              {accuracy !== null ? (
                <>
                  <div className="text-3xl font-bold text-indigo-400">{accuracy}%</div>
                  <div className="text-xs inline-flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
                    Accuracy
                    <InfoTip label="How accuracy is calculated">
                      <strong>Accuracy</strong> = mean per-move accuracy across your moves.
                      Each move is scored 0-100 by how much it dropped your win probability
                      versus the engine's best line (Lichess/chess.com formula). Mate scores
                      are clamped so one missed mate can't tank the whole game.
                    </InfoTip>
                  </div>
                </>
              ) : (
                <div className="text-sm" style={{ color: 'var(--text-muted)' }}>Not yet analyzed</div>
              )}
            </div>
            <div className="grid grid-cols-6 gap-1 text-center text-xs">
              {(
                ['best', 'good', 'inaccuracy', 'mistake', 'miss', 'blunder'] as const
              ).map((cls) => (
                <div key={cls}>
                  <div className="font-bold text-lg" style={{ color: CLASS_COLORS[cls] }}>
                    {classCounts[cls] || 0}
                  </div>
                  <div className="capitalize inline-flex items-center gap-0.5" style={{ color: 'var(--text-muted)' }}>
                    {cls}
                    <InfoTip label={`What ${cls} means`}>{CLASS_DESCRIPTIONS[cls]}</InfoTip>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-3 border-t text-[11px]" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
              <span className="inline-flex items-center gap-1">
                CPL shown below
                <InfoTip>{CPL_EXPLANATION}</InfoTip>
              </span>
            </div>
          </div>

          {/* Current move info */}
          {currentMove && (
            <div className="bg-[#16162a] border border-gray-700 rounded-lg p-3">
              <div className="flex items-center justify-between">
                <span className="font-mono text-white">
                  {Math.ceil(currentMove.ply / 2)}{currentMove.ply % 2 === 1 ? '.' : '...'} {currentMove.san}
                </span>
                {currentMove.classification && (
                  <span className="px-2 py-0.5 rounded text-xs font-bold"
                    style={{ color: CLASS_COLORS[currentMove.classification], border: `1px solid ${CLASS_COLORS[currentMove.classification]}40` }}>
                    {CLASS_ICONS[currentMove.classification]} {currentMove.classification}
                  </span>
                )}
              </div>
              <div className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                {currentMove.eval_after_cp != null && (
                  <span>Eval: {currentMove.eval_after_cp > 0 ? '+' : ''}{(currentMove.eval_after_cp / 100).toFixed(1)}</span>
                )}
                {currentMove.cp_loss != null && currentMove.cp_loss > 0 && (
                  <span className="ml-3">Loss: {(currentMove.cp_loss / 100).toFixed(2)}</span>
                )}
                {currentMove.phase && <span className="ml-3 capitalize">{currentMove.phase}</span>}
                {currentMove.clock_remaining_ms != null && (
                  <span className="ml-3">{formatClock(currentMove.clock_remaining_ms)}</span>
                )}
              </div>
            </div>
          )}

          {/* Move list */}
          <div className="bg-[#16162a] border border-gray-700 rounded-lg p-3 overflow-y-auto" style={{ maxHeight: 400 }}>
            <div className="grid grid-cols-[32px_1fr_1fr] gap-y-0.5 text-sm">
              {game.moves.reduce<Array<{ num: number; white?: typeof game.moves[0]; black?: typeof game.moves[0] }>>(
                (acc, move) => {
                  if (move.ply % 2 === 1) acc.push({ num: Math.ceil(move.ply / 2), white: move })
                  else if (acc.length > 0) acc[acc.length - 1].black = move
                  return acc
                }, []
              ).map((row) => (
                <MoveRow key={row.num} num={row.num} white={row.white} black={row.black}
                  currentPly={currentPly} onSelect={setCurrentPly} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function MoveRow({ num, white, black, currentPly, onSelect }: {
  num: number
  white?: { ply: number; san: string; classification: string | null; is_user_move: boolean }
  black?: { ply: number; san: string; classification: string | null; is_user_move: boolean }
  currentPly: number
  onSelect: (ply: number) => void
}) {
  return (
    <>
      <span style={{ color: 'var(--text-muted)' }} className="text-xs self-center">{num}.</span>
      {white ? <MoveCell move={white} isActive={currentPly === white.ply} onClick={() => onSelect(white.ply)} /> : <span />}
      {black ? <MoveCell move={black} isActive={currentPly === black.ply} onClick={() => onSelect(black.ply)} /> : <span />}
    </>
  )
}

function MoveCell({ move, isActive, onClick }: {
  move: { san: string; classification: string | null; is_user_move: boolean }
  isActive: boolean
  onClick: () => void
}) {
  const color = move.is_user_move && move.classification ? CLASS_COLORS[move.classification] : undefined
  return (
    <button onClick={onClick}
      className={`text-left px-1.5 py-0.5 rounded cursor-pointer text-sm ${isActive ? 'bg-indigo-600/30' : 'hover:bg-gray-700/50'}`}
      style={{ color: color || 'var(--text-primary)' }}>
      {move.is_user_move && move.classification && move.classification !== 'best' && move.classification !== 'good' && (
        <span className="text-[10px] mr-0.5">{CLASS_ICONS[move.classification]}</span>
      )}
      {move.san}
    </button>
  )
}

function NavBtn({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button onClick={onClick}
      className="w-9 h-9 rounded flex items-center justify-center bg-[#16162a] border border-gray-600 hover:bg-gray-700 text-sm"
      style={{ color: 'var(--text-primary)' }}>
      {label}
    </button>
  )
}

function formatClock(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}
