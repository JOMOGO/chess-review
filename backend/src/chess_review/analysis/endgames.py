"""Endgame reach + bucket classification.

We look for the *first* ply in a game where the user has a sustained
winning advantage in the endgame phase, and bucket the position by
material (e.g. ``KRPvKR``, ``KQvKR``). Pairs with the game's final
``user_result`` to tell us how often the user actually converted from
that kind of position.
"""

from __future__ import annotations

from typing import Any

import chess

# Per-piece-type letter, in priority order for the bucket string.
_PIECE_LETTER: list[tuple[chess.PieceType, str]] = [
    (chess.QUEEN, "Q"),
    (chess.ROOK, "R"),
    (chess.BISHOP, "B"),
    (chess.KNIGHT, "N"),
    (chess.PAWN, "P"),
]


def _piece_letters(board: chess.Board, color: chess.Color) -> str:
    """King first, then heavy pieces, then minors, then pawns. Counts each.

    e.g. White has K + R + 2P -> ``KRPP``.
    """
    out = ["K"]
    for piece_type, letter in _PIECE_LETTER:
        count = len(board.pieces(piece_type, color))
        if count:
            out.append(letter * count)
    return "".join(out)


def classify_endgame_bucket(board: chess.Board, user_color_str: str) -> str | None:
    """Return a bucket label like ``KRPvKR`` for the position, or ``None`` if
    there's still too much material on the board for it to be an interesting
    endgame bucket.

    Format is ``{user}v{opp}`` so the same bucket means "I had X against Y"
    regardless of which colour the user was.
    """
    user_color = chess.WHITE if user_color_str == "white" else chess.BLACK
    user_pieces = _piece_letters(board, user_color)
    opp_pieces = _piece_letters(board, not user_color)

    # Sanity cap. classify_phase("endgame") already requires <=8 non-king
    # pieces total; if both letter counts add up to <=10 (incl. two Ks) we
    # accept the bucket. Anything more is noise.
    if len(user_pieces) + len(opp_pieces) > 10:
        return None
    return f"{user_pieces}v{opp_pieces}"


def detect_won_endgame(
    moves: list[Any],
    user_color_str: str,
    *,
    threshold_cp: int = 200,
    sustained_plies: int = 4,
) -> dict[str, Any] | None:
    """Return the entry point of the first sustained won endgame, or ``None``.

    A "sustained" entry is the first ply of a run of at least
    ``sustained_plies`` consecutive plies where:

      * ``GameMove.phase == "endgame"``
      * ``GameMove.eval_after_cp`` exists
      * user-perspective eval (sign-flipped for black) is >= ``threshold_cp``

    The 200cp / 4-ply defaults filter out blips (engine briefly thinks
    you're winning) and positions where the win is unstable.

    Returned dict has ``entry_ply``, ``bucket``, ``user_cp_at_entry``.
    """
    sign = 1 if user_color_str == "white" else -1
    run_start_move: Any | None = None
    expected_next_ply: int | None = None

    for move in moves:
        if move.phase != "endgame" or move.eval_after_cp is None:
            run_start_move = None
            expected_next_ply = None
            continue

        user_eval = sign * move.eval_after_cp
        in_window = user_eval >= threshold_cp
        is_consecutive = expected_next_ply is None or move.ply == expected_next_ply

        if in_window and is_consecutive:
            if run_start_move is None:
                run_start_move = move
            expected_next_ply = move.ply + 1
            run_length = move.ply - run_start_move.ply + 1
            if run_length >= sustained_plies:
                # Build the board at run_start_move.position_after to get the
                # material setup for bucketing.
                try:
                    board = chess.Board(run_start_move.position_after.fen_key + " 0 1")
                except (ValueError, AttributeError):
                    return None
                bucket = classify_endgame_bucket(board, user_color_str)
                if bucket is None:
                    return None
                return {
                    "entry_ply": run_start_move.ply,
                    "bucket": bucket,
                    "user_cp_at_entry": int(sign * run_start_move.eval_after_cp),
                }
        else:
            run_start_move = move if in_window else None
            expected_next_ply = move.ply + 1 if in_window else None

    return None
