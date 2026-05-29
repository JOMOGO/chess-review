import { useState, useMemo, useEffect } from 'react'
import { useParams, useLocation, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Chessboard } from 'react-chessboard'
import { Chess } from 'chess.js'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
  ReferenceArea, ReferenceDot,
} from 'recharts'
import { getGame } from '../api/client'
import BackButton from '../components/BackButton'
import InfoTip from '../components/InfoTip'

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

const PHASE_COLORS: Record<string, string> = {
  opening: '#3b82f6',
  middlegame: '#a855f7',
  endgame: '#22c55e',
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
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [currentPly, setCurrentPly] = useState<number>(() => {
    // Deep-link: ?ply=N jumps straight to that ply (e.g. from the Tactics
    // page so the user lands on the position right before a missed move).
    const p = Number.parseInt(searchParams.get('ply') ?? '', 10)
    return Number.isFinite(p) && p > 0 ? p : 0
  })
  // Hover cursor on the eval chart. We track this ourselves (rounded to the
  // nearest real ply) instead of letting Recharts' Tooltip draw one, because
  // its default cursor snaps to the nearest data point — which now includes
  // synthetic zero-crossing rows at fractional plys, producing a second
  // vertical line whenever the user hovered over a sign flip.
  const [hoverPly, setHoverPly] = useState<number | null>(null)

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
    // Build raw eval points, then walk pair-by-pair inserting a synthetic
    // zero-crossing whenever the eval flips sign. Each resulting point carries
    // three keys — eval (the real curve), evalWhite (clamped to >=0, fed to the
    // white fill area), evalBlack (clamped to <=0, fed to the dark fill area).
    // Because the synthetic point sits at exactly (ply, 0) in all three series,
    // both fill polygons close cleanly at the zero line where the curve crosses
    // it; no SVG gradient or clip-path tricks needed.
    const raw = game.moves.map((m, i) => ({
      ply: i + 1,
      eval: m.eval_after_cp != null
        ? Math.max(-5, Math.min(5, m.eval_after_cp / 100))
        : null,
    }))
    type Row = { ply: number; eval: number | null; evalWhite: number | null; evalBlack: number | null }
    const out: Row[] = []
    for (let i = 0; i < raw.length; i++) {
      const curr = raw[i]
      if (i > 0) {
        const prev = raw[i - 1]
        if (prev.eval != null && curr.eval != null &&
            ((prev.eval > 0 && curr.eval < 0) || (prev.eval < 0 && curr.eval > 0))) {
          const t = prev.eval / (prev.eval - curr.eval)
          const crossPly = prev.ply + t * (curr.ply - prev.ply)
          out.push({ ply: crossPly, eval: 0, evalWhite: 0, evalBlack: 0 })
        }
      }
      out.push({
        ply: curr.ply,
        eval: curr.eval,
        evalWhite: curr.eval != null ? Math.max(0, curr.eval) : null,
        evalBlack: curr.eval != null ? Math.min(0, curr.eval) : null,
      })
    }
    return out
  }, [game])

  // Phase bands for the chart background. Group consecutive plies sharing a
  // phase so each band is one <ReferenceArea> rather than per-ply slivers.
  // Then close the 1-ply gap between adjacent bands by extending each one to
  // the midpoint with its neighbor, so the colors meet 50/50 across the
  // transition instead of leaving a strip of bare background.
  const phaseBands = useMemo(() => {
    if (!game) return []
    const bands: { from: number; to: number; phase: string }[] = []
    let current: { from: number; to: number; phase: string } | null = null
    game.moves.forEach((m, i) => {
      const ply = i + 1
      if (!m.phase) return
      if (current && current.phase === m.phase) {
        current.to = ply
      } else {
        if (current) bands.push(current)
        current = { from: ply, to: ply, phase: m.phase }
      }
    })
    if (current) bands.push(current)
    for (let i = 0; i < bands.length - 1; i++) {
      const mid = (bands[i].to + bands[i + 1].from) / 2
      bands[i].to = mid
      bands[i + 1].from = mid
    }
    return bands
  }, [game])

  // User moves classified as a real error (or a "miss") get a colored dot on
  // the chart so the user can spot their critical moments at a glance.
  const errorDots = useMemo(() => {
    if (!game) return []
    return game.moves
      .map((m, i) => ({ m, ply: i + 1 }))
      .filter(({ m }) =>
        m.is_user_move &&
        m.classification != null &&
        ['blunder', 'mistake', 'miss', 'inaccuracy'].includes(m.classification),
      )
      .map(({ m, ply }) => ({
        ply,
        eval: m.eval_after_cp != null ? Math.max(-5, Math.min(5, m.eval_after_cp / 100)) : 0,
        classification: m.classification as string,
      }))
  }, [game])

  // Lichess accuracy. The previous implementation diverged in three ways that
  // collectively over-rated games by ~10 points: volatility weights were
  // computed from the spread of *accuracy* values (which cluster near 100), not
  // from the spread of win-percent values across the whole game; window/weight
  // had no upper cap; and the final result was a plain weighted mean instead
  // of being averaged with the harmonic mean (which punishes a single blunder
  // much harder than the arithmetic mean does).
  const accuracy = useMemo(() => {
    if (!game) return null
    const clamp = (cp: number) => Math.max(-1000, Math.min(1000, cp))
    const winPercent = (cp: number) =>
      50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1)

    // White-POV win percent for every position (start + after each move).
    const wp: number[] = []
    const firstBefore = game.moves.find((m) => m.eval_before_cp != null)
    if (firstBefore?.eval_before_cp != null) {
      wp.push(winPercent(clamp(firstBefore.eval_before_cp)))
    }
    for (const m of game.moves) {
      if (m.eval_after_cp != null) wp.push(winPercent(clamp(m.eval_after_cp)))
      else if (wp.length > 0) wp.push(wp[wp.length - 1])
    }
    if (wp.length < 2) return null

    // Sliding-window volatility weights (clamped 2..8, 0.5..12 per Lichess).
    const windowSize = Math.max(2, Math.min(8, Math.ceil(wp.length / 10)))
    const weights: number[] = []
    for (let i = 0; i < wp.length; i++) {
      const slice = wp.slice(i, Math.min(wp.length, i + windowSize))
      const mean = slice.reduce((s, v) => s + v, 0) / slice.length
      const variance = slice.reduce((s, v) => s + (v - mean) ** 2, 0) / slice.length
      weights.push(Math.max(0.5, Math.min(12, Math.sqrt(variance))))
    }

    // Per-move user accuracy, paired with the weight at the position the move
    // was played from. wpIdx tracks which position in wp corresponds to the
    // state *before* each move (i.e. the move's starting position).
    const accs: number[] = []
    const accWeights: number[] = []
    let wpIdx = 0
    for (const m of game.moves) {
      const here = wpIdx
      wpIdx++
      if (!m.is_user_move) continue
      if (m.eval_before_cp == null || m.eval_after_cp == null) continue
      const wpB = winPercent(clamp(m.eval_before_cp))
      const wpA = winPercent(clamp(m.eval_after_cp))
      const moverIsWhite = m.ply % 2 === 1
      const drop = moverIsWhite ? Math.max(0, wpB - wpA) : Math.max(0, wpA - wpB)
      const a = Math.max(0, Math.min(100, 103.1668 * Math.exp(-0.04354 * drop) - 3.1668))
      accs.push(a)
      accWeights.push(weights[Math.min(here, weights.length - 1)] ?? 0.5)
    }

    if (accs.length === 0) return null
    if (accs.length === 1) return Math.round(accs[0] * 10) / 10

    let weightedSum = 0
    let totalWeight = 0
    for (let i = 0; i < accs.length; i++) {
      weightedSum += accs[i] * accWeights[i]
      totalWeight += accWeights[i]
    }
    const weightedMean = weightedSum / totalWeight
    const harmonicMean = accs.length /
      accs.reduce((s, a) => s + 1 / Math.max(1, a), 0)

    return Math.round(((weightedMean + harmonicMean) / 2) * 10) / 10
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

  // The board's parent gives us an aspect-square slot whose pixel dimensions
  // can be non-integer (e.g. 580.5px tall after the row's height is
  // distributed). react-chessboard renders 8 squares as `grid-template-columns:
  // repeat(8, 1fr)` — when the parent isn't a multiple of 8, the rows round
  // inconsistently and you get hairline white gaps. Solution: measure the
  // available square and snap to floor(dim / 8) * 8.
  //
  // Using a callback ref via useState so the effect re-runs the moment the
  // slot actually mounts. A plain useRef with `[]`-dep useEffect would miss
  // this — on first render `query.isLoading` returns early and the slot div
  // is never rendered, so the ref stays null and the observer never attaches.
  const [boardSlot, setBoardSlot] = useState<HTMLDivElement | null>(null)
  const [boardSize, setBoardSize] = useState(0)
  useEffect(() => {
    if (!boardSlot) return
    const recompute = () => {
      const w = boardSlot.clientWidth
      const h = boardSlot.clientHeight
      // 920 matches the slot's max-w-[920px] cap; the 600 we had here was
      // an old leftover that was silently clamping the board well below
      // what the column could actually give it.
      const dim = Math.min(w, h, 920)
      setBoardSize(Math.max(64, Math.floor(dim / 8) * 8))
    }
    recompute()
    const ro = new ResizeObserver(recompute)
    ro.observe(boardSlot)
    return () => ro.disconnect()
  }, [boardSlot])

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Loading...</p>
  if (!game) return <p className="text-red-400">Game not found</p>

  const currentFen = positions[currentPly] || 'start'
  const userIsWhite = game.user_color === 'white'
  const boardOrientation: 'white' | 'black' = userIsWhite ? 'white' : 'black'
  const currentMove = currentPly > 0 ? game.moves[currentPly - 1] : null

  // Best move for the *current* position to move from. moves[currentPly] is
  // the next move in the game, whose position_before is what's on the board.
  const nextMove = currentPly < game.moves.length ? game.moves[currentPly] : null
  const bestUci = nextMove?.best_move_uci ?? null
  const bestArrow = bestUci && bestUci.length >= 4
    ? [{ startSquare: bestUci.slice(0, 2), endSquare: bestUci.slice(2, 4), color: 'rgba(34, 197, 94, 0.75)' }]
    : []
  let bestSan: string | null = null
  if (bestUci && bestUci.length >= 4) {
    try {
      const c = new Chess(currentFen)
      const move = c.move({
        from: bestUci.slice(0, 2),
        to: bestUci.slice(2, 4),
        promotion: bestUci.length > 4 ? bestUci.slice(4) : undefined,
      })
      bestSan = move?.san ?? null
    } catch {
      bestSan = null
    }
  }
  const playedMatchesBest = bestUci != null && nextMove != null && nextMove.uci === bestUci

  // Who's to move at the displayed position, and whether the game is over here.
  const gameOver = currentPly === game.moves.length
  const whiteToMove = currentPly % 2 === 0
  const topPlayer = userIsWhite
    ? { name: game.black_username, rating: game.black_rating, color: 'black' as const, isUser: false }
    : { name: game.white_username, rating: game.white_rating, color: 'white' as const, isUser: false }
  const bottomPlayer = userIsWhite
    ? { name: game.white_username, rating: game.white_rating, color: 'white' as const, isUser: true }
    : { name: game.black_username, rating: game.black_rating, color: 'black' as const, isUser: true }
  const topToMove = !gameOver && ((topPlayer.color === 'white') === whiteToMove)
  const bottomToMove = !gameOver && ((bottomPlayer.color === 'white') === whiteToMove)

  return (
    <div>
      <BackButton to={backTo} label="Back" />

      {/* Game meta header — kept compact so the grid row below it claims more
          of the viewport (player names live in the right-column strips).
          Width capped on lg+ to (boardSize + 26 left col + 16 gap + 340 right
          col) so its right edge lands on the move-list's right edge instead of
          stretching to the full max-w-7xl page width. */}
      <div
        className="bg-[#16162a] border border-gray-700 rounded-lg px-3 py-1.5 mb-2 flex items-center justify-between text-sm lg:max-w-[var(--top-bar-w)]"
        style={{ '--top-bar-w': boardSize > 0 ? `${boardSize + 382}px` : 'none' } as React.CSSProperties}
      >
        <div className="flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
          <span>{game.opening_name || game.eco || 'Unknown opening'}</span>
          <span style={{ color: 'var(--text-muted)' }}>&middot;</span>
          <span>{game.time_class} {game.time_control}</span>
          <span style={{ color: 'var(--text-muted)' }}>&middot;</span>
          <span>{new Date(game.played_at).toLocaleDateString()}</span>
        </div>
        <span className={`px-2 py-0.5 rounded text-sm font-medium ${
          game.user_result === 'win' ? 'bg-green-900/50 text-green-400'
          : game.user_result === 'loss' ? 'bg-red-900/50 text-red-400'
          : 'bg-gray-700/50 text-gray-400'
        }`}>
          {game.result} &middot; {game.user_result === 'win' ? 'You won' : game.user_result === 'loss' ? 'You lost' : 'Draw'}
        </span>
      </div>

      {/*
        Cap the grid row's height so the right column's move list can't push
        the layout past the chart's bottom. Both columns inherit this height
        via the default `align-items: stretch`, which lets the right column's
        `flex-1 min-h-0` move list grab exactly the remaining space under
        the cards. Board uses max-h-full so aspect-square scales down if the
        viewport is shorter than the natural ~820px layout.
      */}
      {/* Left grid column is pinned to (boardSize + 26) on lg+ via the
          --board-col CSS variable: that's exactly eval-bar (22) + gap-1 (4) +
          board, so the right column hugs the board with just the gap-4 (16px)
          between them. Falls back to 1fr until boardSize is measured, and the
          mobile single-column layout is unaffected (grid-cols-1 still wins). */}
      <div
        className="grid grid-cols-1 lg:grid-cols-[var(--board-col)_340px] gap-4 lg:h-[calc(100vh-180px)]"
        style={{ '--board-col': boardSize > 0 ? `${boardSize + 26}px` : '1fr' } as React.CSSProperties}
      >
        {/* Left: board + nav + eval graph. Player strips moved to the right
            column so the board can claim the full vertical space here. */}
        <div className="flex flex-col min-h-0">
          <div className="flex gap-1 flex-1 min-h-0 justify-start">
            <EvalBar cp={currentMove?.eval_after_cp ?? null} flipped={boardOrientation === 'black'} />

            {/* Board slot: outer ref measures the available square; inner div
                is sized to the nearest multiple of 8 pixels so the
                chessboard's 1fr×8 grid never falls on a sub-pixel boundary
                (which produces white hairline gaps between squares).
                `justify-start` sits the board flush against the eval bar
                instead of centering it — eliminates the wasted gap on the
                left. The remaining horizontal slack ends up on the right. */}
            <div
              ref={setBoardSlot}
              className="flex-1 max-w-[920px] flex items-center justify-start"
              style={{ height: '100%', minHeight: 0 }}
            >
              {boardSize > 0 && (
                <div style={{ width: boardSize, height: boardSize }}>
                  <Chessboard options={{
                    position: currentFen,
                    boardOrientation: boardOrientation,
                    allowDragging: false,
                    arrows: bestArrow,
                  }} />
                </div>
              )}
            </div>
          </div>

          {/* Navigation buttons */}
          <div className="flex items-center justify-center gap-1.5 mt-1">
            <NavBtn onClick={() => setCurrentPly(0)} label="⟨⟨" title="Jump to start" />
            <NavBtn onClick={() => setCurrentPly(Math.max(0, currentPly - 1))} label="⟨" title="Previous move (←)" />
            <span className="text-xs px-2 font-mono min-w-[64px] text-center" style={{ color: 'var(--text-secondary)' }}>
              {currentPly > 0 ? `${Math.ceil(currentPly / 2)}.${currentPly % 2 === 1 ? '..' : ''}` : 'Start'}
            </span>
            <NavBtn onClick={() => setCurrentPly(Math.min(positions.length - 1, currentPly + 1))} label="⟩" title="Next move (→)" />
            <NavBtn onClick={() => setCurrentPly(positions.length - 1)} label="⟩⟩" title="Jump to end" />
          </div>

          {/* Eval graph — width pinned to (eval-bar 22 + gap-1 4 + boardSize)
              so its left edge lines up with the eval bar above and its right
              edge stops at the board's right edge. No internal padding so the
              plot area fills the row edge-to-edge (plus the chart's own 4px
              margin, which keeps the leftmost/rightmost dots from clipping). */}
          <div
            // Suppress the black focus ring that browsers draw on the chart's
            // internal SVG / surface after a click. The chart is purely a
            // visual surface; we don't want a keyboard-focus indicator.
            className="rounded-lg mt-1 relative overflow-hidden focus:outline-none [&_*]:focus:outline-none [&_*]:outline-none"
            tabIndex={-1}
            style={{
              height: 100,
              background: '#475569',
              width: boardSize > 0 ? boardSize + 26 : '100%',
            }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={evalData} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}
                onClick={(e) => {
                  if (e?.activeLabel != null) setCurrentPly(Math.round(Number(e.activeLabel)))
                }}
                onMouseMove={(e) => {
                  if (e?.activeLabel != null) setHoverPly(Math.round(Number(e.activeLabel)))
                }}
                onMouseLeave={() => setHoverPly(null)}>
                {/* Phase bands sit behind everything else */}
                {phaseBands.map((b, i) => (
                  <ReferenceArea
                    key={`phase-${i}`}
                    x1={b.from}
                    x2={b.to}
                    y1={-5}
                    y2={5}
                    fill={PHASE_COLORS[b.phase] ?? '#64748b'}
                    fillOpacity={0.18}
                    stroke="none"
                    ifOverflow="hidden"
                  />
                ))}
                {/* Domain bounded by the real move count, NOT evalData.length —
                    the array now also contains synthetic zero-crossing rows
                    at fractional plys, so evalData.length overshoots the last
                    move and leaves blank space on the right of the chart. */}
                <XAxis dataKey="ply" type="number" domain={[1, Math.max(1, game.moves.length)]} hide />
                <YAxis domain={[-5, 5]} hide />
                <ReferenceLine y={0} stroke="#e2e8f0" strokeWidth={1} strokeOpacity={0.5} />
                {/* Three Areas sharing the same data array (which now contains
                    synthetic (ply, 0) points at every zero crossing): two
                    solid fills clamped to their half of the y-axis, one
                    stroke-only Area for the real curve. type="linear" so each
                    fill polygon's edges go straight between data points —
                    monotone splines could undershoot the synthetic zero
                    anchors and bleed across the zero line. */}
                <Area
                  type="linear"
                  dataKey="evalWhite"
                  stroke="none"
                  fill="#f8fafc"
                  fillOpacity={1}
                  isAnimationActive={false}
                  baseValue={0}
                  dot={false}
                  activeDot={false}
                  connectNulls
                />
                <Area
                  type="linear"
                  dataKey="evalBlack"
                  stroke="none"
                  fill="#020617"
                  fillOpacity={1}
                  isAnimationActive={false}
                  baseValue={0}
                  dot={false}
                  activeDot={false}
                  connectNulls
                />
                <Area
                  type="linear"
                  dataKey="eval"
                  stroke="#94a3b8"
                  strokeWidth={1.5}
                  fill="none"
                  isAnimationActive={false}
                  baseValue={0}
                  dot={false}
                  activeDot={{ r: 0, fill: 'transparent', stroke: 'transparent' }}
                  connectNulls
                />
                {/* Hover cursor — only when it would land on a different
                    integer ply than the selected one, so we never stack two
                    lines on the same ply. */}
                {hoverPly != null && hoverPly !== currentPly && hoverPly >= 1 && (
                  <ReferenceLine x={hoverPly} stroke="#818cf8" strokeWidth={1} strokeOpacity={0.5} ifOverflow="hidden" />
                )}
                {/* Current-ply cursor */}
                {currentPly >= 1 && (
                  <ReferenceLine x={currentPly} stroke="#818cf8" strokeWidth={1.5} ifOverflow="hidden" />
                )}
                {/* Blunder / mistake / miss / inaccuracy markers */}
                {errorDots.map((d, i) => (
                  <ReferenceDot
                    key={`err-${i}`}
                    x={d.ply}
                    y={d.eval}
                    r={3.5}
                    fill={CLASS_COLORS[d.classification]}
                    stroke="#1f2937"
                    strokeWidth={1.5}
                    ifOverflow="visible"
                  />
                ))}
                {/* Tooltip kept only so AreaChart fires mouse events; cursor
                    and popup are both suppressed — the hover line above is
                    ours so it can snap to integer plys. */}
                <Tooltip
                  isAnimationActive={false}
                  wrapperStyle={{ display: 'none' }}
                  cursor={false}
                  content={() => null}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right panel — player headers + analysis */}
        <div className="flex flex-col gap-3 min-h-0">
          {/* Player strips at the top so the names sit beside the board
              instead of above/below it. Opponent first, then the user, so
              the column reads top-to-bottom like a scoresheet. */}
          <PlayerStrip {...topPlayer} toMove={topToMove} />
          <PlayerStrip {...bottomPlayer} toMove={bottomToMove} />

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
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
                Move classifications
              </span>
              <InfoTip label="Move classification definitions" wide align="right">
                <div className="space-y-1.5">
                  {(['best', 'good', 'inaccuracy', 'mistake', 'miss', 'blunder'] as const).map((cls) => (
                    <div key={cls} className="flex gap-2">
                      <span
                        className="font-bold capitalize whitespace-nowrap"
                        style={{ color: CLASS_COLORS[cls], minWidth: 70 }}
                      >
                        {CLASS_ICONS[cls]} {cls}
                      </span>
                      <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                        {CLASS_DESCRIPTIONS[cls]}
                      </span>
                    </div>
                  ))}
                </div>
              </InfoTip>
            </div>
            <div className="grid grid-cols-3 gap-x-2 gap-y-1.5 text-center text-xs">
              {(
                ['best', 'good', 'inaccuracy', 'mistake', 'miss', 'blunder'] as const
              ).map((cls) => (
                <div key={cls}>
                  <div className="font-bold text-lg leading-tight" style={{ color: CLASS_COLORS[cls] }}>
                    {classCounts[cls] || 0}
                  </div>
                  <div className="capitalize" style={{ color: 'var(--text-muted)' }}>
                    {cls}
                  </div>
                </div>
              ))}
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

          {/* Engine's best move from the current position */}
          {bestSan && (
            <div className="bg-[#16162a] border border-gray-700 rounded-lg p-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className="inline-block rounded-sm"
                  style={{ width: 10, height: 10, background: 'rgba(34, 197, 94, 0.85)' }}
                  aria-hidden
                />
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {whiteToMove ? 'White' : 'Black'} to play &mdash; engine suggests
                </span>
              </div>
              <span className="font-mono text-sm text-green-400">
                {bestSan}{playedMatchesBest && currentMove ? ' ✓' : ''}
              </span>
            </div>
          )}

          {/* Move list — `flex-1 min-h-0` fills the remaining height of the
              right column. Since the parent grid row is height-capped above,
              this naturally ends exactly where the eval chart ends on the
              left. */}
          <div className="bg-[#16162a] border border-gray-700 rounded-lg p-3 overflow-y-auto flex-1 min-h-0">
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

function NavBtn({ onClick, label, title }: { onClick: () => void; label: string; title?: string }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="w-7 h-7 rounded flex items-center justify-center bg-[#16162a] border border-gray-600 hover:bg-gray-700 text-xs transition-colors"
      style={{ color: 'var(--text-primary)' }}
    >
      {label}
    </button>
  )
}

function PlayerStrip({ name, rating, color, isUser, toMove }: {
  name: string
  rating: number | null
  color: 'white' | 'black'
  isUser: boolean
  toMove: boolean
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-[#16162a] border border-gray-700 rounded">
      <span
        className="inline-block rounded-sm border"
        style={{
          width: 14,
          height: 14,
          background: color === 'white' ? '#f1f5f9' : '#0b0b14',
          borderColor: color === 'white' ? '#cbd5e1' : '#6b7280',
        }}
        aria-label={`${color} pieces`}
      />
      <span className="text-white font-semibold truncate">{name}</span>
      {rating != null && (
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>({rating})</span>
      )}
      {isUser && (
        <span className="text-[10px] font-bold uppercase tracking-wide bg-indigo-600/30 text-indigo-300 px-1.5 py-0.5 rounded">
          You
        </span>
      )}
      {toMove && (
        <span className="ml-auto text-xs font-medium" style={{ color: '#22c55e' }}>
          ● to move
        </span>
      )}
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

function EvalBar({ cp, flipped }: { cp: number | null; flipped: boolean }) {
  // Lichess-style: the dark background represents black's share; an absolutely
  // positioned white block fills from the white player's side. Using absolute
  // positioning rather than a flex column avoids the percentage-height collapse
  // that left the white half invisible inside a flex parent with no resolved
  // intrinsic height.
  const whitePct = cp == null
    ? 50
    : Math.max(2, Math.min(98, 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * Math.max(-1500, Math.min(1500, cp)))) - 1)))
  const evalText = cp == null
    ? null
    : Math.abs(cp) >= 1000
      ? `${cp > 0 ? '+' : '−'}${(Math.abs(cp) / 100).toFixed(0)}`
      : `${cp > 0 ? '+' : cp < 0 ? '−' : ''}${(Math.abs(cp) / 100).toFixed(1)}`
  // The number sits at the bar's vertical midpoint and flips its colour based
  // on whichever side currently covers the centre line — so it's always
  // contrast-readable, no matter the orientation.
  const middleIsWhite = whitePct > 50
  return (
    <div
      className="rounded overflow-hidden relative flex-shrink-0 self-stretch"
      style={{ width: 22, background: '#1f2937' }}
    >
      {/* White block anchored to white's side of the board */}
      <div
        className="absolute left-0 right-0 transition-all duration-300"
        style={{
          height: `${whitePct}%`,
          background: '#f1f5f9',
          ...(flipped ? { top: 0 } : { bottom: 0 }),
        }}
      />
      {/* Midline at 50% as an "equal" reference */}
      <div
        className="absolute left-0 right-0 pointer-events-none"
        style={{ top: '50%', height: 1, background: 'rgba(0,0,0,0.35)' }}
      />
      {evalText && (
        <span
          className="absolute left-0 right-0 text-center font-bold leading-none select-none pointer-events-none"
          style={{
            fontSize: 10,
            top: '50%',
            transform: 'translateY(-50%)',
            color: middleIsWhite ? '#0b0b14' : '#f1f5f9',
          }}
        >
          {evalText}
        </span>
      )}
    </div>
  )
}

function formatClock(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}
