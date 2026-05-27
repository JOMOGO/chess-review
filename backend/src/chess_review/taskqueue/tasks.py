"""Task definitions for import and analysis jobs."""

import asyncio
import logging
import uuid as uuid_mod
from datetime import datetime, timezone

import chess
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from chess_review.config import settings
from chess_review.db import async_session
from chess_review.ingestion.chesscom import ChessComClient
from chess_review.ingestion.pgn_parser import parse_chesscom_game
from chess_review.models import Game, GameMove, ImportJob, Player, Position, PositionEval
from chess_review.taskqueue.manager import JobState

logger = logging.getLogger(__name__)

_SENTINEL = "DONE"


class _Stats:
    """Mutable counters shared between import and analysis coroutines."""

    def __init__(self) -> None:
        self.imported = 0
        self.total_games = 0
        self.analyzed = 0
        self.total_positions = 0
        self.estimated_total = 0
        self.games_done = 0
        self.cache_hits = 0
        self.cloud_hits = 0
        self.tablebase_hits = 0
        self.engine_hits = 0


async def import_and_analyze(
    player_id: str,
    *,
    job_id: str,
    sf_pool: object,
    progress: JobState,
) -> None:
    """Import games and analyze concurrently.

    Analysis starts as soon as the first games are committed to DB,
    running in parallel with the remaining import.
    """
    pid = uuid_mod.UUID(player_id)
    jid = uuid_mod.UUID(job_id)
    client = ChessComClient()
    stats = _Stats()
    game_queue: asyncio.Queue[str] = asyncio.Queue()

    try:
        # Look up player
        async with async_session() as session:
            player = (await session.execute(
                select(Player).where(Player.id == pid)
            )).scalar_one()
            job = (await session.execute(
                select(ImportJob).where(ImportJob.id == jid)
            )).scalar_one()
            username = player.username
            job.status = "running"
            await session.commit()

        # Run import and analysis concurrently
        await asyncio.gather(
            _import_games(pid, jid, username, client, stats, progress, game_queue),
            _analyze_from_queue(pid, jid, sf_pool, stats, progress, game_queue),
        )

        # Mark complete
        async with async_session() as session:
            job = (await session.execute(select(ImportJob).where(ImportJob.id == jid))).scalar_one()
            job.status = "done"
            job.imported_games = stats.imported
            job.analyzed_positions = stats.analyzed
            job.total_positions = stats.total_positions
            job.analyzed_games = stats.games_done
            job.cache_hits = stats.cache_hits
            job.cloud_hits = stats.cloud_hits
            job.tablebase_hits = stats.tablebase_hits
            job.engine_hits = stats.engine_hits
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()

        logger.info("All done: %d games, %d positions analyzed", stats.imported, stats.analyzed)

    except Exception as e:
        logger.exception("Import/analysis failed for player %s", player_id)
        progress.error = str(e)
        try:
            async with async_session() as session:
                job = (await session.execute(
                    select(ImportJob).where(ImportJob.id == jid)
                )).scalar_one()
                job.status = "failed"
                job.error = str(e)
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
        except Exception:
            logger.exception("Failed to update job status")
        raise
    finally:
        await client.close()


# Keep old name as alias for the API
import_player_games = import_and_analyze


async def _import_games(
    pid: uuid_mod.UUID,
    jid: uuid_mod.UUID,
    username: str,
    client: ChessComClient,
    stats: _Stats,
    progress: JobState,
    game_queue: asyncio.Queue[str],
) -> None:
    """Download and import games, pushing IDs to the analysis queue."""
    try:
        async with async_session() as session:
            logger.info("Fetching games for %s", username)
            raw_games = await client.get_all_games(username)

            job = (await session.execute(select(ImportJob).where(ImportJob.id == jid))).scalar_one()
            job.total_games = len(raw_games)
            stats.total_games = len(raw_games)
            progress.total_items = len(raw_games)
            await session.commit()

            BATCH = 25
            games_since_stats = 0

            for raw in raw_games:
                parsed = parse_chesscom_game(raw, username)
                if parsed is None:
                    continue

                existing = (await session.execute(
                    select(Game.id).where(
                        Game.provider == "chesscom",
                        Game.provider_game_id == parsed["provider_game_id"],
                    )
                )).scalar_one_or_none()
                if existing:
                    stats.imported += 1
                    progress.completed_items = stats.imported
                    await game_queue.put(str(existing))
                    continue

                position_map: dict[str, Position] = {}
                for pos_data in parsed["positions"]:
                    fk = pos_data["fen_key"]
                    if fk in position_map:
                        continue
                    existing_pos = (await session.execute(
                        select(Position).where(Position.fen_key == fk)
                    )).scalar_one_or_none()
                    if existing_pos:
                        position_map[fk] = existing_pos
                    else:
                        pos = Position(fen_key=fk, material=pos_data["material"])
                        session.add(pos)
                        await session.flush()
                        position_map[fk] = pos

                game = Game(
                    player_id=pid, provider="chesscom",
                    provider_game_id=parsed["provider_game_id"],
                    pgn=parsed["pgn"],
                    white_username=parsed["white_username"],
                    black_username=parsed["black_username"],
                    white_rating=parsed["white_rating"],
                    black_rating=parsed["black_rating"],
                    user_color=parsed["user_color"],
                    result=parsed["result"],
                    user_result=parsed["user_result"],
                    time_control=parsed["time_control"],
                    time_class=parsed["time_class"],
                    eco=parsed["eco"],
                    opening_name=parsed["opening_name"],
                    played_at=parsed["played_at"],
                    ply_count=parsed["ply_count"],
                )
                session.add(game)
                await session.flush()

                for move_data in parsed["moves"]:
                    pos_before = position_map[move_data["position_before_fen_key"]]
                    pos_after = position_map[move_data["position_after_fen_key"]]
                    session.add(GameMove(
                        game_id=game.id, ply=move_data["ply"],
                        san=move_data["san"], uci=move_data["uci"],
                        position_before_id=pos_before.id,
                        position_after_id=pos_after.id,
                        clock_remaining_ms=move_data["clock_remaining_ms"],
                        is_user_move=move_data["is_user_move"],
                    ))

                stats.imported += 1
                progress.completed_items = stats.imported

                # Commit per game so the SQLite write lock is released quickly,
                # then hand the game to analysis. Heavy stats refresh runs on
                # the BATCH boundary to avoid recounting every game.
                await session.commit()
                await game_queue.put(str(game.id))
                games_since_stats += 1

                if games_since_stats >= BATCH:
                    # Count per-game distinct positions across (before ∪ after),
                    # summed across games — matches what _analyze_single_game
                    # iterates over, so analyzed/total stays consistent.
                    before_q = (
                        select(GameMove.game_id.label("gid"),
                               GameMove.position_before_id.label("pid"))
                        .join(Game, GameMove.game_id == Game.id)
                        .where(Game.player_id == pid)
                    )
                    after_q = (
                        select(GameMove.game_id.label("gid"),
                               GameMove.position_after_id.label("pid"))
                        .join(Game, GameMove.game_id == Game.id)
                        .where(Game.player_id == pid)
                    )
                    real_total = (await session.execute(
                        select(func.count()).select_from(
                            before_q.union(after_q).subquery()
                        )
                    )).scalar() or 0
                    job = (await session.execute(select(ImportJob).where(ImportJob.id == jid))).scalar_one()
                    job.imported_games = stats.imported
                    job.total_positions = real_total
                    player_obj = (await session.execute(select(Player).where(Player.id == pid))).scalar_one()
                    player_obj.total_games_imported = stats.imported
                    await session.commit()
                    logger.info("Imported %d/%d games", stats.imported, len(raw_games))
                    games_since_stats = 0

            # Final update
            player_obj = (await session.execute(select(Player).where(Player.id == pid))).scalar_one()
            job = (await session.execute(select(ImportJob).where(ImportJob.id == jid))).scalar_one()
            job.imported_games = stats.imported
            player_obj.total_games_imported = stats.imported
            player_obj.last_imported_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info("Import complete: %d games for %s", stats.imported, username)
    finally:
        # Signal analysis that import is done
        await game_queue.put(_SENTINEL)


async def _analyze_from_queue(
    pid: uuid_mod.UUID,
    jid: uuid_mod.UUID,
    sf_pool: object,
    stats: _Stats,
    progress: JobState,
    game_queue: asyncio.Queue[str],
) -> None:
    """Consume game IDs from the queue and analyze them.

    Runs up to ``sf_pool.pool_size`` games concurrently. Each game pins one
    Stockfish engine for its lifetime so positions of that game flow serially
    through the same engine — keeping the transposition table warm across
    moves that share most of their search tree.
    """
    from chess_review.engine.analysis_orchestrator import (
        AnalysisOrchestrator,
        classify_move,
        classify_phase,
        eval_to_cp,
    )

    orchestrator = AnalysisOrchestrator(sf_pool)  # type: ignore[arg-type]
    max_concurrent = max(1, getattr(sf_pool, "pool_size", 1))

    in_flight: set[asyncio.Task[None]] = set()

    async def _run(gid: uuid_mod.UUID) -> None:
        # Pin one engine for the lifetime of this game (B1). All local-SF
        # calls below route to this engine so its TT stays warm across the
        # game's positions. May be None if the pool isn't started; in that
        # case the orchestrator's SF path will error as before.
        pinned_engine = await sf_pool.acquire()  # type: ignore[attr-defined]
        try:
            await _analyze_single_game(
                gid, jid, pinned_engine, orchestrator, stats, progress,
                classify_move, classify_phase, eval_to_cp,
            )
        except Exception:
            logger.exception("Failed to analyze game %s, skipping", gid)
        finally:
            sf_pool.release(pinned_engine)  # type: ignore[attr-defined]

    try:
        while True:
            game_id_str = await game_queue.get()
            if game_id_str == _SENTINEL:
                break

            gid = uuid_mod.UUID(game_id_str)
            # Cap in-flight games at pool_size so we don't oversubscribe engines.
            # We remove completed tasks explicitly here (the done_callback also
            # does so, idempotently) so the while-check shrinks immediately
            # without depending on event-loop callback ordering.
            while len(in_flight) >= max_concurrent:
                done, _ = await asyncio.wait(
                    in_flight, return_when=asyncio.FIRST_COMPLETED
                )
                in_flight -= done
            task = asyncio.create_task(_run(gid))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)

        # Drain
        if in_flight:
            await asyncio.gather(*in_flight, return_exceptions=True)
    finally:
        await orchestrator.close()


async def _analyze_single_game(
    gid: uuid_mod.UUID,
    jid: uuid_mod.UUID,
    pinned_engine: object,
    orchestrator: object,
    stats: _Stats,
    progress: JobState,
    classify_move_fn: object,
    classify_phase_fn: object,
    eval_to_cp_fn: object,
) -> None:
    """Analyze a single game: eval positions, classify moves, update DB.

    Pins one Stockfish engine for the duration of the game. Non-SF lookups
    (tablebase + Lichess cloud) run concurrently per position; local SF runs
    serially on the pinned engine in game order so the transposition table
    stays hot across positions.
    """
    async with async_session() as session:
        game = (await session.execute(
            select(Game).where(Game.id == gid)
            .options(
                selectinload(Game.moves).selectinload(GameMove.position_before),
                selectinload(Game.moves).selectinload(GameMove.position_after),
            )
        )).scalar_one()

        # Skip if already analyzed
        if game.analyzed_at is not None:
            stats.games_done += 1
            return

        stats.games_done += 1
        logger.info("Analyzing game %d (%s)", stats.games_done, game.id)
        move_evals: dict[str, dict[str, object]] = {}

        # Collect unique positions for this game (preserving game order, position_before first).
        # Also record the earliest ply each position appears at — used to skip
        # Lichess cloud lookups past the opening where cloud rarely has hits.
        unique_positions: list[object] = []
        seen_ids: set[str] = set()
        position_min_ply: dict[str, int] = {}
        for move in game.moves:
            before_ply = max(0, move.ply - 1)
            after_ply = move.ply
            for pos, ply in ((move.position_before, before_ply), (move.position_after, after_ply)):
                pos_id_str = str(pos.id)
                prev_ply = position_min_ply.get(pos_id_str)
                if prev_ply is None or ply < prev_ply:
                    position_min_ply[pos_id_str] = ply
                if pos_id_str in seen_ids:
                    continue
                seen_ids.add(pos_id_str)
                unique_positions.append(pos)
                move_evals[pos_id_str] = {}

        # Bulk cache lookup at inventory depth — one query, pick best per position_id.
        position_ids = [pos.id for pos in unique_positions]  # type: ignore[attr-defined]
        cached_inv: dict[str, PositionEval] = {}
        if position_ids:
            rows = (await session.execute(
                select(PositionEval)
                .where(
                    PositionEval.position_id.in_(position_ids),
                    PositionEval.depth >= settings.inventory_depth,
                )
            )).scalars().all()
            for row in rows:
                key = str(row.position_id)
                prev = cached_inv.get(key)
                if prev is None or row.depth > prev.depth:
                    cached_inv[key] = row

        uncached: list[tuple[str, object]] = []
        for pos in unique_positions:
            pos_id_str = str(pos.id)  # type: ignore[attr-defined]
            existing = cached_inv.get(pos_id_str)
            if existing:
                move_evals[pos_id_str] = {
                    "eval_cp": existing.eval_cp, "eval_mate": existing.eval_mate,
                    "best_move_uci": existing.best_move_uci,
                }
                stats.cache_hits += 1
                stats.analyzed += 1
            else:
                uncached.append((pos_id_str, pos))

        stats.total_positions += len(move_evals)

        # A3: forced-move skip. When a position has exactly one legal move, the
        # engine's eval is identical to the eval of the resulting position
        # (mover has no choice). If the forced position isn't reachable any
        # other way in this game, we can skip searching it and copy the after
        # position's eval after analysis.
        positions_as_after: set[str] = {str(m.position_after_id) for m in game.moves}
        forced_skip: dict[str, tuple[str, str]] = {}  # before_id -> (after_id, forced_uci)
        if uncached:
            uncached_ids = {pid_s for pid_s, _ in uncached}
            for move in game.moves:
                pid_before = str(move.position_before_id)
                if pid_before not in uncached_ids or pid_before in forced_skip:
                    continue
                if pid_before in positions_as_after:
                    continue
                try:
                    board_check = chess.Board(move.position_before.fen_key + " 0 1")
                except Exception:
                    continue
                if board_check.legal_moves.count() == 1:
                    forced_skip[pid_before] = (str(move.position_after_id), move.uci)
            if forced_skip:
                uncached = [(pid_s, pos) for pid_s, pos in uncached if pid_s not in forced_skip]

        # Two-phase inventory analysis (B1): non-SF lookups in parallel, then
        # local Stockfish serially on the pinned engine in game order so the
        # engine's transposition table stays warm across positions.
        game_token = str(gid)
        if uncached:
            prefetch_results = await asyncio.gather(*[
                orchestrator.prefetch_non_sf(  # type: ignore[attr-defined]
                    pos.fen_key,
                    settings.inventory_depth,
                    ply=position_min_ply.get(pid_s),
                )
                for pid_s, pos in uncached
            ])
            sf_needed: list[tuple[str, object]] = []
            for (pid_s, pos), res in zip(uncached, prefetch_results):
                if res:
                    _record_inventory_eval(session, pos, pid_s, res, move_evals, stats)
                else:
                    sf_needed.append((pid_s, pos))

            # Serial SF on pinned engine; positions are in game order so TT
            # entries from move N help the search at move N+1.
            for pid_s, pos in sf_needed:
                try:
                    result = await orchestrator.analyze_position(  # type: ignore[attr-defined]
                        pos.fen_key,
                        min_depth=settings.inventory_depth,
                        game=game_token,
                        ply=position_min_ply.get(pid_s),
                        engine=pinned_engine,
                    )
                    _record_inventory_eval(session, pos, pid_s, result, move_evals, stats)
                except Exception:
                    logger.exception("Failed to analyze %s", pos.fen_key)  # type: ignore[attr-defined]
                    move_evals[pid_s] = {"eval_cp": None, "eval_mate": None, "best_move_uci": ""}
                    stats.analyzed += 1

            # Commit (not just flush) so SQLite write lock is released before
            # the slow deep-pass below; otherwise concurrent imports block.
            await session.commit()

        # Post-fill forced-skip positions from their after-position eval.
        for pid_before, (pid_after, forced_uci) in forced_skip.items():
            ae = move_evals.get(pid_after)
            if not ae or "eval_cp" not in ae:
                continue
            move_evals[pid_before] = {
                "eval_cp": ae["eval_cp"],
                "eval_mate": ae["eval_mate"],
                "best_move_uci": forced_uci,
            }
            stats.analyzed += 1

        # Deep pass for swing positions — collect swing candidates, bulk-check cache, then analyze misses.
        swing_candidates: list[object] = []
        swing_seen: set[str] = set()
        for move in game.moves:
            be = move_evals.get(str(move.position_before_id), {})
            ae = move_evals.get(str(move.position_after_id), {})
            cb = eval_to_cp_fn(be.get("eval_cp"), be.get("eval_mate"))
            ca = eval_to_cp_fn(ae.get("eval_cp"), ae.get("eval_mate"))

            if abs(cb - ca) > settings.swing_threshold_cp:
                for pos in [move.position_before, move.position_after]:
                    pid_s = str(pos.id)
                    if pid_s in swing_seen:
                        continue
                    swing_seen.add(pid_s)
                    swing_candidates.append(pos)

        cached_deep: dict[str, PositionEval] = {}
        if swing_candidates:
            swing_ids = [pos.id for pos in swing_candidates]  # type: ignore[attr-defined]
            rows = (await session.execute(
                select(PositionEval)
                .where(
                    PositionEval.position_id.in_(swing_ids),
                    PositionEval.depth >= settings.deep_depth,
                )
            )).scalars().all()
            for row in rows:
                key = str(row.position_id)
                prev = cached_deep.get(key)
                if prev is None or row.depth > prev.depth:
                    cached_deep[key] = row

        deep_needed: list[tuple[str, object]] = []
        for pos in swing_candidates:
            pid_s = str(pos.id)  # type: ignore[attr-defined]
            ed = cached_deep.get(pid_s)
            if ed:
                move_evals[pid_s] = {"eval_cp": ed.eval_cp, "eval_mate": ed.eval_mate, "best_move_uci": ed.best_move_uci}
            else:
                deep_needed.append((pid_s, pos))

        if deep_needed:
            # Same two-phase split as the inventory pass.
            deep_prefetch = await asyncio.gather(*[
                orchestrator.prefetch_non_sf(  # type: ignore[attr-defined]
                    pos.fen_key,
                    settings.deep_depth,
                    ply=position_min_ply.get(pid_s),
                )
                for pid_s, pos in deep_needed
            ])
            deep_sf: list[tuple[str, object]] = []
            for (pid_s, pos), res in zip(deep_needed, deep_prefetch):
                if res:
                    _record_deep_eval(session, pos, pid_s, res, move_evals)
                else:
                    deep_sf.append((pid_s, pos))

            for pid_s, pos in deep_sf:
                try:
                    result = await orchestrator.analyze_position(  # type: ignore[attr-defined]
                        pos.fen_key,
                        min_depth=settings.deep_depth,
                        game=game_token,
                        ply=position_min_ply.get(pid_s),
                        engine=pinned_engine,
                    )
                    _record_deep_eval(session, pos, pid_s, result, move_evals)
                except Exception:
                    logger.exception("Deep analysis failed for %s", pos.fen_key)  # type: ignore[attr-defined]
            await session.commit()

        # Classify moves
        board = chess.Board()
        for move in game.moves:
            be = move_evals.get(str(move.position_before_id), {})
            ae = move_evals.get(str(move.position_after_id), {})
            cp_before = eval_to_cp_fn(be.get("eval_cp"), be.get("eval_mate"))
            cp_after = eval_to_cp_fn(ae.get("eval_cp"), ae.get("eval_mate"))
            best_uci = be.get("best_move_uci", "")

            if not best_uci:
                cp_after_best = cp_before
            elif best_uci == move.uci:
                cp_after_best = cp_after
            else:
                cp_after_best = cp_before

            mover_is_white = move.ply % 2 == 1
            classification, cp_loss = classify_move_fn(cp_before, cp_after, cp_after_best, mover_is_white)

            move.eval_before_cp = cp_before
            move.eval_after_cp = cp_after
            move.cp_loss = cp_loss
            move.classification = classification
            move.phase = classify_phase_fn(board, move.ply)

            try:
                board.push_uci(move.uci)
            except Exception:
                pass

        game.analyzed_at = datetime.now(timezone.utc)

        # Write stats + game result in same transaction
        job = (await session.execute(select(ImportJob).where(ImportJob.id == jid))).scalar_one()
        job.analyzed_positions = stats.analyzed
        job.analyzed_games = stats.games_done
        # Don't overwrite total_positions — import side sets the real count
        job.cache_hits = stats.cache_hits
        job.cloud_hits = stats.cloud_hits
        job.tablebase_hits = stats.tablebase_hits
        job.engine_hits = stats.engine_hits
        await session.commit()

    logger.info(
        "Game %d done (%d pos: %d cache, %d cloud, %d tb, %d engine)",
        stats.games_done, stats.analyzed,
        stats.cache_hits, stats.cloud_hits, stats.tablebase_hits, stats.engine_hits,
    )


def _record_inventory_eval(
    session: object,
    pos: object,
    pid_s: str,
    result: dict[str, object],
    move_evals: dict[str, dict[str, object]],
    stats: _Stats,
) -> None:
    """Persist an inventory-pass eval row and update counters."""
    session.add(PositionEval(  # type: ignore[attr-defined]
        position_id=pos.id, engine=result["engine"], depth=result["depth"],  # type: ignore[attr-defined]
        eval_cp=result["eval_cp"], eval_mate=result["eval_mate"],
        best_move_uci=result["best_move_uci"], pv=result["pv"],
        nodes=result["nodes"], computed_at=result["computed_at"],
    ))
    move_evals[pid_s] = {
        "eval_cp": result["eval_cp"], "eval_mate": result["eval_mate"],
        "best_move_uci": result["best_move_uci"],
    }
    engine_name = result["engine"]
    if engine_name == "lichess-cloud":
        stats.cloud_hits += 1
    elif engine_name == "lichess-tablebase":
        stats.tablebase_hits += 1
    else:
        stats.engine_hits += 1
    stats.analyzed += 1


def _record_deep_eval(
    session: object,
    pos: object,
    pid_s: str,
    result: dict[str, object],
    move_evals: dict[str, dict[str, object]],
) -> None:
    """Persist a deep-pass eval row. Does not bump stats — those positions
    were already counted in the inventory pass."""
    session.add(PositionEval(  # type: ignore[attr-defined]
        position_id=pos.id, engine=result["engine"], depth=result["depth"],  # type: ignore[attr-defined]
        eval_cp=result["eval_cp"], eval_mate=result["eval_mate"],
        best_move_uci=result["best_move_uci"], pv=result["pv"],
        nodes=result["nodes"], computed_at=result["computed_at"],
    ))
    move_evals[pid_s] = {
        "eval_cp": result["eval_cp"], "eval_mate": result["eval_mate"],
        "best_move_uci": result["best_move_uci"],
    }
