"""Performance by opponent rating bucket."""

import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.models import Game, GameMove

RATING_BUCKETS = [
    ("<800", 0, 800),
    ("800-1000", 800, 1000),
    ("1000-1200", 1000, 1200),
    ("1200-1400", 1200, 1400),
    ("1400-1600", 1400, 1600),
    ("1600-1800", 1600, 1800),
    ("1800-2000", 1800, 2000),
    ("2000+", 2000, 9999),
]


async def get_rating_performance(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None = None,
) -> list[dict]:
    """Win rate and accuracy bucketed by opponent rating."""
    results = []

    clamped_cpl = case(
        (GameMove.cp_loss > 1000, 1000),
        else_=GameMove.cp_loss,
    )

    for label, low, high in RATING_BUCKETS:
        opp_rating_filter = (
            (Game.user_color == "white") & (Game.black_rating >= low) & (Game.black_rating < high)
        ) | (
            (Game.user_color == "black") & (Game.white_rating >= low) & (Game.white_rating < high)
        )

        base_filters = [
            Game.player_id == player_id,
            Game.analyzed_at.isnot(None),
            opp_rating_filter,
        ]
        if since is not None:
            base_filters.append(Game.played_at >= since)

        row = (await session.execute(
            select(
                func.count().label("n"),
                func.sum(case((Game.user_result == "win", 1), else_=0)).label("wins"),
                func.sum(case((Game.user_result == "draw", 1), else_=0)).label("draws"),
            )
            .where(and_(*base_filters))
        )).one()

        n = row.n or 0
        if n == 0:
            continue

        cpl_filters = base_filters + [
            GameMove.is_user_move.is_(True),
            GameMove.cp_loss.isnot(None),
        ]
        cpl = (await session.execute(
            select(func.avg(clamped_cpl))
            .join(Game, GameMove.game_id == Game.id)
            .where(and_(*cpl_filters))
        )).scalar()

        results.append({
            "bucket": label,
            "low": low,
            "high": high,
            "games": n,
            "wins": row.wins or 0,
            "draws": row.draws or 0,
            "losses": n - (row.wins or 0) - (row.draws or 0),
            "win_rate": round((row.wins or 0) / n, 3),
            "avg_cpl": round(float(cpl or 0), 1),
        })

    return results
