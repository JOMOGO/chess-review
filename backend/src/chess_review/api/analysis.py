"""Analysis endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.db import get_session
from chess_review.models import Position, PositionEval

router = APIRouter(tags=["analysis"])


@router.get("/positions/{fen_key:path}/eval")
async def get_position_eval(
    fen_key: str,
    depth_min: int = 18,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    stmt = select(Position).where(Position.fen_key == fen_key)
    result = await session.execute(stmt)
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    eval_stmt = (
        select(PositionEval)
        .where(PositionEval.position_id == pos.id, PositionEval.depth >= depth_min)
        .order_by(PositionEval.depth.desc())
        .limit(1)
    )
    eval_result = await session.execute(eval_stmt)
    ev = eval_result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="No eval at requested depth")

    return {
        "fen_key": fen_key,
        "engine": ev.engine,
        "depth": ev.depth,
        "eval_cp": ev.eval_cp,
        "eval_mate": ev.eval_mate,
        "best_move_uci": ev.best_move_uci,
        "pv": ev.pv,
    }
