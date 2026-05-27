"""Player endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.db import get_session
from chess_review.models import ImportJob, Player
from chess_review.schemas import CreatePlayerRequest, ImportStatusResponse, PlayerOut
from chess_review.taskqueue.tasks import import_player_games

router = APIRouter(prefix="/players", tags=["players"])


@router.post("", response_model=PlayerOut)
async def create_player(
    body: CreatePlayerRequest,
    session: AsyncSession = Depends(get_session),
) -> Player:
    lower = body.username.lower()
    stmt = select(Player).where(
        Player.provider == body.provider, Player.username_lower == lower
    )
    result = await session.execute(stmt)
    player = result.scalar_one_or_none()
    if player:
        return player
    player = Player(
        provider=body.provider,
        username=body.username,
        username_lower=lower,
    )
    session.add(player)
    await session.commit()
    await session.refresh(player)
    return player


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(
    player_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Player:
    stmt = select(Player).where(Player.id == player_id)
    result = await session.execute(stmt)
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@router.post("/{player_id}/import")
async def start_import(
    player_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    stmt = select(Player).where(Player.id == player_id)
    result = await session.execute(stmt)
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    job = ImportJob(player_id=player.id, status="pending")
    session.add(job)
    await session.commit()
    await session.refresh(job)

    tm = request.app.state.task_manager
    await tm.enqueue(import_player_games, str(player.id), job_id=str(job.id), sf_pool=request.app.state.sf_pool)
    return {"job_id": str(job.id)}


@router.get("/{player_id}/import/status", response_model=ImportStatusResponse | None)
async def import_status(
    player_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ImportJob | None:
    stmt = (
        select(ImportJob)
        .where(ImportJob.player_id == player_id)
        .order_by(ImportJob.started_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
