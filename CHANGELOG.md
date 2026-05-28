# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-05-29

UX-focused release: the Game Review page got a significant redesign, the openings analytics were unified into a single page with multiple views, and the win-rate model now matches the chess-world standard.

### Added
- **Unified Openings page** at `/players/:id/openings` with two tabs: **Win Rates** (list by named opening) and **Move Tree** (position-based, shows shared lines). Time-range filter is shared across tabs.
- **Chess-standard score rate** (`(wins + 0.5·draws) / games`) replaces the previous `wins / games` win rate as the headline metric on opening rows. Matches FIDE, lichess, and chess.com.
- **Stacked W-D-L bar** (Lichess-style green/grey/red) on every opening row and move-tree node.
- **Per-game accuracy + CPL** in the opening drill-down — the games listed under a row now show their accuracy% and avg CPL inline.
- **Grouping toggle** on the Win Rates tab: Flat / by ECO family (A–E) / by shared opening-name prefix. Choice persisted to localStorage.
- **Move tree W-D-L + score%** per node, plus a colour filter (All / ♔ White / ♚ Black) so the tree shows one repertoire at a time and a minimum-games-per-branch threshold (1 / 2 / 5 / 10).
- **Best-move arrow** drawn on the board during Game Review, sourced from the cached deepest `PositionEval` so no extra engine calls are made.
- **Engine-suggestion card** in the right-side panel showing the best move's SAN with a `✓` when the played move matched the engine's pick.
- **Lichess-style eval bar** (vertical, beside the board) with the eval text floating at the visual midline, contrast-flipped against whichever side covers the centre.
- **Lichess-style bottom eval chart** with solid white-above-zero / dark-below-zero fill (gradient hard-stop at the zero line), phase bands (opening / middlegame / endgame), blunder/mistake/miss dots colour-coded by classification, and a live cursor on the current ply.
- **Player strips** showing colour swatch, name, rating, `You` chip on the user's row, and a green `● to move` indicator on whichever side is to move at the current ply.
- **Navigation buttons** under the board (`⟨⟨ ⟨ N ⟩ ⟩⟩`) with keyboard-shortcut tooltips; arrow keys / Home / End still work.
- **Move Tree** dashboard nav card; the page existed at `/players/:id/openings` but had no entry from the dashboard.
- **`QueryError`** component wired into the analytics pages (Accuracy, Phase, Rating, Time, Openings list, Openings tree) so backend errors render a real card instead of a blank screen.
- **CPL / Score% explanation popups** consolidated into one `InfoTip` per page, listing all classifications with their definitions in a single wide popup.
- **Force-import button** on the dashboard (replaces the misleadingly-named "Re-import"). Same backend behaviour — pulls only games not already in the local DB.

### Changed
- **Game Review layout**: player strips moved to the right column so the board can claim the full vertical space; chart now lives flush below the board.
- **Board size-snap**: rendered size is now `floor(min(w, h, 920) / 8) * 8` so the chessboard's 8×8 grid never falls on a sub-pixel boundary (no more white hairline gaps between squares).
- **Opening tree analytics** (`build_opening_tree`): every move along a game's path now counts as a visit (not just user moves), so the tree no longer collapses to depth-1. Each node carries W-D-L counts and score rate. The key for sibling moves now uses `position_after.fen_key` instead of `position_before.fen_key`, so 1.e4, 1.d4, 1.c4 each get their own root branch (previously they all collapsed into one).
- **Eval bar**: solid two-tone with the eval number floating mid-bar in the contrasting colour; flips with board orientation.
- **CHANGELOG / version pinning** added to both `backend/pyproject.toml` and `frontend/package.json` (was a single source of truth missing).
- **App-wide shared formatters**: `lib/format.ts` consolidates `resultIcon`, `resultColor`, `resultLabel`, `colorIcon`; `lib/openings.ts` consolidates `scoreColor`, `relativeDate`; `components/WdlBar.tsx` is shared across the openings views.

### Fixed
- **N+1 / inefficient queries in opening analytics** stayed flagged but not yet refactored — see the open punch list.
- **Tooltip-popup overflow** on the right-side panel when the popup was wider than the column (`InfoTip` got `align="right"` for right-anchored popups).
- **Recharts hover artefact** — the bottom eval chart no longer shows a black-block tooltip cursor or active-dot circles; cursor is a thin indigo line and the popup card was removed.
- **Focus-ring outline** around the eval chart after clicking is suppressed.
- **`print()` in `entry.py`** replaced with `logging.error` per the no-print rule.

### Build / ops
- Stop hook (`.claude/settings.local.json`) closes any running `chess-review.exe`, rebuilds, and relaunches at the end of every Claude Code turn.
- Vite `chunkSizeWarningLimit` bumped to 1500 — meaningful only as a web app; the PyInstaller exe serves bundle from disk.

[1.1.0]: https://github.com/JOMOGO/chess-review/releases/tag/v1.1.0

## [1.0.0] — 2026-05-27

First public release. Windows desktop app, single-user, ships as a PyInstaller `.exe`.

### Added
- chess.com import: full archive fetch, newest-first, per-game commit.
- Position deduplication across games via normalized FEN key (halfmove/fullmove stripped).
- Two-pass Stockfish 18 analysis: inventory depth 14, deep re-analysis at depth 22 around eval swings > 100 cp.
- Engine pool with per-game engine pinning to keep the transposition table hot.
- Auto-download of a CPU-tier-matched Stockfish build on first launch (AVX-512 → BMI2 → x86-64), sized via CPUID.
- Cache layering: in-DB `PositionEval` → Lichess tablebase (≤7 pieces) → Lichess cloud eval (opening only) → local Stockfish.
- Move classification (best / good / inaccuracy / mistake / blunder) with dampened thresholds when both sides are already winning/losing.
- Phase classification (opening / middlegame / endgame) from ply + non-king piece count.
- Analytics pages: per-game review, opening leaks, phase performance, time-pressure curve, accuracy trend, rating performance, opening win rates.
- React 19 + Vite + Tailwind 4 frontend with `react-chessboard`, Recharts, TanStack Query, dark mode, import-progress toast.
- Native pywebview window wrapping a local FastAPI server; SPA fallback for any non-`/api/...` path.
- Auto-sized engine `Hash` MB per worker (≈ 1/4 RAM split across pool, clamped to [256, 1024]).
- Optional Syzygy tablebase support via `CHESS_REVIEW_SYZYGY_PATH`.

[1.0.0]: https://github.com/JOMOGO/chess-review/releases/tag/v1.0.0
