"""Game endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chess_review.db import get_session
from chess_review.models import Game, GameMove

router = APIRouter(tags=["games"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/players/{player_id}/games")
async def list_games(
    player_id: uuid.UUID,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    time_class: str | None = None,
    user_color: str | None = None,
    user_result: str | None = None,
    opening_name: str | None = None,
    opening_search: str | None = Query(
        None,
        description="Case-insensitive substring match against opening_name.",
    ),
    eco: str | None = None,
    opp_rating_min: int | None = None,
    opp_rating_max: int | None = None,
    user_rating_min: int | None = None,
    user_rating_max: int | None = None,
    played_from: str | None = Query(
        None,
        description="ISO timestamp. Only include games with played_at >= this.",
    ),
    played_to: str | None = Query(
        None,
        description="ISO timestamp. Only include games with played_at <= this.",
    ),
    analyzed: bool | None = Query(
        None,
        description="If true, only return analyzed games. If false, only unanalyzed.",
    ),
    sort: str = Query(
        "played_at",
        pattern="^(played_at|opp_rating|user_rating|ply_count)$",
    ),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    filters: list = [Game.player_id == player_id]

    if time_class:
        filters.append(Game.time_class == time_class)
    if user_color:
        filters.append(Game.user_color == user_color)
    if user_result:
        filters.append(Game.user_result == user_result)
    if opening_name:
        filters.append(Game.opening_name == opening_name)
    if opening_search:
        filters.append(Game.opening_name.ilike(f"%{opening_search}%"))
    if eco:
        filters.append(Game.eco == eco)
    if analyzed is True:
        filters.append(Game.analyzed_at.isnot(None))
    elif analyzed is False:
        filters.append(Game.analyzed_at.is_(None))

    if opp_rating_min is not None or opp_rating_max is not None:
        lo = opp_rating_min if opp_rating_min is not None else 0
        hi = opp_rating_max if opp_rating_max is not None else 9999
        filters.append(
            or_(
                and_(
                    Game.user_color == "white",
                    Game.black_rating.isnot(None),
                    Game.black_rating >= lo,
                    Game.black_rating < hi,
                ),
                and_(
                    Game.user_color == "black",
                    Game.white_rating.isnot(None),
                    Game.white_rating >= lo,
                    Game.white_rating < hi,
                ),
            )
        )
    if user_rating_min is not None or user_rating_max is not None:
        lo = user_rating_min if user_rating_min is not None else 0
        hi = user_rating_max if user_rating_max is not None else 9999
        filters.append(
            or_(
                and_(
                    Game.user_color == "white",
                    Game.white_rating.isnot(None),
                    Game.white_rating >= lo,
                    Game.white_rating < hi,
                ),
                and_(
                    Game.user_color == "black",
                    Game.black_rating.isnot(None),
                    Game.black_rating >= lo,
                    Game.black_rating < hi,
                ),
            )
        )

    pf = _parse_dt(played_from)
    pt = _parse_dt(played_to)
    if pf is not None:
        filters.append(Game.played_at >= pf)
    if pt is not None:
        filters.append(Game.played_at <= pt)

    stmt = select(Game).where(and_(*filters))
    count_stmt = select(func.count()).select_from(Game).where(and_(*filters))

    if sort == "opp_rating":
        # Opponent rating depends on user_color — pick whichever isn't yours.
        sort_col = func.coalesce(
            case(
                (Game.user_color == "white", Game.black_rating),
                else_=Game.white_rating,
            ),
            0,
        )
    elif sort == "user_rating":
        sort_col = func.coalesce(
            case(
                (Game.user_color == "white", Game.white_rating),
                else_=Game.black_rating,
            ),
            0,
        )
    elif sort == "ply_count":
        sort_col = Game.ply_count
    else:
        sort_col = Game.played_at

    sort_expr = sort_col.desc() if order == "desc" else sort_col.asc()
    # Tie-break by played_at desc so pagination is stable when the primary sort
    # column has duplicates.
    if sort != "played_at":
        stmt = stmt.order_by(sort_expr, Game.played_at.desc())
    else:
        stmt = stmt.order_by(sort_expr)

    total = (await session.execute(count_stmt)).scalar() or 0
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    games = result.scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "games": [
            {
                "id": str(g.id),
                "white_username": g.white_username,
                "black_username": g.black_username,
                "white_rating": g.white_rating,
                "black_rating": g.black_rating,
                "user_color": g.user_color,
                "result": g.result,
                "user_result": g.user_result,
                "time_control": g.time_control,
                "time_class": g.time_class,
                "eco": g.eco,
                "opening_name": g.opening_name,
                "played_at": g.played_at.isoformat(),
                "ply_count": g.ply_count,
                "analyzed_at": g.analyzed_at.isoformat() if g.analyzed_at else None,
            }
            for g in games
        ],
    }


@router.get("/games/{game_id}")
async def get_game(
    game_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    stmt = (
        select(Game)
        .where(Game.id == game_id)
        .options(
            selectinload(Game.moves).selectinload(GameMove.position_before),
            selectinload(Game.moves).selectinload(GameMove.position_after),
        )
    )
    result = await session.execute(stmt)
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    moves_out = []
    for m in game.moves:
        moves_out.append({
            "ply": m.ply,
            "san": m.san,
            "uci": m.uci,
            "fen_before": m.position_before.fen_key if m.position_before else None,
            "fen_after": m.position_after.fen_key if m.position_after else None,
            "clock_remaining_ms": m.clock_remaining_ms,
            "eval_before_cp": m.eval_before_cp,
            "eval_after_cp": m.eval_after_cp,
            "cp_loss": m.cp_loss,
            "classification": m.classification,
            "phase": m.phase,
            "is_user_move": m.is_user_move,
        })

    return {
        "id": str(game.id),
        "white_username": game.white_username,
        "black_username": game.black_username,
        "white_rating": game.white_rating,
        "black_rating": game.black_rating,
        "user_color": game.user_color,
        "result": game.result,
        "user_result": game.user_result,
        "time_control": game.time_control,
        "time_class": game.time_class,
        "eco": game.eco,
        "opening_name": game.opening_name,
        "played_at": game.played_at.isoformat(),
        "ply_count": game.ply_count,
        "pgn": game.pgn,
        "moves": moves_out,
    }
