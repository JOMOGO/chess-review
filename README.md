# Chess Review

A single-user **Windows desktop app** that imports your entire chess.com game
history, analyzes every position with **Stockfish 18**, and surfaces patterns
across all your games — not just one-off blunders.

## What it shows you

- **Per-game review** with a Lichess-style eval bar, best-move arrow (sourced from the cached engine line, no extra calls), bottom eval chart with phase bands and blunder/mistake dots, and move classification (best / good / inaccuracy / mistake / blunder / miss).
- **Unified Openings page** with two views of the same data: a *Win Rates* list grouped by ECO family or name prefix (collapsible) and a *Move Tree* showing your moves stacked by shared lines. Win rate uses the chess-standard score = (W + 0.5·D) / N.
- **Move Tree** with per-position W-D-L bars, score%, and a colour filter so you can view your repertoire one colour at a time.
- **Phase performance** — opening vs. middlegame vs. endgame CPL.
- **Time-pressure curve** — accuracy as a function of clock remaining.
- **Accuracy trend** over time, **rating performance** by opponent rating bucket, **tactical motif** classifier for missed forks/pins/skewers, and **endgame conversion** stats.

## How it works

- Imports chess.com archives newest-first, parses PGNs with `python-chess`, and **deduplicates positions** across games via a normalized FEN key (halfmove/fullmove stripped).
- **Two-pass Stockfish analysis**: shallow inventory at depth 14, deep re-analysis at depth 22 on the positions on either side of any move whose eval swings by more than 100 cp.
- **Engine pinned per game** so the transposition table stays hot across overlapping positions in the same game.
- **Cache layered before the engine**: in-DB `PositionEval` rows → Lichess tablebase (≤7 pieces) → Lichess cloud eval (opening only) → local Stockfish.
- **CPU-tier-matched Stockfish build** auto-downloaded on first launch (AVX-512 → BMI2 → x86-64 fallback chain), sized via CPUID.

## Install

Download `chess-review.exe` from the [Releases](../../releases) page and double-click.

App data (SQLite DB, log, downloaded Stockfish binary) lives in `%LOCALAPPDATA%\ChessReview\`. Uninstalling is just deleting the `.exe` and that folder.

## Build from source

Requires Python 3.12+ and Node 20+ on Windows.

```powershell
pip install -e "backend[dev,build]"
cd frontend; npm install; cd ..
python build.py     # produces dist/chess-review.exe
```

## Dev loop

```powershell
# Terminal 1 — backend (FastAPI on :18765)
$env:CHESS_REVIEW_DEV_MODE = "true"
uvicorn chess_review.main:app --reload --app-dir backend/src --port 18765

# Terminal 2 — frontend (Vite on :5173, proxies /api to :18765)
cd frontend
npm run dev
```

Then open <http://localhost:5173>.

## Configuration

Anything in `backend/src/chess_review/config.py::Settings` accepts a `CHESS_REVIEW_` env prefix or an entry in `.env`. Useful knobs:

| Variable | Default | Effect |
|---|---|---|
| `CHESS_REVIEW_INVENTORY_DEPTH` | 14 | Shallow-pass depth |
| `CHESS_REVIEW_DEEP_DEPTH` | 25 | Deep-pass depth around eval swings |
| `CHESS_REVIEW_SF_WORKERS` | `cores - 2` (min 1) | Stockfish pool size; leaves 2 cores free for the user |
| `CHESS_REVIEW_SF_THREADS` | 1 | Threads per engine; raise for fewer-but-faster games |
| `CHESS_REVIEW_SF_HASH_MB` | auto (≈ 1/4 RAM ÷ pool) | Per-engine hash, clamped to [256, 1024] |
| `CHESS_REVIEW_SYZYGY_PATH` | unset | Directory of `.rtbw/.rtbz` tablebase files |
| `CHESS_REVIEW_LICHESS_CLOUD_ENABLED` | `true` | Use Lichess cloud eval cache for opening positions |
| `CHESS_REVIEW_STOCKFISH_PATH` | unset | Skip auto-download / CPU detect, use this binary |

## Tech stack

Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async) + SQLite (`aiosqlite`), `python-chess`, an in-process async task queue (no Redis/ARQ), pywebview for the native window, PyInstaller for packaging.

Frontend: React 19, Vite, TypeScript, Tailwind 4, TanStack Query, `react-chessboard`, Recharts, react-router v7.

Engine: Stockfish 18, called via UCI subprocess from a per-process engine pool.

## License

[GPL-3.0-only](LICENSE). The bundled Stockfish 18 binary is also GPL-3.0-only.
