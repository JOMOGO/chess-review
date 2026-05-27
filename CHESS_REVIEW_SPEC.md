# Chess Review Platform — Build Specification

> This document is the brief for building a self-hostable chess analysis platform that imports a player's full game history from chess.com (and later lichess) and finds **systemic weaknesses across all their games** using Stockfish 18. Per-game review is table stakes; the cross-game pattern detection is the actual product.

---

## 1. Project Overview

### What we are building

A web app that lets a user enter a chess.com username, ingests their entire game history, analyzes every position with Stockfish 18, and surfaces:

1. **Per-game review** (like chess.com Game Review).
2. **Opening tree with leak detection** — positions reached frequently where the user plays poorly.
3. **Phase performance** — opening vs middlegame vs endgame CPL.
4. **Time pressure curve** — CPL as a function of time remaining.
5. **Tactical motif blind spots** (v2) — clustering missed tactics by type.
6. **Endgame conversion stats** (v2).

### Why this is non-trivial

- **Compute economics**: 2,000–10,000 games per user, ~50 positions each, Stockfish 18 at meaningful depth = 50–300 CPU-hours per user if done naively. Must cache aggressively and reuse evaluations across games via position deduplication.
- **Pattern definitions**: "Average CPL" is useless on its own. The product value is in well-defined cluster detection.

### Target users

Initially: the developer (self-hosted on a TrueNAS box). Architecture must support multi-user later, but auth and billing are out of scope for v0.

### Non-goals

- Real-time game analysis (during live play)
- Mobile app (responsive web is enough)
- Social features, leaderboards, sharing
- Engine alternatives (lc0, Komodo). **Stockfish 18 only.**

---

## 2. Tech Stack (Decided — Do Not Substitute)

| Layer | Choice | Reason |
|---|---|---|
| **Backend language** | Python 3.12+ | `python-chess` is the gold standard, no real alternative |
| **Backend framework** | FastAPI | Async-native, fast, modern |
| **Database** | PostgreSQL 16+ | Position dedup needs strong indexing |
| **ORM** | SQLAlchemy 2.0 (async) + Alembic | Standard |
| **Job queue** | ARQ (Redis-backed) | Simpler than Celery, async-native |
| **Chess library** | `python-chess` >= 1.999 | PGN parsing, UCI engine wrapper, board logic |
| **Engine** | Stockfish 18 (compiled binary, called via UCI subprocess) | Released Jan 2026, +46 Elo over SF17, SFNNv10 net |
| **Frontend framework** | React 18 + Vite + TypeScript | Standard |
| **Board UI** | `react-chessboard` | Best maintained option |
| **Client-side engine** | `stockfish.wasm` (lazy loaded) | For ad-hoc "analyze this position deeper" |
| **State / data fetching** | TanStack Query (React Query v5) | Standard |
| **Charts** | Recharts | For phase/time/CPL visualizations |
| **Styling** | Tailwind CSS | Standard |
| **Deployment** | Docker Compose | Single-host self-hosting on TrueNAS |

**No microservices. No Kubernetes. No serverless.** Single backend service, single Postgres, single Redis, one or more worker processes, one React app.

---

## 3. Repository Structure

Monorepo layout:

```
chess-review/
├── docker-compose.yml
├── docker-compose.dev.yml
├── README.md
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── src/chess_review/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Pydantic settings
│   │   ├── db.py                # SQLAlchemy session, base
│   │   ├── models/              # ORM models (one file per aggregate)
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── api/                 # FastAPI routers
│   │   │   ├── players.py
│   │   │   ├── games.py
│   │   │   ├── analysis.py
│   │   │   └── insights.py
│   │   ├── ingestion/           # chess.com / lichess clients
│   │   │   ├── chesscom.py
│   │   │   ├── lichess.py
│   │   │   └── pgn_parser.py
│   │   ├── engine/              # Stockfish wrapper + lichess cloud eval
│   │   │   ├── stockfish_pool.py
│   │   │   ├── lichess_cloud.py
│   │   │   └── analysis_orchestrator.py
│   │   ├── analytics/           # The actual product: weak spot detection
│   │   │   ├── opening_tree.py
│   │   │   ├── phase_split.py
│   │   │   ├── time_pressure.py
│   │   │   ├── motif_classifier.py
│   │   │   └── endgame_conversion.py
│   │   ├── workers/             # ARQ task definitions
│   │   │   └── tasks.py
│   │   └── util/
│   │       ├── fen.py           # Dedup key, FEN normalization
│   │       └── pgn.py
│   └── tests/
│       └── ...
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── Dockerfile
│   ├── public/
│   │   └── stockfish/           # WASM engine files
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/                 # Generated or hand-written API client
│       ├── components/
│       │   ├── Board.tsx
│       │   ├── EvalBar.tsx
│       │   ├── MoveList.tsx
│       │   └── ...
│       ├── pages/
│       │   ├── PlayerImport.tsx
│       │   ├── GameReview.tsx
│       │   ├── OpeningTree.tsx
│       │   ├── PhaseDashboard.tsx
│       │   └── TimePressure.tsx
│       ├── lib/
│       │   ├── stockfish-worker.ts
│       │   └── chess-utils.ts
│       └── styles/
└── stockfish/
    └── Dockerfile               # Builds SF18 binary into a thin image
```

---

## 4. Phased Build Plan

Build strictly in order. Do not start a phase until the previous one is functional end-to-end.

### Phase 0 — Plumbing (must complete first)

- Docker Compose with Postgres, Redis, backend, worker, frontend.
- Alembic baseline migration.
- Health-check endpoint `GET /api/health` returning `{status, db, redis, engine}`.
- Stockfish 18 binary compiled and accessible from the worker container.
- Smoke test: backend can call `stockfish` and get a bestmove for the starting position.

**Acceptance:** `docker compose up` brings everything online; `GET /api/health` returns all green.

### Phase 1 — Game ingestion

- chess.com client: list archives, download monthly PGN bundles.
- PGN parser: extract one game per record, store games + positions.
- Position dedup via normalized FEN hash.
- Endpoint: `POST /api/players/{username}/import` enqueues a background job.
- Endpoint: `GET /api/players/{username}/import/status` returns progress.

**Acceptance:** importing a user with 200 games stores 200 games, ~10k positions (with dedup typically ~6–8k unique).

### Phase 2 — Analysis pipeline

- ARQ worker that consumes positions from a queue, analyzes them with Stockfish 18.
- Two-tier analysis: **inventory pass at depth 18** for every position, **deep pass at depth 25** for positions where the eval swings >100cp from previous move.
- Lichess cloud eval check before invoking local Stockfish.
- Store: bestmove, eval (cp or mate), PV (first 5 plies), depth, engine_version.

**Acceptance:** for an imported player, 100% of positions in their games have an eval after the job completes.

### Phase 3 — Per-game review UI

- Frontend page `/games/:id` showing board, move list, eval graph, classified moves (brilliant/best/good/inaccuracy/mistake/blunder).
- Classification thresholds (loss in cp from best move): `<10 best, <40 good, <100 inaccuracy, <300 mistake, >=300 blunder`. Exception: if both moves keep eval >+5.0 or both keep <-5.0, downgrade severity (already winning/losing).
- Client-side WASM Stockfish for "deeper look" on demand.

**Acceptance:** opening any game from the imported set renders a chess.com-style review without further server analysis.

### Phase 4 — Opening tree with leaks (the headline feature)

- Build a tree of the user's first 12 moves across all games.
- For each node (position) with >=5 visits, compute average CPL of the next move played by the user.
- UI: explorable tree, sortable by visit count and CPL. Each node clickable to see the games that passed through it.

**Acceptance:** for a user with 500+ games, the opening tree page renders in <1 second and the "biggest leaks" view surfaces at least 3 actionable repeat-blunder positions.

### Phase 5 — Phase performance dashboard

- Classify every move as **opening / middlegame / endgame** (see §8.3).
- Aggregate user CPL by phase, by color, over time.
- Recharts visualizations.

**Acceptance:** dashboard renders all three phases with sample size, average CPL, blunder rate, and a rolling trend over the last 6 months.

### Phase 6 — Time pressure curve

- chess.com PGN includes `%clk` annotations. Extract them.
- Plot user CPL bucketed by time-remaining-when-move-was-made (e.g. buckets: >120s, 60–120s, 30–60s, 10–30s, <10s).

**Acceptance:** curve renders for any user with rapid/blitz games; clearly shows degradation under 30s if it exists.

### Phase 7 — Lichess support

- Lichess client (ndjson games export, much more generous API).
- Unify ingestion under a `Provider` enum.

### Phase 8 (v2 territory) — Motif classifier and endgame conversion

- Skip until phases 0–7 are solid.

---

## 5. Data Model

All tables are owned by a single `chess_review` schema. UUIDs as primary keys throughout. Timestamps in UTC.

### `players`
| col | type | notes |
|---|---|---|
| id | uuid PK | |
| provider | text | `chesscom` or `lichess` |
| username | text | provider-side username |
| display_name | text | nullable |
| created_at | timestamptz | |
| last_imported_at | timestamptz | nullable |
| total_games_imported | int | denormalized counter |

Unique index on `(provider, lower(username))`.

### `games`
| col | type | notes |
|---|---|---|
| id | uuid PK | |
| player_id | uuid FK | the user whose perspective we're tracking |
| provider | text | |
| provider_game_id | text | chess.com or lichess game id |
| pgn | text | full raw PGN |
| white_username | text | |
| black_username | text | |
| white_rating | int | nullable |
| black_rating | int | nullable |
| user_color | text | `white` or `black` |
| result | text | `1-0`, `0-1`, `1/2-1/2` |
| user_result | text | `win`, `loss`, `draw` |
| time_control | text | e.g. `600+0`, `180+2` |
| time_class | text | `bullet`, `blitz`, `rapid`, `classical`, `daily` |
| eco | text | nullable, opening code |
| opening_name | text | nullable |
| played_at | timestamptz | |
| ply_count | int | |
| analyzed_at | timestamptz | nullable |
| created_at | timestamptz | |

Unique on `(provider, provider_game_id)`.

### `positions`
The dedup table. One row per **unique** position ever encountered.

| col | type | notes |
|---|---|---|
| id | uuid PK | |
| fen_key | text | normalized FEN: piece placement + side to move + castling + en passant only. Half-move clock and fullmove number stripped. |
| zobrist | bigint | optional, for fast lookup |
| material | int | piece count (for endgame classification) |
| created_at | timestamptz | |

Unique index on `fen_key`. This is the central dedup mechanism.

### `position_evals`
| col | type | notes |
|---|---|---|
| id | uuid PK | |
| position_id | uuid FK | |
| engine | text | `stockfish-18` or `lichess-cloud` |
| depth | int | |
| eval_cp | int | nullable if mate |
| eval_mate | int | nullable if not mate (positive = white mates) |
| best_move_uci | text | |
| pv | text | space-separated UCI moves, first 5 plies |
| nodes | bigint | nullable |
| computed_at | timestamptz | |

Index on `(position_id, depth desc)`. Keep multiple evals per position (different depths); query the deepest available.

### `game_moves`
The per-game timeline. One row per ply played in a game.

| col | type | notes |
|---|---|---|
| id | uuid PK | |
| game_id | uuid FK | |
| ply | int | 1-indexed |
| san | text | move in SAN, e.g. `Nf3` |
| uci | text | e.g. `g1f3` |
| position_before_id | uuid FK | position before the move |
| position_after_id | uuid FK | position after the move |
| clock_remaining_ms | int | nullable, extracted from %clk |
| eval_before_cp | int | nullable, copied from position_evals for convenience |
| eval_after_cp | int | nullable |
| cp_loss | int | how much eval dropped from best move (always >=0 from mover's perspective) |
| classification | text | `best`, `good`, `inaccuracy`, `mistake`, `blunder`, `brilliant` |
| phase | text | `opening`, `middlegame`, `endgame` |
| is_user_move | bool | |

Index on `(game_id, ply)`, and on `(game_id, is_user_move, classification)`.

### `import_jobs`
For tracking ingestion progress.

| col | type | notes |
|---|---|---|
| id | uuid PK | |
| player_id | uuid FK | |
| status | text | `pending`, `running`, `done`, `failed` |
| total_games | int | |
| imported_games | int | |
| analyzed_positions | int | |
| total_positions | int | |
| error | text | nullable |
| started_at | timestamptz | |
| completed_at | timestamptz | nullable |

---

## 6. External APIs

### chess.com Public API

- **Auth:** none required.
- **List archives:** `GET https://api.chess.com/pub/player/{username}/games/archives` → list of monthly URLs.
- **Download month:** `GET {archiveUrl}` → JSON with `games[]`, each has a `pgn` field.
- **Rate limit:** be polite. Sleep 250ms between requests; honor 429s with exponential backoff.
- **User-Agent header is required.** Set it to something identifying like `chess-review/0.1 (your-email@example.com)`.

### Lichess Cloud Eval API

- **Endpoint:** `GET https://lichess.org/api/cloud-eval?fen={FEN}&multiPv=1`
- **Returns:** `{ pvs: [{ moves, cp | mate }], depth, knodes }` or 404 if not cached.
- **Cost:** free, no auth. Cached positions return instantly.
- **Coverage:** essentially every opening and most early middlegame positions are in their cache. Hit rate for typical games is ~30-50% of positions.
- **Strategy:** always query this *before* invoking local Stockfish. Store result under `engine='lichess-cloud'`. If the depth is acceptable (>=20), do not re-analyze locally for the inventory pass.

### Lichess Games Export (Phase 7)

- `GET https://lichess.org/api/games/user/{username}?max=10000&clocks=true&evals=false&opening=true` returns ndjson PGN. Very generous, supports auth tokens for higher rate limits.

---

## 7. Stockfish Integration

### Binary

Build SF18 from source in `stockfish/Dockerfile`:

```dockerfile
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch sf_18 https://github.com/official-stockfish/Stockfish.git
WORKDIR /src/Stockfish/src
RUN make -j$(nproc) profile-build ARCH=x86-64-bmi2
RUN strip stockfish

FROM debian:bookworm-slim
COPY --from=build /src/Stockfish/src/stockfish /usr/local/bin/stockfish
ENTRYPOINT ["/usr/local/bin/stockfish"]
```

For TrueNAS deployment (likely modern Intel/AMD), `x86-64-bmi2` is the right ARCH. The worker image should COPY this binary in:

```dockerfile
COPY --from=chess-review-stockfish:latest /usr/local/bin/stockfish /usr/local/bin/stockfish
```

### Engine pool

`engine/stockfish_pool.py` should manage a pool of `chess.engine.SimpleEngine` instances (use `chess.engine.popen_uci`). Configurable concurrency via env var `SF_WORKERS` (default: half of `os.cpu_count()`). UCI options to set per engine:

```python
{
    "Threads": 1,                   # one thread per worker, more workers instead
    "Hash": 256,                    # MB
    "UCI_ShowWDL": "true",          # optional
}
```

### Analysis call

```python
import chess.engine

info = engine.analyse(
    board,
    chess.engine.Limit(depth=target_depth),
    multipv=1,
)
# info: {"score": PovScore, "pv": [Move, ...], "depth": int, "nodes": int}
```

Convert `PovScore` to cp from White's perspective and store. Persist mate scores separately.

### Two-tier strategy

```
for each game:
    inventory_depth = 18
    deep_depth = 25
    
    1. For every position in the game, get an eval at depth >= 18.
       a. Check lichess-cloud cache first.
       b. If miss or depth < 18, queue local SF inventory job.
    2. After inventory, for moves where |eval_before - eval_after| > 100cp,
       re-queue both positions for deep analysis at depth 25.
    3. Persist all evals.
```

---

## 8. Core Algorithms

### 8.1 FEN normalization (the dedup key)

```python
def fen_key(board: chess.Board) -> str:
    """Strip half-move clock and fullmove number for position dedup."""
    parts = board.fen().split(" ")
    # parts = [placement, side, castling, ep, halfmove, fullmove]
    return " ".join(parts[:4])
```

This is the single most important function in the codebase. All position lookups go through it.

### 8.2 Move classification

```python
def classify(cp_before: int, cp_after_actual: int, cp_after_best: int, mover_is_white: bool) -> str:
    """All evals from White's perspective."""
    # Convert to mover's perspective
    sign = 1 if mover_is_white else -1
    best = sign * cp_after_best
    actual = sign * cp_after_actual
    loss = max(0, best - actual)
    
    # Both winning/losing dampening
    if best > 500 and actual > 300:
        return "good" if loss < 200 else "inaccuracy"
    if best < -300:
        return "good"  # already lost, any move is "fine"
    
    if loss < 10:   return "best"
    if loss < 40:   return "good"
    if loss < 100:  return "inaccuracy"
    if loss < 300:  return "mistake"
    return "blunder"
```

"Brilliant" classification is intentionally deferred. Doing it well is hard and not core to v0.

### 8.3 Phase classification

Use piece count and move number together:

```python
def classify_phase(board: chess.Board, ply: int) -> str:
    total_non_king = sum(
        1 for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.piece_type != chess.KING
    )
    
    if ply <= 20 and total_non_king >= 24:
        return "opening"
    if total_non_king <= 8:
        return "endgame"
    return "middlegame"
```

Document this heuristic prominently; tweak based on empirical results.

### 8.4 Opening tree with leak detection

Pseudocode:

```python
def build_opening_tree(player_id, max_ply=24):
    """
    Walk through every game's first max_ply plies.
    Tree node = (fen_key, user_color).
    For each visit, record what move the user played next (if it was their turn)
    and the cp_loss of that move.
    
    Surface "leaks": nodes with:
      - visit_count >= 5
      - avg_cp_loss >= 50
      - rank by visit_count * avg_cp_loss
    """
```

The tree should be materialized in a `opening_tree_nodes` table for fast UI rendering, or computed on demand and cached in Redis with a TTL. Pick materialized; recompute on each new game import.

### 8.5 Time pressure curve

For each user move where `clock_remaining_ms` is known, bucket:

```
>120s, 60-120s, 30-60s, 10-30s, <10s
```

Compute average CPL per bucket. Only include rapid/blitz games (classical has too few time-pressure data points; bullet is noisy).

---

## 9. Backend API

All endpoints prefixed `/api`. JSON in/out. No auth for v0. CORS open to the frontend origin from env.

### Players

- `POST /api/players` body: `{provider, username}` — creates player record if not exists. Returns player.
- `GET /api/players/{id}` — returns player + summary stats.
- `POST /api/players/{id}/import` — enqueues import job. Returns `{job_id}`.
- `GET /api/players/{id}/import/status` — returns latest import job state.

### Games

- `GET /api/players/{id}/games?limit=50&offset=0&time_class=blitz` — paginated list.
- `GET /api/games/{id}` — full game with moves, evals, classifications.

### Analysis

- `POST /api/games/{id}/analyze` — force re-analysis (rare).
- `GET /api/positions/{fen_key}/eval?depth_min=18` — fetch deepest available eval.

### Insights

- `GET /api/players/{id}/insights/opening-tree?min_visits=5&max_ply=24`
- `GET /api/players/{id}/insights/phase-performance?since=2025-01-01`
- `GET /api/players/{id}/insights/time-pressure?time_class=blitz`

All insight endpoints accept date range filters.

---

## 10. Frontend

### Pages

1. **`/`** — landing. Input field: chess.com username. Button: "Import & Analyze". Polls import status.
2. **`/players/:id`** — overview dashboard. Cards: total games, win rate, top opening, biggest leak.
3. **`/players/:id/games`** — paginated game list, filterable by color, time class, result.
4. **`/games/:id`** — review page (board + eval bar + move list with classifications + eval graph).
5. **`/players/:id/openings`** — opening tree explorer.
6. **`/players/:id/phases`** — phase performance dashboard.
7. **`/players/:id/time`** — time pressure curve.

### Board component

Use `react-chessboard`. Support: click-to-move, arrow overlays for best move PV, square highlights for last move and classification color.

### Classification colors

- **best**: green
- **good**: light green
- **inaccuracy**: yellow
- **mistake**: orange
- **blunder**: red
- **brilliant**: cyan (reserved, not used in v0)

### Client-side Stockfish

Lazy-load WASM Stockfish on the review page. Provide a "Deeper analysis" button that runs depth 28+ in the browser on the current position. Do not send these results back to the server.

### State management

- TanStack Query for all API calls (5-min staleTime for evals, instant for current game).
- No global state library; lift state where needed.

---

## 11. Infrastructure

### `docker-compose.yml` (production)

Services:
- `postgres` (image: `postgres:16-alpine`, volume for data, healthcheck)
- `redis` (image: `redis:7-alpine`)
- `stockfish` (built image, used only as a binary source via multi-stage in workers)
- `backend` (FastAPI via uvicorn, 2 workers)
- `worker` (ARQ worker process, scales independently)
- `frontend` (nginx serving built React app)

Environment variables (`.env`):
```
DATABASE_URL=postgresql+asyncpg://chess:chess@postgres:5432/chess_review
REDIS_URL=redis://redis:6379/0
STOCKFISH_PATH=/usr/local/bin/stockfish
SF_WORKERS=4
LICHESS_CLOUD_ENABLED=true
CHESSCOM_USER_AGENT="chess-review/0.1 (contact@example.com)"
CORS_ORIGIN=http://localhost:5173
```

### Resource sizing (for a single-user TrueNAS deployment)

- Postgres: 2GB RAM, 50GB disk per heavy user
- Redis: 512MB RAM
- Worker: 2 CPU cores per SF worker, scale `replicas` based on host
- Backend: 1 CPU, 512MB RAM

### Local dev

`docker-compose.dev.yml` overlay should mount source as volumes, run uvicorn with `--reload`, run Vite dev server, expose ports 8000 (backend) and 5173 (frontend).

---

## 12. Testing Strategy

### Backend

- **Unit tests** (pytest) for:
  - `fen_key()` (critical — test castling rights, en passant, side to move all roundtrip)
  - `classify()` (table-driven test, ~20 cases including edge cases like already-winning)
  - `classify_phase()`
  - PGN parser edge cases (variations, comments, headers with quotes)
- **Integration tests** for chess.com client using `respx` to mock HTTP.
- **Engine smoke test** that spawns real Stockfish and confirms it returns a bestmove for the start position.

### Frontend

- Vitest + React Testing Library for components.
- One Playwright end-to-end test: import a tiny known PGN, verify a known blunder shows up classified as a blunder.

### CI

GitHub Actions workflow that runs lints, tests, and builds Docker images on every push.

---

## 13. Development Setup Instructions

Add a thorough `README.md` at the repo root with:

1. Prerequisites: Docker, Docker Compose, ~4GB free RAM.
2. `cp .env.example .env` and edit.
3. `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`.
4. Visit `http://localhost:5173`.
5. Backend at `http://localhost:8000/docs` (FastAPI swagger).
6. How to run migrations: `docker compose exec backend alembic upgrade head`.
7. How to run tests: `docker compose exec backend pytest`.

---

## 14. Acceptance Criteria (the agent's definition of done for v0)

After phases 0–6 are complete, the following must work end-to-end:

1. From a clean `docker compose up`, I can enter a chess.com username and click Import.
2. Within a reasonable time (depends on game count and hardware), import status reaches `done`.
3. I can open the player dashboard and see total games, win rate, and biggest leak surfaced.
4. I can open any individual game and see a chess.com-style review with eval bar, classifications, and a clickable move list. The eval graph reflects real Stockfish 18 evaluations.
5. I can navigate to the opening tree and see frequently-visited nodes ranked by leak severity, with the games drillable.
6. I can navigate to the phase dashboard and see opening/middlegame/endgame CPL split.
7. I can navigate to the time pressure page and see the CPL-vs-time-remaining curve.
8. All pages render in <1 second for a 500-game user, after initial analysis is complete.
9. All evals are cached: re-opening a game does not re-invoke Stockfish.

---

## 15. Hard Rules

- **Never** call Stockfish for a position already analyzed at equal or greater depth.
- **Always** call `fen_key()` for position lookups; never compare raw FENs.
- **Never** block the FastAPI event loop with synchronous engine calls — engine work runs in the ARQ worker.
- **All datetimes are timezone-aware UTC** in storage; convert at the UI edge.
- **No `print()`** in backend code; use `logging` with structured output.
- **Type hints on every public function.** `mypy --strict` should pass on the `analytics/` and `engine/` modules at minimum.
- **No silent failures.** Every `except` either re-raises or logs at WARNING/ERROR with context.

---

## 16. Out of Scope for v0

Do not implement, even if it seems easy:

- Multi-user authentication.
- Email / notifications.
- Game annotations / comments by the user.
- Comparing two players.
- Tournament import.
- Mobile app.
- Anything related to "training" or "drills" (this is an analysis tool, not Chessable).

Build the v0 scope tight and ship it. v1 considerations (motif classifier, endgame conversion, lichess import) are documented in `docs/ROADMAP.md` (create this file with a brief stub for each).
