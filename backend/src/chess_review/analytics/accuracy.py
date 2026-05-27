"""Per-game accuracy score and player-wide accuracy trend.

Accuracy is computed per-move using a win-percentage delta (Lichess/chess.com
style), then averaged across the user's moves. This is far more robust than
averaging raw centipawn loss because raw cp_loss is unbounded — a single
missed mate (eval jumps from +9990 to -200) would otherwise tank the whole
game's accuracy.
"""

import math
import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_review.models import Game, GameMove


def _win_percent(cp: float) -> float:
    """Convert a centipawn evaluation (white POV) to white's win probability %.

    Uses the Lichess sigmoid: 50 + 50 * (2/(1+exp(-0.00368208*cp)) - 1).
    Clamped to [0, 100]. Mate scores are pre-clamped by the caller.
    """
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * cp)) - 1.0)


def _move_accuracy(cp_before: float, cp_after: float, mover_is_white: bool) -> float:
    """Per-move accuracy: 100% means the move kept your winning chances intact.

    Compute the drop in *your* win% from before to after the move, then map
    that delta to a 0-100 score via the chess.com/Lichess formula.
    """
    if mover_is_white:
        wp_before = _win_percent(cp_before)
        wp_after = _win_percent(cp_after)
    else:
        wp_before = 100.0 - _win_percent(cp_before)
        wp_after = 100.0 - _win_percent(cp_after)

    drop = max(0.0, wp_before - wp_after)
    raw = 103.1668 * math.exp(-0.04354 * drop) - 3.1668
    return max(0.0, min(100.0, raw))


def _clamp_eval_cp(cp: int | None) -> float:
    """Clamp eval to [-1000, 1000] so a single mate score can't dominate."""
    if cp is None:
        return 0.0
    return float(max(-1000, min(1000, cp)))


def _weighted_game_accuracy(per_move: list[float]) -> float:
    """Lichess-style game accuracy: weighted mean of per-move accuracies where
    each move's weight is the standard deviation of accuracy in a window
    around it.

    Quiet stretches get tiny weights; moves near blunders get large ones, so a
    single missed mate doesn't get diluted by 30 calm developing moves.

    Window size: max(2, ceil(N/10)). Min weight 0.5 to avoid divide-by-zero in
    pathologically flat games.
    """
    n = len(per_move)
    if n == 0:
        return 0.0
    if n == 1:
        return per_move[0]
    window = max(2, math.ceil(n / 10))
    total = 0.0
    weight_sum = 0.0
    for i, acc in enumerate(per_move):
        lo = max(0, i - window)
        hi = min(n, i + window + 1)
        slice_ = per_move[lo:hi]
        mean = sum(slice_) / len(slice_)
        var = sum((a - mean) ** 2 for a in slice_) / len(slice_)
        w = max(0.5, math.sqrt(var))
        total += acc * w
        weight_sum += w
    return total / weight_sum


def compute_game_accuracy(moves: list[GameMove]) -> tuple[float, float, int]:
    """Compute accuracy %, avg CPL, and user-move count for one game.

    Accuracy = Lichess-style volatility-weighted mean of per-move accuracies
    on user moves with both evals set. Calm moves get tiny weights so a single
    blunder isn't diluted away.
    Avg CPL = mean of cp_loss across user moves (still useful as a raw metric).
    """
    accuracies: list[float] = []
    cpl_values: list[int] = []
    for m in moves:
        if not m.is_user_move:
            continue
        if m.eval_before_cp is None or m.eval_after_cp is None:
            continue
        cb = _clamp_eval_cp(m.eval_before_cp)
        ca = _clamp_eval_cp(m.eval_after_cp)
        mover_is_white = m.ply % 2 == 1
        accuracies.append(_move_accuracy(cb, ca, mover_is_white))
        if m.cp_loss is not None:
            cpl_values.append(min(m.cp_loss, 1000))

    if not accuracies:
        return 0.0, 0.0, 0
    avg_acc = round(_weighted_game_accuracy(accuracies), 1)
    avg_cpl = round(sum(cpl_values) / len(cpl_values), 1) if cpl_values else 0.0
    return avg_acc, avg_cpl, len(accuracies)


async def get_game_accuracy(
    session: AsyncSession,
    game_id: uuid.UUID,
) -> dict:
    """Get accuracy score for a single game."""
    rows = (await session.execute(
        select(GameMove)
        .where(GameMove.game_id == game_id)
        .order_by(GameMove.ply)
    )).scalars().all()

    accuracy, avg_cpl, n = compute_game_accuracy(list(rows))
    return {
        "game_id": str(game_id),
        "avg_cpl": avg_cpl,
        "accuracy": accuracy,
        "move_count": n,
    }


async def get_accuracy_trend(
    session: AsyncSession,
    player_id: uuid.UUID,
    time_class: str | None = None,
    since: datetime | None = None,
) -> list[dict]:
    """Get accuracy per game over time, for trend visualization.

    Computes the proper per-move-averaged accuracy on each game.
    """
    filters = [
        Game.player_id == player_id,
        Game.analyzed_at.isnot(None),
    ]
    if time_class:
        filters.append(Game.time_class == time_class)
    if since is not None:
        filters.append(Game.played_at >= since)

    game_rows = (await session.execute(
        select(Game.id, Game.played_at, Game.time_class, Game.user_result, Game.opening_name)
        .where(and_(*filters))
        .order_by(Game.played_at.asc())
    )).all()
    if not game_rows:
        return []

    game_ids = [r.id for r in game_rows]
    move_rows = (await session.execute(
        select(GameMove)
        .where(GameMove.game_id.in_(game_ids))
        .order_by(GameMove.game_id, GameMove.ply)
    )).scalars().all()

    moves_by_game: dict[uuid.UUID, list[GameMove]] = {gid: [] for gid in game_ids}
    for m in move_rows:
        moves_by_game[m.game_id].append(m)

    out: list[dict] = []
    for r in game_rows:
        moves = moves_by_game.get(r.id, [])
        accuracy, avg_cpl, n = compute_game_accuracy(moves)
        if n == 0:
            continue
        out.append({
            "game_id": str(r.id),
            "played_at": r.played_at.isoformat() if r.played_at else None,
            "time_class": r.time_class,
            "user_result": r.user_result,
            "opening_name": r.opening_name,
            "avg_cpl": avg_cpl,
            "accuracy": accuracy,
        })
    return out
