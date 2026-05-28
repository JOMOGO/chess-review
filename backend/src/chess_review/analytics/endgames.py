"""Endgame conversion analytics."""

import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.models import EndgameReach, Game


async def get_endgame_summary(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None = None,
    min_reached: int = 2,
) -> list[dict]:
    """Per-bucket counts: reached vs. converted.

    Buckets with fewer than ``min_reached`` occurrences are excluded — a 1/1
    "100% conversion" of some exotic material balance is noise, not a
    statistic. The frontend can pass ``min_reached=1`` to override.
    """
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
    ]
    if since:
        filters.append(Game.played_at >= since)

    stmt = (
        select(
            EndgameReach.bucket,
            func.count().label("reached"),
            func.sum(case((EndgameReach.converted.is_(True), 1), else_=0)).label("converted"),
            func.avg(EndgameReach.user_cp_at_entry).label("avg_cp_at_entry"),
        )
        .join(Game, Game.id == EndgameReach.game_id)
        .where(and_(*filters))
        .group_by(EndgameReach.bucket)
        .having(func.count() >= min_reached)
        .order_by(func.count().desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "bucket": row.bucket,
            "reached": int(row.reached),
            "converted": int(row.converted or 0),
            "conversion_rate": (
                round((row.converted or 0) / row.reached, 4) if row.reached else 0.0
            ),
            "avg_cp_at_entry": int(row.avg_cp_at_entry or 0),
        }
        for row in rows
    ]


async def get_endgame_examples(
    session: AsyncSession,
    player_id: uuid.UUID,
    bucket: str,
    limit: int = 20,
    since: datetime | None = None,
) -> list[dict]:
    """Recent games for one bucket. Drilldown / "show me the games I blew"."""
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
        EndgameReach.bucket == bucket,
    ]
    if since:
        filters.append(Game.played_at >= since)

    stmt = (
        select(
            EndgameReach.id,
            EndgameReach.entry_ply,
            EndgameReach.user_cp_at_entry,
            EndgameReach.converted,
            Game.id.label("game_id"),
            Game.opening_name,
            Game.user_result,
            Game.user_color,
            Game.time_class,
            Game.played_at,
        )
        .join(Game, Game.id == EndgameReach.game_id)
        .where(and_(*filters))
        .order_by(Game.played_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "reach_id": str(row.id),
            "game_id": str(row.game_id),
            "entry_ply": row.entry_ply,
            "user_cp_at_entry": row.user_cp_at_entry,
            "converted": bool(row.converted),
            "opening_name": row.opening_name,
            "user_result": row.user_result,
            "user_color": row.user_color,
            "time_class": row.time_class,
            "played_at": row.played_at,
        }
        for row in rows
    ]
