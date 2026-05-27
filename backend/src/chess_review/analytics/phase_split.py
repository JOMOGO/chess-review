"""Phase performance analysis: CPL breakdown by opening/middlegame/endgame."""

import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.models import Game, GameMove


async def get_phase_performance(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None = None,
) -> list[dict]:
    """Compute average CPL and error rates per game phase for user moves."""
    filters = [
        GameMove.is_user_move.is_(True),
        GameMove.classification.isnot(None),
        GameMove.phase.isnot(None),
        GameMove.cp_loss.isnot(None),
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
    ]
    if since:
        filters.append(Game.played_at >= since)

    clamped_cpl = case(
        (GameMove.cp_loss > 1000, 1000),
        else_=GameMove.cp_loss,
    )
    stmt = (
        select(
            GameMove.phase,
            func.count().label("sample_size"),
            func.avg(clamped_cpl).label("avg_cpl"),
            # Misses (gave up a winning position) count as blunders here —
            # they're the same severity to a stats-aggregate consumer.
            func.sum(case(
                (GameMove.classification.in_(("blunder", "miss")), 1), else_=0
            )).label("blunders"),
            func.sum(case(
                (GameMove.classification == "mistake", 1), else_=0
            )).label("mistakes"),
            func.sum(case(
                (GameMove.classification == "inaccuracy", 1), else_=0
            )).label("inaccuracies"),
        )
        .join(Game, GameMove.game_id == Game.id)
        .where(and_(*filters))
        .group_by(GameMove.phase)
    )

    rows = (await session.execute(stmt)).all()

    results = []
    for row in rows:
        n = row.sample_size or 1
        results.append({
            "phase": row.phase,
            "color": None,
            "sample_size": row.sample_size,
            "avg_cpl": round(float(row.avg_cpl or 0), 1),
            "blunder_rate": round((row.blunders or 0) / n, 4),
            "mistake_rate": round((row.mistakes or 0) / n, 4),
            "inaccuracy_rate": round((row.inaccuracies or 0) / n, 4),
        })

    phase_order = {"opening": 0, "middlegame": 1, "endgame": 2}
    results.sort(key=lambda r: phase_order.get(r["phase"], 99))
    return results
