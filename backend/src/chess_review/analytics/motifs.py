"""Motif analytics: per-player aggregation of detected tactical motifs."""

import uuid
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.models import Game, GameMove, MoveTactic


async def get_motif_summary(
    session: AsyncSession,
    player_id: uuid.UUID,
    since: datetime | None = None,
) -> list[dict]:
    """Aggregate missed motifs across the player's analyzed games.

    Returns one row per motif: count, distinct game count, and the worst
    classification it landed under (so the UI can show "you've missed 12
    forks, 4 of which dropped the game").
    """
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
        GameMove.is_user_move.is_(True),
    ]
    if since:
        filters.append(Game.played_at >= since)

    stmt = (
        select(
            MoveTactic.motif,
            func.count().label("count"),
            func.count(func.distinct(GameMove.game_id)).label("games"),
            func.sum(case(
                (GameMove.classification.in_(("blunder", "miss")), 1), else_=0
            )).label("blunders"),
            func.sum(case(
                (GameMove.classification == "mistake", 1), else_=0
            )).label("mistakes"),
        )
        .join(GameMove, GameMove.id == MoveTactic.game_move_id)
        .join(Game, Game.id == GameMove.game_id)
        .where(and_(*filters))
        .group_by(MoveTactic.motif)
        .order_by(func.count().desc())
    )

    rows = (await session.execute(stmt)).all()
    return [
        {
            "motif": row.motif,
            "count": int(row.count),
            "games": int(row.games),
            "blunders": int(row.blunders or 0),
            "mistakes": int(row.mistakes or 0),
        }
        for row in rows
    ]


async def get_motif_examples(
    session: AsyncSession,
    player_id: uuid.UUID,
    motif: str,
    limit: int = 20,
    since: datetime | None = None,
) -> list[dict]:
    """Recent examples of a single motif — for the drilldown view.

    Returns most-recent first. Each row is enough to deep-link the user to
    the move in the per-game review.
    """
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
        GameMove.is_user_move.is_(True),
        MoveTactic.motif == motif,
    ]
    if since:
        filters.append(Game.played_at >= since)

    stmt = (
        select(
            MoveTactic.id,
            Game.id.label("game_id"),
            GameMove.id.label("move_id"),
            GameMove.ply,
            GameMove.san,
            GameMove.classification,
            GameMove.cp_loss,
            Game.opening_name,
            Game.user_result,
            Game.played_at,
        )
        .join(GameMove, GameMove.id == MoveTactic.game_move_id)
        .join(Game, Game.id == GameMove.game_id)
        .where(and_(*filters))
        .order_by(Game.played_at.desc())
        .limit(limit)
    )

    rows = (await session.execute(stmt)).all()
    return [
        {
            "tactic_id": str(row.id),
            "game_id": str(row.game_id),
            "move_id": str(row.move_id),
            "ply": row.ply,
            "san": row.san,
            "classification": row.classification,
            "cp_loss": row.cp_loss,
            "opening_name": row.opening_name,
            "user_result": row.user_result,
            "played_at": row.played_at,
        }
        for row in rows
    ]
