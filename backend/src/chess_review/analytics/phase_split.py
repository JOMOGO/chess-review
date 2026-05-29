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
    """Compute average CPL and error rates per game phase.

    Returns one row per phase with both user and opponent stats. The
    user-vs-opponent CPL delta is the actionable signal: an absolute CPL of
    30 means very different things depending on whether your opponents
    average 15 (you're being outplayed there) or 50 (that phase is fine for
    your rating tier).
    """
    filters = [
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
    user_cpl = case((GameMove.is_user_move.is_(True), clamped_cpl), else_=None)
    opp_cpl = case((GameMove.is_user_move.is_(False), clamped_cpl), else_=None)

    stmt = (
        select(
            GameMove.phase,
            # User stats. Misses (gave up a winning position) count as
            # blunders here — same severity to a stats-aggregate consumer.
            func.sum(case((GameMove.is_user_move.is_(True), 1), else_=0)).label("sample_size"),
            func.avg(user_cpl).label("avg_cpl"),
            func.sum(case(
                (and_(
                    GameMove.is_user_move.is_(True),
                    GameMove.classification.in_(("blunder", "miss")),
                ), 1),
                else_=0,
            )).label("blunders"),
            func.sum(case(
                (and_(
                    GameMove.is_user_move.is_(True),
                    GameMove.classification == "mistake",
                ), 1),
                else_=0,
            )).label("mistakes"),
            func.sum(case(
                (and_(
                    GameMove.is_user_move.is_(True),
                    GameMove.classification == "inaccuracy",
                ), 1),
                else_=0,
            )).label("inaccuracies"),
            # Opponent stats — only avg CPL and sample size are surfaced.
            # Their blunder rate isn't actionable for the user.
            func.sum(case((GameMove.is_user_move.is_(False), 1), else_=0)).label("opp_sample_size"),
            func.avg(opp_cpl).label("opp_avg_cpl"),
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
            "opponent_sample_size": row.opp_sample_size or 0,
            "opponent_avg_cpl": round(float(row.opp_avg_cpl or 0), 1),
        })

    phase_order = {"opening": 0, "middlegame": 1, "endgame": 2}
    results.sort(key=lambda r: phase_order.get(r["phase"], 99))
    return results


async def get_phase_examples(
    session: AsyncSession,
    player_id: uuid.UUID,
    phase: str,
    limit: int = 20,
    since: datetime | None = None,
) -> list[dict]:
    """Worst user moves in a phase, sorted by cp_loss desc — drill-down list.

    Only inaccuracies and worse are returned (the "good" / "best" tail is
    huge and useless for a what-to-study-next view).
    """
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
        GameMove.is_user_move.is_(True),
        GameMove.phase == phase,
        GameMove.cp_loss.isnot(None),
        GameMove.classification.in_(("inaccuracy", "mistake", "blunder", "miss")),
    ]
    if since:
        filters.append(Game.played_at >= since)

    stmt = (
        select(
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
        .join(Game, Game.id == GameMove.game_id)
        .where(and_(*filters))
        .order_by(GameMove.cp_loss.desc())
        .limit(limit)
    )

    rows = (await session.execute(stmt)).all()
    return [
        {
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
