"""FEN normalization for position deduplication."""

import chess


def fen_key(board: chess.Board) -> str:
    """Strip half-move clock and fullmove number for position dedup.

    This is the single most important function in the codebase.
    All position lookups go through it.
    """
    parts = board.fen().split(" ")
    return " ".join(parts[:4])
