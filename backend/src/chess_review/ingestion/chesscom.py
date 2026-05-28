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

