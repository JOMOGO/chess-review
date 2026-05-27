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

    async def get_all_games(self, username: str) -> list[dict[str, Any]]:
        """Fetch all games for a player, sorted newest first.

        Chess.com archives are monthly and return games oldest-first within
        each month, so we sort the merged list by ``end_time`` descending to
        get strict newest-first ordering. The import queue is FIFO so this
        order is preserved through analysis.
        """
        archives = await self.get_archives(username)
        # Walk archives newest-month-first so we can show progress in a
        # newest-first order even before the final sort.
        archives = list(reversed(archives))
        logger.info("Found %d archives for %s (newest first)", len(archives), username)
        all_games: list[dict[str, Any]] = []
        for i, url in enumerate(archives):
            games = await self.get_monthly_games(url)
            all_games.extend(games)
            logger.info(
                "Archive %d/%d: %d games (total: %d)",
                i + 1, len(archives), len(games), len(all_games),
            )
        all_games.sort(key=lambda g: g.get("end_time") or 0, reverse=True)
        return all_games
