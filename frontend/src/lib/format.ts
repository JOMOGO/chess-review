/**
 * Cross-page formatting helpers. These are repeated in every page that lists
 * games or shows result/colour info; keep the shapes consistent here so
 * future styling changes only need to touch one place.
 */

export type UserResult = 'win' | 'loss' | 'draw'

/** Compact result icon used in game lists. */
export function resultIcon(result: string): string {
  switch (result) {
    case 'win':
      return '✓'
    case 'loss':
      return '✕'
    default:
      return '½'
  }
}

/** Tailwind text-color class for a result string. */
export function resultColor(result: string): string {
  switch (result) {
    case 'win':
      return 'text-green-400'
    case 'loss':
      return 'text-red-400'
    default:
      // Draws use the muted text colour so they don't visually compete with
      // wins/losses in long game lists.
      return ''
  }
}

/** Pieces icon for a colour string ('white' or 'black'). */
export function colorIcon(color: string): string {
  return color === 'white' ? '♔' : '♚'
}

/** Human label for a result string. */
export function resultLabel(result: string): string {
  switch (result) {
    case 'win':
      return 'Win'
    case 'loss':
      return 'Loss'
    default:
      return 'Draw'
  }
}
