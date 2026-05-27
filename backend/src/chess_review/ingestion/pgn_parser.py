"""PGN parsing and game data extraction."""

import io
import logging
import re
from datetime import datetime, timezone
from typing import Any

import chess
import chess.pgn

from chess_review.util.fen import fen_key

logger = logging.getLogger(__name__)

# Matches chess.com %clk annotation like {[%clk 0:04:52.3]}
CLK_PATTERN = re.compile(r"\[%clk (\d+):(\d+):(\d+(?:\.\d+)?)\]")


def parse_clock_comment(comment: str) -> int | None:
    """Extract clock remaining in milliseconds from a move comment."""
    m = CLK_PATTERN.search(comment)
    if not m:
        return None
    hours = int(m.group(1))
    minutes = int(m.group(2))
    seconds = float(m.group(3))
    return int((hours * 3600 + minutes * 60 + seconds) * 1000)


def parse_chesscom_game(
    raw: dict[str, Any], target_username: str
) -> dict[str, Any] | None:
    """Parse a chess.com API game dict into our internal format.

    Returns None if the game is not parseable (e.g. missing PGN).
    """
    pgn_text = raw.get("pgn")
    if not pgn_text:
        return None

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None

    headers = game.headers
    white = headers.get("White", "")
    black = headers.get("Black", "")

    target_lower = target_username.lower()
    if white.lower() == target_lower:
        user_color = "white"
    elif black.lower() == target_lower:
        user_color = "black"
    else:
        logger.warning("User %s not found in game %s vs %s", target_username, white, black)
        return None

    result = headers.get("Result", "*")
    if result == "1-0":
        user_result = "win" if user_color == "white" else "loss"
    elif result == "0-1":
        user_result = "win" if user_color == "black" else "loss"
    elif result == "1/2-1/2":
        user_result = "draw"
    else:
        user_result = "unknown"

    # Extract time control info
    time_control = headers.get("TimeControl", "?")
    time_class = raw.get("time_class", "unknown")

    # Parse ratings
    white_rating = _safe_int(headers.get("WhiteElo"))
    black_rating = _safe_int(headers.get("BlackElo"))

    # Parse date
    played_at = _parse_datetime(raw.get("end_time"), headers)

    # Provider game ID from the URL
    url = raw.get("url", "")
    provider_game_id = url.split("/")[-1] if url else str(raw.get("end_time", ""))

    # Walk moves
    moves_data: list[dict[str, Any]] = []
    positions: list[dict[str, str]] = []
    board = game.board()
    # Starting position
    start_fk = fen_key(board)
    positions.append({
        "fen_key": start_fk,
        "material": _count_material(board),
    })

    ply = 0
    node = game
    while node.variations:
        next_node = node.variation(0)
        move = next_node.move
        ply += 1

        pos_before_fk = fen_key(board)
        san = board.san(move)
        uci = move.uci()

        is_white_move = board.turn == chess.WHITE
        is_user_move = (user_color == "white" and is_white_move) or (
            user_color == "black" and not is_white_move
        )

        board.push(move)
        pos_after_fk = fen_key(board)

        clock_ms = parse_clock_comment(next_node.comment)

        moves_data.append({
            "ply": ply,
            "san": san,
            "uci": uci,
            "position_before_fen_key": pos_before_fk,
            "position_after_fen_key": pos_after_fk,
            "clock_remaining_ms": clock_ms,
            "is_user_move": is_user_move,
        })

        positions.append({
            "fen_key": pos_after_fk,
            "material": _count_material(board),
        })

        node = next_node

    return {
        "provider_game_id": provider_game_id,
        "pgn": pgn_text,
        "white_username": white,
        "black_username": black,
        "white_rating": white_rating,
        "black_rating": black_rating,
        "user_color": user_color,
        "result": result,
        "user_result": user_result,
        "time_control": time_control,
        "time_class": time_class,
        "eco": headers.get("ECO"),
        "opening_name": _parse_opening_name(headers.get("ECOUrl", "")),
        "played_at": played_at,
        "ply_count": ply,
        "moves": moves_data,
        "positions": positions,
    }


# chess.com writes ECOUrls ending in "/Undefined" when their opening
# classifier doesn't match the position. Strip those so they're treated
# the same as an entirely missing opening.
_PLACEHOLDER_OPENING_NAMES = {"undefined", "unknown", ""}


def _parse_opening_name(eco_url: str) -> str | None:
    if not eco_url:
        return None
    slug = eco_url.rstrip("/").split("/")[-1]
    name = slug.replace("-", " ").strip()
    if not name or name.lower() in _PLACEHOLDER_OPENING_NAMES:
        return None
    return name


def _count_material(board: chess.Board) -> int:
    return sum(
        1 for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.piece_type != chess.KING
    )


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_datetime(end_time: Any, headers: dict[str, str]) -> datetime:
    if end_time and isinstance(end_time, (int, float)):
        return datetime.fromtimestamp(end_time, tz=timezone.utc)
    date_str = headers.get("UTCDate", "")
    time_str = headers.get("UTCTime", "")
    if date_str and time_str:
        try:
            return datetime.strptime(
                f"{date_str} {time_str}", "%Y.%m.%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
