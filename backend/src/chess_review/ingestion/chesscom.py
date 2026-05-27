"""Chess.com public API client."""

import asyncio
import logging
from typing import Any, AsyncIterator

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
        await asyncio.sleep(0.25)  # Rate limiting
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

    async def stream_all_games(self, username: str) -> AsyncIterator[dict[str, Any]]:
        """Yield games newest-month-first as each monthly archive arrives.

        Compared to building one big list, streaming lets the consumer start
        ingesting + analyzing games as soon as the first archive returns
        (~0.5s) rather than waiting for the full walk (~0.25s * months).

        Order is "newest-month-first, within-archive newest-first" — not
        strictly globally newest-first (a late-March game can show up after
        an early-April game), but the boundary case is rare and not worth
        materializing the whole list to fix.
        """
        archives = list(reversed(await self.get_archives(username)))
        logger.info("Found %d archives for %s (newest first)", len(archives), username)
        for i, url in enumerate(archives):
            games = await self.get_monthly_games(url)
            logger.info("Archive %d/%d: %d games", i + 1, len(archives), len(games))
            # chess.com returns each month oldest-first; reverse so within a
            # month the most recent game is yielded first.
            for game in reversed(games):
                yield game
