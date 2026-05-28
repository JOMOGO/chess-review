"""Chess.com public API client."""

import asyncio
import logging
from typing import Any

import httpx

from chess_review.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.chess.com/pub"


class ChessComClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": settings.chesscom_user_agent},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_archives(self, username: str) -> list[str]:
        """List monthly archive URLs for a player."""
        resp = await self._client.get(f"{BASE_URL}/player/{username}/games/archives")
        resp.raise_for_status()
        return resp.json()["archives"]

    async def get_monthly_games(self, archive_url: str) -> list[dict[str, Any]]:
        """Download one month's games from an archive URL."""
        try:
            resp = await self._client.get(archive_url)
            if resp.status_code == 429:
                logger.warning("Rate limited, sleeping 5s")
                await asyncio.sleep(5)
                resp = await self._client.get(archive_url)
            resp.raise_for_status()
            return resp.json().get("games", [])
        except httpx.HTTPStatusError:
            logger.exception("Failed to fetch archive %s", archive_url)
            return []

    async def get_all_games(self, username: str) -> list[dict[str, Any]]:
        """Fetch every game newest-month-first, using bounded-parallel
        archive fetches so the full count is known before the importer
        starts processing.

        Trade-off vs. streaming: we wait for every archive before returning,
        but at concurrency 3 that's ~1/3 the sequential time and lets the
        importer set ``total_games`` exactly once. Progress UI shows a
        real ratio instead of a moving estimate.

        Order: newest-month-first; within a month, newest game first.
        Strict global newest-first across month boundaries is not
        preserved (a late-March game can show after an early-April one),
        which matches the previous streaming behaviour.
        """
        archives = list(reversed(await self.get_archives(username)))
        if not archives:
            return []
        logger.info("Found %d archives for %s (newest first)", len(archives), username)

        sem = asyncio.Semaphore(3)

        async def _fetch(idx: int, url: str) -> tuple[int, list[dict[str, Any]]]:
            async with sem:
                games = await self.get_monthly_games(url)
                logger.info(
                    "Archive %d/%d: %d games", idx + 1, len(archives), len(games),
                )
                return idx, games

        results = await asyncio.gather(*[_fetch(i, u) for i, u in enumerate(archives)])
        results.sort(key=lambda r: r[0])
        return [g for _, archive in results for g in reversed(archive)]

