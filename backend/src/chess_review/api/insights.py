"""Insight endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.analytics.accuracy import get_accuracy_trend
from chess_review.analytics.endgames import get_endgame_examples, get_endgame_summary
from chess_review.analytics.motifs import get_motif_examples, get_motif_summary
from chess_review.analytics.opening_tree import build_opening_tree
from chess_review.analytics.openings_winrate import get_opening_stats
from chess_review.analytics.phase_split import get_phase_examples, get_phase_performance
from chess_review.analytics.rating_performance import get_rating_performance
from chess_review.analytics.recommendations import get_recommendations
from chess_review.analytics.time_pressure import get_time_pressure
from chess_review.db import get_session

router = APIRouter(prefix="/players/{player_id}/insights", tags=["insights"])


# Range tokens supported by every analytics endpoint. ``all`` means no filter.
_RANGE_TO_DAYS = {
    "day": 1,
    "week": 7,
    "month": 30,
    "year": 365,
}


def _resolve_since(range_: str | None, since: str | None) -> datetime | None:
    """Pick the effective ``played_at >= X`` cutoff.

    ``range`` is the dropdown token (day/week/month/year/all). ``since`` is an
    explicit ISO-8601 timestamp override (kept for backwards compatibility).
    """
    if since:
        try:
            return datetime.fromisoformat(since)
        except ValueError:
            pass
    if range_ and range_ != "all":
        days = _RANGE_TO_DAYS.get(range_)
        if days is not None:
            return datetime.now(timezone.utc) - timedelta(days=days)
    return None


@router.get("/opening-tree")
async def opening_tree(
    player_id: uuid.UUID,
    min_visits: int = 5,
    max_ply: int = 24,
    range: str | None = None,
    color: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    nodes = await build_opening_tree(
        session, player_id, max_ply, min_visits,
        since=_resolve_since(range, None),
        color=color,
    )
    return {"nodes": nodes}


@router.get("/phase-performance")
async def phase_performance(
    player_id: uuid.UUID,
    since: str | None = None,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_phase_performance(
        session, player_id, _resolve_since(range, since),
    )


@router.get("/phase-performance/{phase}")
async def phase_examples(
    player_id: uuid.UUID,
    phase: str,
    limit: int = 20,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_phase_examples(
        session, player_id, phase, limit=limit,
        since=_resolve_since(range, None),
    )


@router.get("/time-pressure")
async def time_pressure(
    player_id: uuid.UUID,
    time_class: str = "blitz",
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_time_pressure(
        session, player_id, time_class,
        since=_resolve_since(range, None),
    )


@router.get("/accuracy-trend")
async def accuracy_trend(
    player_id: uuid.UUID,
    time_class: str | None = None,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_accuracy_trend(
        session, player_id, time_class,
        since=_resolve_since(range, None),
    )


@router.get("/opening-stats")
async def opening_stats(
    player_id: uuid.UUID,
    min_games: int = 3,
    color: str | None = None,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_opening_stats(
        session, player_id, min_games, color,
        since=_resolve_since(range, None),
    )


@router.get("/rating-performance")
async def rating_performance(
    player_id: uuid.UUID,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_rating_performance(
        session, player_id,
        since=_resolve_since(range, None),
    )


@router.get("/recommendations")
async def recommendations(
    player_id: uuid.UUID,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return await get_recommendations(
        session, player_id,
        since=_resolve_since(range, None),
    )


@router.get("/motifs")
async def motifs(
    player_id: uuid.UUID,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_motif_summary(
        session, player_id,
        since=_resolve_since(range, None),
    )


@router.get("/motifs/{motif}")
async def motif_examples(
    player_id: uuid.UUID,
    motif: str,
    limit: int = 20,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_motif_examples(
        session, player_id, motif, limit=limit,
        since=_resolve_since(range, None),
    )


@router.get("/endgames")
async def endgames(
    player_id: uuid.UUID,
    min_reached: int = 2,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_endgame_summary(
        session, player_id, since=_resolve_since(range, None),
        min_reached=min_reached,
    )


@router.get("/endgames/{bucket}")
async def endgame_examples(
    player_id: uuid.UUID,
    bucket: str,
    limit: int = 20,
    range: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_endgame_examples(
        session, player_id, bucket, limit=limit,
        since=_resolve_since(range, None),
    )
