"""Time pressure curve: CPL bucketed by clock remaining."""

import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.models import Game, GameMove

BUCKETS = [
    (">120s", 120_000, None),
    ("60-120s", 60_000, 120_000),
    ("30-60s", 30_000, 60_000),
    ("10-30s", 10_000, 30_000),
    ("<10s", 0, 10_000),
]


async def get_time_pressure(
    session: AsyncSession,
    player_id: uuid.UUID,
    time_class: str = "blitz",
    since: datetime | None = None,
) -> list[dict]:
    """Compute CPL per time-remaining bucket for user moves."""
    results = []

    clamped_cpl = case(
        (GameMove.cp_loss > 1000, 1000),
        else_=GameMove.cp_loss,
    )

    for label, low, high in BUCKETS:
        filters = [
            GameMove.is_user_move.is_(True),
            GameMove.cp_loss.isnot(None),
            GameMove.clock_remaining_ms.isnot(None),
            GameMove.classification.isnot(None),
            Game.player_id == player_id,
            Game.analyzed_at.isnot(None),
            Game.time_class == time_class,
            GameMove.clock_remaining_ms >= low,
        ]
        if high is not None:
            filters.append(GameMove.clock_remaining_ms < high)
        if since is not None:
            filters.append(Game.played_at >= since)

        stmt = (
            select(
                func.count().label("n"),
                func.avg(clamped_cpl).label("avg_cpl"),
                func.sum(
                    case(
                        # Misses count as blunders for time-pressure stats.
                        (GameMove.classification.in_(("blunder", "miss")), 1),
                        else_=0,
                    )
                ).label("blunders"),
            )
            .join(Game, GameMove.game_id == Game.id)
            .where(and_(*filters))
        )

        row = (await session.execute(stmt)).one()
        n = row.n or 0
        if n == 0:
            continue

        results.append({
            "bucket": label,
            "sample_size": n,
            "avg_cpl": round(float(row.avg_cpl or 0), 1),
            "blunder_rate": round((row.blunders or 0) / n, 4),
        })

    return results
