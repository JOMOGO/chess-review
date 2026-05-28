"""Win rate breakdown by opening."""

import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.models import Game, GameMove


async def get_opening_stats(
    session: AsyncSession,
    player_id: uuid.UUID,
    min_games: int = 3,
    color: str | None = None,
    since: datetime | None = None,
) -> list[dict]:
    """Win/draw/loss rate and average CPL per opening."""
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
        Game.opening_name.isnot(None),
        Game.opening_name != "",
        # Old imports stored chess.com's "Undefined" placeholder literally.
        # Excluding here covers existing DB rows; the ingestion path now
        # normalises this to NULL so new imports won't carry it.
        func.lower(Game.opening_name) != "undefined",
        func.lower(Game.opening_name) != "unknown",
    ]
    if color:
        filters.append(Game.user_color == color)
    if since is not None:
        filters.append(Game.played_at >= since)

    rows = (await session.execute(
        select(
            Game.eco,
            Game.opening_name,
            Game.user_color,
            func.count().label("games"),
            func.sum(case((Game.user_result == "win", 1), else_=0)).label("wins"),
            func.sum(case((Game.user_result == "draw", 1), else_=0)).label("draws"),
            func.sum(case((Game.user_result == "loss", 1), else_=0)).label("losses"),
            func.max(Game.played_at).label("last_played_at"),
        )
        .where(and_(*filters))
        .group_by(Game.eco, Game.opening_name, Game.user_color)
        .having(func.count() >= min_games)
        .order_by(func.count().desc())
    )).all()

    results = []
    for r in rows:
        n = r.games
        cpl_filters = [
            Game.player_id == player_id,
            Game.opening_name == r.opening_name,
            Game.user_color == r.user_color,
            GameMove.is_user_move.is_(True),
            GameMove.cp_loss.isnot(None),
        ]
        if since is not None:
            cpl_filters.append(Game.played_at >= since)
        clamped_cpl = case(
            (GameMove.cp_loss > 1000, 1000),
            else_=GameMove.cp_loss,
        )
        cpl_row = (await session.execute(
            select(func.avg(clamped_cpl))
            .join(Game, GameMove.game_id == Game.id)
            .where(and_(*cpl_filters))
        )).scalar()

        results.append({
            "eco": r.eco,
            # ECO codes are 1 letter + 2 digits (e.g. B20). The leading letter
            # groups openings into the five canonical families (A/B/C/D/E).
            "parent_eco": r.eco[0] if r.eco else None,
            "opening_name": r.opening_name,
            "color": r.user_color,
            "games": n,
            "wins": r.wins,
            "draws": r.draws,
            "losses": r.losses,
            "win_rate": round(r.wins / n, 3),
            # Chess-standard performance score: win=1, draw=0.5, loss=0.
            "score_rate": round((r.wins + 0.5 * r.draws) / n, 3),
            "avg_cpl": round(float(cpl_row or 0), 1),
            "last_played_at": r.last_played_at.isoformat() if r.last_played_at else None,
        })

    return results
