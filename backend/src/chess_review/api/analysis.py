"""Analysis endpoints."""

import chess
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.db import get_session
from chess_review.engine.analysis_orchestrator import score_to_cp
from chess_review.engine.stockfish_pool import StockfishPool
from chess_review.models import Position, PositionEval
from chess_review.schemas import (
    AnalyzeLine,
    AnalyzePositionRequest,
    AnalyzePositionResponse,
)

router = APIRouter(tags=["analysis"])


@router.post("/analyze", response_model=AnalyzePositionResponse)
async def analyze_position(
    body: AnalyzePositionRequest,
    request: Request,
) -> AnalyzePositionResponse:
    """Live multi-PV Stockfish analysis of an arbitrary position.

    Powers the interactive board on the game review page: the user can drag
    pieces into any variation and see the engine's top moves for whichever
    side is to move. Unlike the precomputed per-game evals (served from the
    DB cache), this hits Stockfish directly via the shared pool, so it blocks
    until a pool engine is free.
    """
    sf: StockfishPool = request.app.state.sf_pool
    if not sf.available:
        raise HTTPException(status_code=503, detail="Engine not available")

    # While an import/reanalysis is running, the interactive engine runs on
    # reduced threads so it coexists with the throughput-optimized pool instead
    # of oversubscribing every core. It snaps back to full power when idle.
    tm = request.app.state.task_manager
    reduced = bool(tm is not None and tm.has_active_jobs())

    try:
        board = chess.Board(body.fen)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid FEN")

    turn = "white" if board.turn == chess.WHITE else "black"

    # Checkmate / stalemate / no legal moves — nothing to search.
    if board.is_game_over(claim_draw=True) or not any(board.legal_moves):
        return AnalyzePositionResponse(
            fen=board.fen(), turn=turn, game_over=True, lines=[], reduced=reduced
        )

    # Clamp to sane bounds; never ask for more lines than there are moves.
    depth = max(6, min(24, body.depth))
    multipv = max(1, min(5, body.multipv, board.legal_moves.count()))

    try:
        infos = await sf.analyse_interactive(board, depth, multipv, reduced=reduced)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Engine not available")

    lines: list[AnalyzeLine] = []
    for i, info in enumerate(infos):
        cp, mate = score_to_cp(info)
        pv = info.get("pv") or []
        pv_san: list[str] = []
        first_uci: str | None = None
        if pv:
            first_uci = pv[0].uci()
            scratch = board.copy(stack=False)
            for mv in pv[:12]:
                try:
                    pv_san.append(scratch.san(mv))
                    scratch.push(mv)
                except (AssertionError, ValueError):
                    break
        info_depth = info.get("depth")
        lines.append(
            AnalyzeLine(
                rank=i + 1,
                eval_cp=cp,
                eval_mate=mate,
                best_move_uci=first_uci,
                best_move_san=pv_san[0] if pv_san else None,
                pv_san=pv_san,
                depth=int(info_depth) if info_depth is not None else depth,
            )
        )

    return AnalyzePositionResponse(
        fen=board.fen(), turn=turn, game_over=False, lines=lines, reduced=reduced
    )


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
