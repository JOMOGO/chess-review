"""Pool of Stockfish UCI engine instances."""

import asyncio
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import chess
import chess.engine

from chess_review.config import settings

_POPEN_FLAGS: dict[str, object] = {}
if sys.platform == "win32":
    _POPEN_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW

logger = logging.getLogger(__name__)


def _detect_total_ram_mb() -> int | None:
    """Return total physical RAM in MB, or None if undetectable. Stdlib-only."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemStatus()
            stat.dwLength = ctypes.sizeof(_MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            return int(stat.ullTotalPhys // (1024 * 1024))
        # POSIX (Linux/Mac)
        pages = os.sysconf("SC_PHYS_PAGES")  # type: ignore[attr-defined]
        page_size = os.sysconf("SC_PAGE_SIZE")  # type: ignore[attr-defined]
        return int(pages * page_size // (1024 * 1024))
    except Exception:
        return None


def auto_hash_mb(pool_size: int) -> int:
    """Pick a per-engine Hash size in MB.

    Targets ~1/4 of total RAM for Stockfish in aggregate, split across the
    pool. Clamped to [256, 1024] per engine so we never starve the TT and
    never grab silly amounts on a workstation. Falls back to a RAM-agnostic
    formula if detection fails.
    """
    if pool_size < 1:
        pool_size = 1
    total_ram = _detect_total_ram_mb()
    if total_ram:
        per_engine = (total_ram // 4) // pool_size
    else:
        per_engine = 4096 // pool_size
    return max(256, min(1024, per_engine))


class StockfishPool:
    """Manages a pool of Stockfish engine processes."""

    def __init__(
        self,
        stockfish_path: str,
        pool_size: int = 2,
        hash_mb: int = 256,
        *,
        interactive_threads: int = 0,
        interactive_hash_mb: int = 0,
        interactive_busy_threads: int = 0,
    ):
        self._path = stockfish_path
        self._pool_size = pool_size
        self._hash_mb = hash_mb
        # Dedicated interactive engine config: many threads on ONE engine so a
        # single live-analysis search is as fast as possible (the opposite of
        # the pool's one-thread-per-engine, many-engines throughput config).
        # While an import runs we drop it to `busy_threads` so it coexists with
        # the import pool instead of oversubscribing every core.
        self._interactive_threads = interactive_threads if interactive_threads > 0 else (os.cpu_count() or 1)
        self._interactive_busy_threads = (
            interactive_busy_threads if interactive_busy_threads > 0
            else max(1, self._interactive_threads // 4)
        )
        self._interactive_hash_mb = interactive_hash_mb if interactive_hash_mb > 0 else hash_mb
        # Tracks the Threads value currently configured on the interactive
        # engine so we only send a setoption when it actually changes.
        self._interactive_threads_active = self._interactive_threads
        self._engines: list[chess.engine.UciProtocol] = []
        self._semaphore = asyncio.Semaphore(pool_size)
        self._available: asyncio.Queue[chess.engine.UciProtocol] = asyncio.Queue()
        self._interactive: chess.engine.UciProtocol | None = None
        self._interactive_lock = asyncio.Lock()
        self._started = False

    @property
    def available(self) -> bool:
        return self._started and len(self._engines) > 0

    @property
    def engine_name(self) -> str:
        if self._engines:
            return self._engines[0].id.get("name", "unknown")
        return "not started"

    async def start(self) -> None:
        if not Path(self._path).exists():
            logger.warning("Stockfish binary not found at %s", self._path)
            return

        for i in range(self._pool_size):
            engine = await self._spawn_one()
            if engine is not None:
                self._engines.append(engine)
                await self._available.put(engine)
                logger.info("Started Stockfish instance %d/%d", i + 1, self._pool_size)

        self._started = True
        if self._engines:
            logger.info(
                "StockfishPool ready: %d/%d engines (%s)",
                len(self._engines), self._pool_size, self.engine_name,
            )
            # Dedicated engine for interactive single-position analysis. Used
            # only by the live /api/analyze endpoint, which is itself blocked
            # while imports run — so this many-threaded engine never competes
            # with the pool for CPU.
            self._interactive = await self._spawn_one(
                threads=self._interactive_threads,
                hash_mb=self._interactive_hash_mb,
            )
            if self._interactive is not None:
                logger.info(
                    "Interactive engine ready (Threads=%d, Hash=%d MB)",
                    self._interactive_threads, self._interactive_hash_mb,
                )

    async def _spawn_one(
        self,
        *,
        threads: int | None = None,
        hash_mb: int | None = None,
    ) -> chess.engine.UciProtocol | None:
        """Open one Stockfish process and configure it. Returns ``None`` on
        failure so the caller can leave that slot empty. ``threads``/``hash_mb``
        override the pool defaults (used for the interactive engine).
        """
        try:
            _, engine = await chess.engine.popen_uci(self._path, **_POPEN_FLAGS)
            uci_options: dict[str, object] = {
                "Threads": settings.sf_threads if threads is None else threads,
                "Hash": self._hash_mb if hash_mb is None else hash_mb,
            }
            if settings.syzygy_path and Path(settings.syzygy_path).is_dir():
                uci_options["SyzygyPath"] = settings.syzygy_path
                uci_options["SyzygyProbeLimit"] = 7
            await engine.configure(uci_options)
            return engine
        except Exception:
            logger.exception("Failed to spawn Stockfish")
            return None

    @staticmethod
    def _engine_alive(engine: chess.engine.UciProtocol) -> bool:
        """True if the engine's subprocess is still running."""
        transport = getattr(engine, "transport", None)
        if transport is None:
            return False
        # asyncio transports expose is_closing(); also check returncode where
        # available for belt-and-braces.
        try:
            if transport.is_closing():
                return False
        except Exception:
            return False
        proc = getattr(transport, "_proc", None)
        if proc is not None and getattr(proc, "returncode", None) is not None:
            return False
        return True

    async def _replace_dead(self) -> None:
        """Spawn a fresh Stockfish to fill a slot a dead engine just vacated."""
        logger.warning("Replacing dead Stockfish engine")
        new_engine = await self._spawn_one()
        if new_engine is None:
            logger.error(
                "Could not respawn Stockfish; pool size effectively reduced"
            )
            # Don't release the semaphore — we have one fewer real engine now.
            # Better to run at reduced capacity than hand out a poison slot.
            return
        self._engines.append(new_engine)
        self._available.put_nowait(new_engine)
        self._semaphore.release()

    async def stop(self) -> None:
        for eng in self._engines:
            try:
                await eng.quit()
            except Exception:
                pass
        if self._interactive is not None:
            try:
                await self._interactive.quit()
            except Exception:
                pass
            self._interactive = None
        self._engines.clear()
        self._started = False
        logger.info("StockfishPool stopped")

    async def analyse(
        self,
        board: chess.Board,
        depth: int,
        *,
        game: object | None = None,
    ) -> chess.engine.InfoDict:
        """Analyse a position at the given depth. Blocks until an engine is free.

        The optional ``game`` token is passed straight through to
        ``python-chess``'s ``engine.analyse``. It only sends ``ucinewgame`` when
        the token changes between calls, so passing a stable per-game value
        keeps the transposition table warm across positions of the same game.
        """
        async with self._semaphore:
            engine = await self._available.get()
            try:
                info = await engine.analyse(
                    board,
                    chess.engine.Limit(depth=depth),
                    game=game,
                )
                return info
            finally:
                await self._available.put(engine)

    async def analyse_interactive(
        self,
        board: chess.Board,
        depth: int,
        multipv: int,
        *,
        reduced: bool = False,
    ) -> list[chess.engine.InfoDict]:
        """Analyse a single position on the dedicated many-threaded interactive
        engine, returning up to ``multipv`` ranked lines (best first).

        This engine is NOT part of the pool and does not touch the pool
        semaphore, so it never waits on import work for an engine slot. A lock
        serializes concurrent live requests (one engine can't run two searches
        at once), and the engine is respawned if it died.

        When ``reduced`` is set (an import/reanalysis is in flight) the engine
        is reconfigured to ``interactive_busy_threads`` so a live search shares
        the CPU with the import pool instead of oversubscribing every core; it
        snaps back to full threads once the import finishes. The reconfigure is
        skipped when the thread count is already correct.
        """
        async with self._interactive_lock:
            engine = self._interactive
            if engine is None or not self._engine_alive(engine):
                engine = await self._spawn_one(
                    threads=self._interactive_threads,
                    hash_mb=self._interactive_hash_mb,
                )
                self._interactive = engine
                self._interactive_threads_active = self._interactive_threads
            if engine is None:
                raise RuntimeError("Interactive Stockfish engine unavailable")
            want = self._interactive_busy_threads if reduced else self._interactive_threads
            if want != self._interactive_threads_active:
                await engine.configure({"Threads": want})
                self._interactive_threads_active = want
            info = await engine.analyse(
                board,
                chess.engine.Limit(depth=depth),
                multipv=multipv,
            )
            return list(info) if isinstance(info, list) else [info]

    @property
    def pool_size(self) -> int:
        return self._pool_size

    async def acquire(self) -> chess.engine.UciProtocol | None:
        """Reserve one engine for an extended series of analyses (e.g., a whole
        game). Caller MUST release the engine when done. Returns None if the
        pool isn't started or no engines are available.

        Pinning an engine for a game keeps Stockfish's transposition table warm
        across the game's positions — they overlap by all-but-one move each.
        """
        if not self._started or not self._engines:
            return None
        await self._semaphore.acquire()
        try:
            engine = await self._available.get()
        except BaseException:
            self._semaphore.release()
            raise
        return engine

    def release(self, engine: chess.engine.UciProtocol | None) -> None:
        """Return a previously-acquired engine to the pool, replacing it
        with a fresh process if it died.

        Stockfish can crash (OOM, weird position, internal bug); without
        this check the dead process would go back in the queue and every
        subsequent ``analyse`` call against it would raise
        ``EngineTerminatedError``, silently failing entire games. Detecting
        a dead transport here and respawning in the background means one
        crash kills exactly one game's analysis, not every game queued
        behind it on that engine.
        """
        if engine is None:
            return
        if not self._engine_alive(engine):
            try:
                self._engines.remove(engine)
            except ValueError:
                pass
            # Replacement is async (popen + configure); fire-and-forget so
            # the caller's release() returns immediately. Semaphore stays
            # decremented until the new engine is ready.
            asyncio.create_task(self._replace_dead())
            return
        self._available.put_nowait(engine)
        self._semaphore.release()

    @asynccontextmanager
    async def pinned(self) -> AsyncIterator[chess.engine.UciProtocol | None]:
        """Async context manager: acquire one engine, release on exit."""
        engine = await self.acquire()
        try:
            yield engine
        finally:
            self.release(engine)

    async def analyse_on(
        self,
        engine: chess.engine.UciProtocol,
        board: chess.Board,
        depth: int,
        *,
        game: object | None = None,
    ) -> chess.engine.InfoDict:
        """Analyse on a specific engine the caller has already acquired.

        Does NOT touch the semaphore or queue — the caller is responsible for
        having held the engine via :meth:`acquire`.
        """
        return await engine.analyse(
            board,
            chess.engine.Limit(depth=depth),
            game=game,
        )
