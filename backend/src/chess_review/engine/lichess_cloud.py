"""Lichess cloud eval API client."""

import logging

import httpx

logger = logging.getLogger(__name__)


class LichessCloudClient:
    """Query Lichess cloud eval cache before invoking local Stockfish.

    Only queries for early-game positions (first ~15 moves) since
    Lichess cloud cache coverage drops sharply after the opening.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=1.5,
            headers={"Accept": "application/json", "User-Agent": "chess-review/0.1"},
        )
        self._consecutive_misses = 0
        self._hits = 0
        self._misses = 0

    async def close(self) -> None:
        await self._client.aclose()

    async def get_eval(
        self, fen: str, min_depth: int = 14
    ) -> dict[str, object] | None:
        """Fetch cloud eval for a FEN. Returns None if not cached."""
        # Disable after 5 consecutive misses — cloud probably won't help
        if self._consecutive_misses >= 5:
            return None

        try:
            resp = await self._client.get(
                "https://lichess.org/api/cloud-eval",
                params={"fen": fen, "multiPv": 1},
            )
            if resp.status_code == 404:
                self._consecutive_misses += 1
                self._misses += 1
                return None
            resp.raise_for_status()
            data = resp.json()
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
        except Exception:
            self._consecutive_misses += 1
            self._misses += 1
            return None
