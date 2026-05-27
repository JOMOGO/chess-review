# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
