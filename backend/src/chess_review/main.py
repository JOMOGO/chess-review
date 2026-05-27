"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from chess_review.api.analysis import router as analysis_router
from chess_review.api.games import router as games_router
from chess_review.api.insights import router as insights_router
from chess_review.api.players import router as players_router
from chess_review.config import settings
from chess_review.db import Base, async_session, engine
from chess_review.engine.stockfish_pool import StockfishPool, auto_hash_mb
from chess_review.schemas import HealthResponse
from chess_review.taskqueue.manager import TaskManager
from chess_review.util.paths import get_static_dir

from chess_review.util.paths import get_app_data_dir

_log_file = get_app_data_dir() / "chess_review.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(_log_file), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)
logger.info("Log file: %s", _log_file)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    # Auto-detect worker count
    import os
    worker_count = settings.sf_workers or max(1, (os.cpu_count() or 4) // 2)
    logger.info("Using %d Stockfish workers (cores: %s)", worker_count, os.cpu_count())

    # Start task manager
    tm = TaskManager(max_concurrent=worker_count)
    await tm.start()
    app.state.task_manager = tm

    # Ensure Stockfish binary exists (auto-download if needed)
    from chess_review.engine.sf_download import ensure_stockfish

    sf_path = settings.stockfish_path  # explicit override from env
    if not sf_path:
        resolved = await ensure_stockfish()
        sf_path = str(resolved) if resolved else ""

    # Pick Hash size: explicit override wins, otherwise auto-size by pool + RAM.
    hash_mb = settings.sf_hash_mb if settings.sf_hash_mb > 0 else auto_hash_mb(worker_count)
    logger.info("Stockfish Hash: %d MB per engine (%d engines)", hash_mb, worker_count)

    # Start Stockfish pool
    sf = StockfishPool(
        sf_path,
        pool_size=worker_count,
        hash_mb=hash_mb,
    )
    await sf.start()
    app.state.sf_pool = sf

    yield

    await tm.stop()
    await sf.stop()
    await engine.dispose()


app = FastAPI(title="Chess Review", version="0.1.0", lifespan=lifespan)

# CORS for dev mode (Vite on :5173)
if settings.dev_mode:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

# API routes
app.include_router(players_router, prefix="/api")
app.include_router(games_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(insights_router, prefix="/api")


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # Check DB
    db_ok = False
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("DB health check failed")

    # Check engine
    sf: StockfishPool = app.state.sf_pool
    engine_name = sf.engine_name if sf.available else "unavailable"

    # Check queue
    tm: TaskManager = app.state.task_manager
    queue_ok = tm._worker_task is not None and not tm._worker_task.done()

    status = "ok" if (db_ok and sf.available and queue_ok) else "degraded"
    return HealthResponse(status=status, db=db_ok, engine=engine_name, queue=queue_ok)


# Serve React SPA (static files)
static_dir = get_static_dir()
if static_dir.exists() and (static_dir / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    # Serve other static files (favicon, etc.) from root
    @app.get("/favicon.ico")
    async def favicon() -> FileResponse:
        return FileResponse(static_dir / "favicon.ico")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """SPA fallback: serve index.html for all non-API routes."""
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(static_dir / "index.html")
