/**
 * Lichess-style stacked W-D-L bar. Green / slate-grey / red segments
 * proportional to wins / draws / losses. Empty (zero games) renders as a
 * neutral placeholder so layouts stay aligned.
 *
 * Hover surfaces the raw counts plus pure win% and chess-standard score%.
 */
export default function WdlBar({
  wins,
  draws,
  losses,
  width = 100,
}: {
  wins: number
  draws: number
  losses: number
  width?: number
}) {
  const total = wins + draws + losses
  if (total === 0) {
    return (
      <div
        className="h-2 rounded"
        style={{ background: 'var(--border)', width, minWidth: width }}
      />
    )
  }
  const w = (wins / total) * 100
  const d = (draws / total) * 100
  const l = (losses / total) * 100
  const winRate = Math.round((wins / total) * 100)
  const scoreRate = Math.round(((wins + 0.5 * draws) / total) * 100)
  return (
    <div
      className="h-2 rounded overflow-hidden flex"
      style={{ width, minWidth: width }}
      title={`+${wins} =${draws} -${losses} · Win ${winRate}% · Score ${scoreRate}%`}
    >
      {w > 0 && <div style={{ width: `${w}%`, background: '#22c55e' }} />}
      {d > 0 && <div style={{ width: `${d}%`, background: '#6b7280' }} />}
      {l > 0 && <div style={{ width: `${l}%`, background: '#ef4444' }} />}
    </div>
  )
}
