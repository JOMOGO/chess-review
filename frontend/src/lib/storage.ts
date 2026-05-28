const PLAYER_KEY = 'chess_review_player'
const IMPORT_KEY = 'chess_review_import'
const IMPORT_EVENT = 'chess-review-import-changed'
const TOAST_VISIBLE_KEY = 'chess_review_toast_visible'

interface StoredPlayer {
  id: string
  username: string
}

export interface StoredImport {
  playerId: string
  jobId: string
}

export function getStoredPlayer(): StoredPlayer | null {
  try {
    const raw = localStorage.getItem(PLAYER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setStoredPlayer(player: StoredPlayer): void {
  localStorage.setItem(PLAYER_KEY, JSON.stringify(player))
}

export function getStoredImport(): StoredImport | null {
  try {
    const raw = localStorage.getItem(IMPORT_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setStoredImport(imp: StoredImport | null): void {
  if (imp) {
    localStorage.setItem(IMPORT_KEY, JSON.stringify(imp))
    // Auto-show toast when new import starts
    setToastVisible(true)
  } else {
    localStorage.removeItem(IMPORT_KEY)
  }
  window.dispatchEvent(new Event(IMPORT_EVENT))
}

export function isToastVisible(): boolean {
  return localStorage.getItem(TOAST_VISIBLE_KEY) !== 'false'
}

export function setToastVisible(v: boolean): void {
  localStorage.setItem(TOAST_VISIBLE_KEY, v ? 'true' : 'false')
  window.dispatchEvent(new Event(IMPORT_EVENT))
}

export function onImportChanged(callback: () => void): () => void {
  window.addEventListener(IMPORT_EVENT, callback)
  return () => window.removeEventListener(IMPORT_EVENT, callback)
}
