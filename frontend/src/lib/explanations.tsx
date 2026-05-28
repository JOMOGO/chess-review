/** Standard reusable copy for CPL — keep one source of truth. */
export const CPL_EXPLANATION = (
  <>
    <strong>CPL = Centipawn Loss.</strong> Stockfish compares your move
    against the engine's best move and measures how much eval you gave
    up, in hundredths of a pawn. Lower is better.
    <span className="block mt-1" style={{ color: 'var(--text-secondary)' }}>
      Rough ranges: 0-20 strong, 20-50 solid, 50-100 inaccurate, 100+ a mistake.
    </span>
  </>
)
