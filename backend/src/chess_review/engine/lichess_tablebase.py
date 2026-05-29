"""Lichess tablebase API — perfect endgame evaluation for positions with ≤7 pieces."""

import logging

import chess
import httpx

logger = logging.getLogger(__name__)


class LichessTablebaseClient:
    """Query Lichess Syzygy tablebase API for endgame positions."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=2.0,
            headers={"User-Agent": "chess-review/0.1"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    def is_tablebase_position(self, fen: str) -> bool:
        """Check if position has ≤7 pieces (full Lichess tablebase coverage).

        Once a game drops to ≤7 pieces, all remaining positions are also ≤7.
        Requests are fired concurrently so latency is amortized.
        """
        try:
            board = chess.Board(fen)
            return len(board.piece_map()) <= 7
        except Exception:
            return False

    async def probe(self, fen: str) -> dict[str, object] | None:
        """Probe the tablebase for a position.

        Returns eval dict with perfect WDL result, or None if not available.
        """
        if not self.is_tablebase_position(fen):
            return None

        try:
            resp = await self._client.get(
                "https://tablebase.lichess.org/standard",
                params={"fen": fen},
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            category = data.get("category")
            if not category:
                return None

            # Convert tablebase result to centipawns.
            # category and dtm are from the SIDE-TO-MOVE's perspective per the
            # Lichess tablebase API, but every other eval in this codebase
            # (Stockfish via pov.white(), Lichess cloud, GameMove.eval_*_cp) is
            # white-POV. We flip the sign here for black-to-move positions so
            # downstream eval_to_cp and the eval bar read consistently.
            # category: "win", "maybe-win", "cursed-win", "draw",
            #           "blessed-loss", "maybe-loss", "loss"
            dtm = data.get("dtm")  # distance to mate (signed, stm POV)
            white_to_move = chess.Board(fen).turn

            eval_cp: int | None
            eval_mate: int | None
            if category in ("win", "maybe-win", "cursed-win"):
                eval_mate = dtm if dtm else 1
                eval_cp = None
            elif category in ("loss", "maybe-loss", "blessed-loss"):
                eval_mate = dtm if dtm else -1
                eval_cp = None
            else:  # draw
                eval_cp = 0
                eval_mate = None
            if eval_mate is not None and not white_to_move:
                eval_mate = -eval_mate

            # Best move
            moves = data.get("moves", [])
            best_uci = moves[0]["uci"] if moves else ""

            return {
                "engine": "lichess-tablebase",
                "depth": 254,  # tablebase = perfect depth
                "eval_cp": eval_cp,
                "eval_mate": eval_mate,
                "best_move_uci": best_uci,
                "pv": best_uci,
                "nodes": 0,
            }

        except Exception:
            logger.debug("Tablebase probe failed for %s", fen, exc_info=True)
            return None
