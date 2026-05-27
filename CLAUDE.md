# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this actually is

A single-user **Windows desktop application** that imports a chess.com player's full game history, analyzes every position with Stockfish 18, and surfaces cross-game weaknesses (opening leaks, phase performance, time pressure, accuracy trend, opening win rates, rating performance).

The original brief for this project described a Docker/Postgres/Redis/ARQ web service; the real code is a PyInstaller-packaged native app. Trust the code over any older spec docs when they conflict:

| Spec says | Code actually uses |
|---|---|
| Docker Compose, Postgres, Redis, ARQ | PyInstaller `.exe`, SQLite (`aiosqlite`), in-process `TaskManager` |
| Worker process | Same-process async task queue with semaphore-limited concurrency |
| Containerized Stockfish binary | Auto-downloaded Windows Stockfish 18, CPU-tier-matched via CPUID |
| nginx + React build | FastAPI mounts the Vite `dist/` directly; pywebview embeds it in a native window |

`docs/ROADMAP.md` lists v1 features (motif classifier, endgame conversion, Lichess import, multi-user).

## Architecture

### Entry point and process model
- `backend/src/chess_review/entry.py` is the app entry. It picks a free port, starts uvicorn on a background thread, polls `/api/health`, then opens a `pywebview` window pointing at the local server. Closing the window shuts uvicorn down.
- `backend/src/chess_review/main.py` defines the FastAPI app and a `lifespan` that:
  1. `Base.metadata.create_all` against SQLite (no Alembic migration runs at startup — the `alembic/versions/` folder is empty).
  2. Starts the `TaskManager` (async in-process queue).
  3. Auto-downloads Stockfish via `engine/sf_download.py` if no binary exists in the app-data dir.
  4. Starts the `StockfishPool` (one `chess.engine.UciProtocol` per worker).
  5. Mounts `frontend/dist` as static + SPA fallback so any non-`/api/...` path serves `index.html`.

### Data paths (`util/paths.py`)
PyInstaller-aware. In a frozen exe, app data lives in `%LOCALAPPDATA%/ChessReview/` (DB, log, downloaded Stockfish). In dev, it lives in `<repo>/data/`. Static frontend is `sys._MEIPASS/static` when frozen, `<repo>/frontend/dist` in dev.

### Analysis pipeline (the core of the product)
`taskqueue/tasks.py::import_and_analyze` runs import and analysis **concurrently** via `asyncio.gather`:
- `_import_games` downloads chess.com archives newest-first, parses each game with `ingestion/pgn_parser.py`, deduplicates positions via `util/fen.py::fen_key` (the single most important function — strips halfmove/fullmove from FEN), commits per game, and pushes game IDs onto an internal queue.
- `_analyze_from_queue` consumes that queue with up to `sf_pool.pool_size` games in flight at once. **Each game pins one Stockfish engine for its entire lifetime** (`sf_pool.acquire`/`release`) so the transposition table stays warm across the game's overlapping positions.

Per-position analysis priority in `engine/analysis_orchestrator.py`:
1. **In-DB cache** — `PositionEval` rows at >= target depth, bulk-queried per game.
2. **Lichess tablebase** (`lichess_tablebase.py`) — perfect play in <=7-piece endgames.
3. **Lichess cloud eval** (`lichess_cloud.py`) — skipped past `settings.cloud_max_ply` (default 40), coverage tanks past the opening.
4. **Local Stockfish** on the pinned engine via `StockfishPool.analyse_on` (no semaphore handoff).

Two-tier strategy: an **inventory pass** at `inventory_depth` (default 14) for every position, then a **deep pass** at `deep_depth` (default 22) re-runs the positions on either side of any move whose eval swings by more than `swing_threshold_cp` (default 100). Forced-move positions (exactly one legal move) skip the search and copy the after-position's eval.

After all evals land, `classify_move` (in `analysis_orchestrator.py`) labels each move best/good/inaccuracy/mistake/blunder using cp loss thresholds 10/40/100/300, with dampening when both before and after are already winning/losing. `classify_phase` uses ply + non-king piece count.

### Stockfish pool
`engine/stockfish_pool.py`. Manages N `python-chess` engine subprocesses (`creationflags=CREATE_NO_WINDOW` on Windows so no console pops up). `analyse(game=...)` passes the game token straight through to `python-chess` — it only sends `ucinewgame` when the token changes, so a stable per-game value keeps the TT hot. `auto_hash_mb` sizes `Hash` MB per engine targeting ~1/4 of total RAM split across the pool, clamped to [256, 1024]. Detects RAM via `GlobalMemoryStatusEx` on Windows.

`engine/cpu_detect.py` runs raw CPUID via shellcode in `VirtualAlloc`'d executable memory (Windows-only) to pick the best Stockfish build tier (`avx512icl` → `bmi2` → `x86-64` fallback chain).

### Frontend
React 19 + Vite + Tailwind 4 + TanStack Query + `react-chessboard` + Recharts + `react-router-dom` v7. `frontend/vite.config.ts` proxies `/api` to `http://localhost:18765` for dev. Routes live in `App.tsx`; pages in `src/pages/`; the API client (with all response type defs) is `src/api/client.ts`. Dark mode + import progress toast persist via `lib/storage.ts` (localStorage).

### Configuration
`config.py` uses `pydantic-settings` with `CHESS_REVIEW_` env prefix and `.env`. Defaults are tuned for the desktop case: `sf_workers=0` (auto = `cores - 2`, leaving 2 cores free for the user, min 1), `sf_hash_mb=0` (auto), `port=18765`, no DB URL (falls back to `sqlite+aiosqlite:///<app_data>/chess_review.db`).

## Commands

All commands assume the repo root `C:\code\chess-review` (PowerShell paths). The dev loop is **frontend Vite on :5173 + backend uvicorn on :18765**; Vite proxies `/api` so you point your browser at :5173.

### Backend (Python 3.12+)
```powershell
# Install editable + dev deps
pip install -e "backend[dev]"

# Run the FastAPI server in dev mode (auto-reload, CORS enabled for :5173)
$env:CHESS_REVIEW_DEV_MODE = "true"
uvicorn chess_review.main:app --host 127.0.0.1 --port 18765 --reload --app-dir backend/src

# Run the full desktop app (uvicorn + pywebview window)
python -m chess_review.entry   # or: chess-review  (after pip install -e)

# Tests (none exist yet under backend/tests/, but the harness is configured)
pytest backend            # all
pytest backend -k fen_key # single test by keyword
```

### Frontend
```powershell
cd frontend
npm install
npm run dev      # Vite dev server on :5173, proxies /api -> :18765
npm run build    # tsc -b && vite build -> frontend/dist/
npm run lint     # eslint .
```

### Building the distributable `.exe`
```powershell
# Builds frontend, runs PyInstaller against chess_review.spec, copies Stockfish next to the exe
python build.py
# Output: dist/chess-review.exe
```
The spec file (`chess_review.spec`) bundles `frontend/dist/` as `static/` and lists hidden imports for `aiosqlite`, `chess.engine`, `webview.platforms.edgechromium`, etc. PyInstaller is in the `[build]` extras: `pip install -e "backend[build]"`.

### Env overrides
Anything in `config.py::Settings` accepts the `CHESS_REVIEW_` prefix, e.g.:
- `CHESS_REVIEW_INVENTORY_DEPTH=18` / `CHESS_REVIEW_DEEP_DEPTH=25` — engine depths
- `CHESS_REVIEW_SF_WORKERS=4` — override the half-of-cores default
- `CHESS_REVIEW_SF_HASH_MB=512` — override the auto-sizing
- `CHESS_REVIEW_SYZYGY_PATH=...` — directory of `.rtbw/.rtbz` for in-engine tablebase probing
- `CHESS_REVIEW_LICHESS_CLOUD_ENABLED=false` — disable cloud lookups
- `CHESS_REVIEW_STOCKFISH_PATH=...` — skip the auto-download/CPU-detect, use this binary

## Rules and invariants worth keeping

These come from the spec and are enforced (or should be) in the code:

- **Always** call `fen_key()` for position lookups; never compare raw FENs. Halfmove/fullmove must be stripped.
- **Never** re-analyze a position already evaluated at >= the target depth — the cache is queried in bulk per game before any engine call.
- **Never** block FastAPI's event loop with synchronous engine calls. All engine work runs through `StockfishPool` which uses `chess.engine.popen_uci` (async).
- **All timestamps are timezone-aware UTC** in storage (see `_utcnow` in `models/tables.py`).
- **No `print()`** — use `logging`. The app writes to both stderr and `<app_data>/chess_review.log`.
- `mypy --strict` is configured in `pyproject.toml` (no module excludes); the `analytics/` and `engine/` packages were the spec's hard target.
- When extending the analysis pipeline, preserve **engine pinning per game** — pulling that out destroys TT locality and roughly doubles wall time on large imports.

## Things that look weird but are intentional

- `subprocess.CREATE_NO_WINDOW` is passed to every Stockfish/Python `Popen` on Windows so child consoles don't flash. If you spawn a subprocess, follow the pattern.
- `engine/cpu_detect.py` JITs shellcode to call `CPUID` directly because there's no stdlib API for it. Touch with care; it's `ctypes` + `VirtualAlloc`.
- `taskqueue/manager.py` is a deliberate replacement for ARQ/Redis (single-user app, no need). `JobState` is passed into the task function as a `progress=` kwarg so tasks can update counters live.
- The cloud-eval skip past `cloud_max_ply=40` exists because Lichess's cache hit rate cliffs after the opening; querying past that just adds latency.
- `lifespan` calls `Base.metadata.create_all` instead of running Alembic. `backend/alembic/versions/` is empty — schema lives in `models/tables.py`. If you need to evolve the schema in production, write a migration and wire Alembic into the lifespan or a CLI command.
