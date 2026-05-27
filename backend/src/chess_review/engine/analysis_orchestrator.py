"""Orchestrates two-tier analysis: Lichess cloud -> Stockfish inventory -> deep pass."""

import logging
from datetime import datetime, timezone

import chess

from chess_review.config import settings
from chess_review.engine.lichess_cloud import LichessCloudClient
from chess_review.engine.lichess_tablebase import LichessTablebaseClient
from chess_review.engine.stockfish_pool import StockfishPool

logger = logging.getLogger(__name__)


def score_to_cp(info: chess.engine.InfoDict) -> tuple[int | None, int | None]:
    """Extract centipawn and mate scores from White's perspective."""
    score = info.get("score")
    if score is None:
        return None, None
    pov = score.white()
    if pov.is_mate():
        return None, pov.mate()
    return pov.score(), None


class AnalysisOrchestrator:
    """Coordinates Lichess cloud checks and local Stockfish analysis."""

    def __init__(self, sf_pool: StockfishPool) -> None:
        self._sf = sf_pool
        self._cloud = LichessCloudClient() if settings.lichess_cloud_enabled else None
        self._tablebase = LichessTablebaseClient()
        self._inventory_depth = settings.inventory_depth
        self._deep_depth = settings.deep_depth

    async def close(self) -> None:
        if self._cloud:
            await self._cloud.close()
        await self._tablebase.close()

    async def prefetch_non_sf(
        self,
        fen: str,
        target_depth: int,
        *,
        ply: int | None = None,
    ) -> dict[str, object] | None:
        """Try tablebase + Lichess cloud only. Returns None if neither hits.

        Used by the per-game flow to fan out non-SF lookups in parallel before
        serializing local-Stockfish calls onto a pinned engine.
        """
        tb = await self._tablebase.probe(fen)
        if tb:
            tb["computed_at"] = datetime.now(timezone.utc)
            return tb

        cloud_eligible = self._cloud and (ply is None or ply <= settings.cloud_max_ply)
        if cloud_eligible:
            cloud = await self._cloud.get_eval(fen, min_depth=target_depth)  # type: ignore[union-attr]
            if cloud:
                best_uci = ""
                pv_str = cloud.get("pv", "")
                if isinstance(pv_str, str) and pv_str:
                    best_uci = pv_str.split()[0]
                return {
                    "engine": "lichess-cloud",
                    "depth": cloud["depth"],
                    "eval_cp": cloud["eval_cp"],
                    "eval_mate": cloud["eval_mate"],
                    "best_move_uci": best_uci,
                    "pv": _truncate_pv(pv_str, 5),
                    "nodes": cloud.get("nodes"),
                    "computed_at": datetime.now(timezone.utc),
                }
        return None

    async def analyze_position(
        self,
        fen: str,
        min_depth: int | None = None,
        *,
        game: object | None = None,
        ply: int | None = None,
        engine: object | None = None,
    ) -> dict[str, object]:
        """Analyze a single position. Returns eval dict.

        Priority: tablebase (perfect) > cloud cache > local Stockfish.

        ``game`` is a stable per-game token forwarded to the Stockfish pool to
        keep the TT warm across positions of the same game.

        ``ply`` is an optional position-ply hint. When provided and greater
        than ``settings.cloud_max_ply``, the Lichess cloud check is skipped
        because cloud coverage drops off sharply after the opening.

        ``engine`` is an optional pinned engine acquired via
        :meth:`StockfishPool.acquire`. When provided, local Stockfish runs on
        that engine directly (no pool semaphore handoff) — used by the
        per-game flow to preserve transposition-table locality.
        """
        target_depth = min_depth or self._inventory_depth

        prefetched = await self.prefetch_non_sf(fen, target_depth, ply=ply)
        if prefetched:
            return prefetched

        # Local Stockfish
        if not self._sf.available:
            raise RuntimeError("Stockfish not available")

        board = chess.Board(fen)
        if engine is not None:
            info = await self._sf.analyse_on(engine, board, target_depth, game=game)  # type: ignore[arg-type]
        else:
            info = await self._sf.analyse(board, target_depth, game=game)
        cp, mate = score_to_cp(info)
        pv_moves = info.get("pv", [])
        best_uci = pv_moves[0].uci() if pv_moves else ""
        pv_str = " ".join(m.uci() for m in pv_moves[:5])

        return {
            "engine": "stockfish-18",
            "depth": info.get("depth", target_depth),
            "eval_cp": cp,
            "eval_mate": mate,
            "best_move_uci": best_uci,
            "pv": pv_str,
            "nodes": info.get("nodes"),
            "computed_at": datetime.now(timezone.utc),
        }


def _truncate_pv(pv: str | object, max_moves: int) -> str:
    if not isinstance(pv, str):
        return ""
    parts = pv.split()
    return " ".join(parts[:max_moves])


def classify_move(
    cp_before: int, cp_after_actual: int, cp_after_best: int, mover_is_white: bool
) -> tuple[str, int]:
    """Classify a move. Returns (classification, cp_loss).

    Possible classifications (from best to worst):
        ``best``      — engine's top move (cp_loss < 10).
        ``good``      — cp_loss < 40, or any move in an already-decided position.
        ``inaccuracy``— cp_loss 40-99.
        ``mistake``   — cp_loss 100-299.
        ``blunder``   — cp_loss >= 300.
        ``miss``      — you were winning, played a non-top move, and the win
                        evaporated. Severity-wise it overrides mistake/blunder.

    All evals are White's perspective on input; internally flipped to "the
    mover's perspective" via ``sign``. Returns ``loss >= 0`` in centipawns.
    """
    sign = 1 if mover_is_white else -1
    before_user = sign * cp_before
    best = sign * cp_after_best
    actual = sign * cp_after_actual
    loss = max(0, best - actual)

    # Miss: you were winning, gave it back. Checked before mistake/blunder so
    # the more specific tag wins.
    if before_user >= 200 and best >= 200 and actual < 100 and loss >= 150:
        return "miss", loss

    # Dampening: both winning/losing — don't punish you for slippage in an
    # already-decided position.
    if best > 500 and actual > 300:
        cls = "good" if loss < 200 else "inaccuracy"
        return cls, loss
    if best < -300:
        return "good", loss

    if loss < 10:
        return "best", loss
    if loss < 40:
        return "good", loss
    if loss < 100:
        return "inaccuracy", loss
    if loss < 300:
        return "mistake", loss
    return "blunder", loss


def classify_phase(board: chess.Board, ply: int) -> str:
    """Classify the game phase for a position."""
    total_non_king = sum(
        1 for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.piece_type != chess.KING
    )
    if ply <= 20 and total_non_king >= 24:
        return "opening"
    if total_non_king <= 8:
        return "endgame"
    return "middlegame"


def eval_to_cp(eval_cp: int | None, eval_mate: int | None) -> int:
    """Convert eval to centipawns. Mate scores mapped to large values."""
    if eval_cp is not None:
        return eval_cp
    if eval_mate is not None:
        # Positive mate = white mates, negative = black mates
        if eval_mate > 0:
            return 10000 - eval_mate * 10
        return -10000 - eval_mate * 10
    return 0
