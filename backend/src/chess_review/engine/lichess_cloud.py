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
    # Consecutive timeouts / rate-limit (429) / server-error responses before
    # cloud is disabled for the rest of the job. Under a parallel import,
    # Lichess throttles us and every request times out on the 5s budget; the
    # shared MAX_CONCURRENT gate then becomes a pipeline-wide bottleneck that
    # starves the Stockfish pool (engines sit idle waiting for prefetch to
    # return). Timeouts are NOT coverage signal, so they never tripped the
    # miss budget — meaning the client stayed enabled and throttled forever.
    # This separate budget bails out fast once throttling is evident.
    _FAIL_LIMIT = 5

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=5.0,
            headers={"Accept": "application/json", "User-Agent": "chess-review/0.1"},
        )
        self._sem = asyncio.Semaphore(self._MAX_CONCURRENT)
        self._consecutive_misses = 0
        self._consecutive_failures = 0
        self._disabled = False
        self._hits = 0
        self._misses = 0

    async def close(self) -> None:
        await self._client.aclose()

    def _note_failure(self) -> None:
        """Record a timeout / rate-limit / server error. Disable the client
        for the rest of the job once they pile up — continuing to wait on the
        3-wide, 5s-timeout gate would starve the engine pipeline."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._FAIL_LIMIT and not self._disabled:
            self._disabled = True
            logger.info(
                "Lichess cloud disabled for this job after %d consecutive "
                "timeouts/rate-limits — falling straight through to Stockfish "
                "so concurrent games don't stall on cloud lookups.",
                self._consecutive_failures,
            )

    async def get_eval(
        self, fen: str, min_depth: int = 14
    ) -> dict[str, object] | None:
        """Fetch cloud eval for a FEN. Returns None if not cached."""
        if self._disabled or self._consecutive_misses >= self._MISS_LIMIT:
            return None

        async with self._sem:
            try:
                resp = await self._client.get(
                    "https://lichess.org/api/cloud-eval",
                    params={"fen": fen, "multiPv": 1},
                )
            except Exception:
                # Timeout / network error. Under concurrent load this is almost
                # always Lichess throttling us — count it toward the bail-out
                # budget so cloud stops gating the pipeline.
                self._note_failure()
                return None

            # Reached Lichess but it's refusing us (rate limit) or broken —
            # same bail-out signal as a timeout.
            if resp.status_code == 429 or resp.status_code >= 500:
                self._note_failure()
                return None

            # Got a genuine answer (hit or real miss) — the connection is
            # healthy, so reset the failure streak.
            self._consecutive_failures = 0

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
