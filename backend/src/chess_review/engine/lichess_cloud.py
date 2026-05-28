"""Lichess cloud eval API client."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class LichessCloudClient:
    """Query Lichess cloud eval cache before invoking local Stockfish.

    Bounded-concurrency wrapper around the cloud-eval endpoint. The previous
    incarnation fired one request per uncached position with no concurrency
    cap and a 1.5s timeout — for a 10-game-parallel import that meant
    hundreds of in-flight requests against Lichess, which they (rightly)
    rate-limited, every timeout got counted as a "miss", and the
    5-consecutive-miss kill switch disabled the client for the whole job.
    Result: 0 cloud hits.

    Fixes:
      * Concurrency limited to ``_MAX_CONCURRENT`` simultaneous requests.
      * Timeout raised to 5s.
      * Only HTTP 404 (genuine cache-miss from Lichess) and stale-depth
        responses count toward the miss budget. Network errors / timeouts
        don't — they're not signal about coverage.
      * Miss budget raised to 20 so a stretch of novel middlegame positions
        doesn't kill the rest of the import.
    """

    _MAX_CONCURRENT = 3
    _MISS_LIMIT = 20

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=5.0,
            headers={"Accept": "application/json", "User-Agent": "chess-review/0.1"},
        )
        self._sem = asyncio.Semaphore(self._MAX_CONCURRENT)
        self._consecutive_misses = 0
        self._hits = 0
        self._misses = 0

    async def close(self) -> None:
        await self._client.aclose()

    async def get_eval(
        self, fen: str, min_depth: int = 14
    ) -> dict[str, object] | None:
        """Fetch cloud eval for a FEN. Returns None if not cached."""
        if self._consecutive_misses >= self._MISS_LIMIT:
            return None

        async with self._sem:
            try:
                resp = await self._client.get(
                    "https://lichess.org/api/cloud-eval",
                    params={"fen": fen, "multiPv": 1},
                )
            except Exception:
                # Network error / timeout — no signal about coverage; don't
                # count toward the disable budget.
                return None

            if resp.status_code == 404:
                self._consecutive_misses += 1
                self._misses += 1
                return None
            try:
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                return None

            if data.get("depth", 0) < min_depth:
                self._consecutive_misses += 1
                self._misses += 1
                return None
            pvs = data.get("pvs", [])
            if not pvs:
                return None
            pv = pvs[0]
            self._consecutive_misses = 0
            self._hits += 1
            return {
                "depth": data["depth"],
                "eval_cp": pv.get("cp"),
                "eval_mate": pv.get("mate"),
                "pv": pv.get("moves", ""),
                "nodes": data.get("knodes", 0) * 1000,
            }
