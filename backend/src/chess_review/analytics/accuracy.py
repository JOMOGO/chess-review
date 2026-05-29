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


def _lichess_accuracy(
    win_pcts: list[float],
    user_accuracies: list[tuple[int, float]],
) -> float:
    """Lichess game accuracy.

    Volatility weights are the sliding-window stdev of win-percent across all
    positions (not just user moves). Window size and weight are clamped to
    Lichess's bounds (2..8 and 0.5..12). The final result is the arithmetic
    mean of (a) the weight-paired arithmetic mean of user-move accuracies and
    (b) their harmonic mean, which punishes a single blunder harder than the
    arithmetic mean alone does.
    """
    if len(user_accuracies) == 0:
        return 0.0
    if len(user_accuracies) == 1:
        return user_accuracies[0][1]
    if len(win_pcts) < 2:
        return sum(a for _, a in user_accuracies) / len(user_accuracies)

    window = max(2, min(8, math.ceil(len(win_pcts) / 10)))
    weights: list[float] = []
    for i in range(len(win_pcts)):
        slice_ = win_pcts[i : min(len(win_pcts), i + window)]
        mean = sum(slice_) / len(slice_)
        var = sum((v - mean) ** 2 for v in slice_) / len(slice_)
        weights.append(max(0.5, min(12.0, math.sqrt(var))))

    weighted_sum = 0.0
    total_weight = 0.0
    for pos_idx, acc in user_accuracies:
        w = weights[min(pos_idx, len(weights) - 1)]
        weighted_sum += acc * w
        total_weight += w
    weighted_mean = weighted_sum / total_weight

    accs = [a for _, a in user_accuracies]
    harmonic_mean = len(accs) / sum(1.0 / max(1.0, a) for a in accs)

    return (weighted_mean + harmonic_mean) / 2


def compute_game_accuracy(moves: list[GameMove]) -> tuple[float, float, int]:
    """Compute accuracy %, avg CPL, and user-move count for one game.

    Accuracy is computed with Lichess's full formula: volatility-weighted mean
    of per-move user-side accuracies, averaged with the harmonic mean so a
    single blunder isn't diluted by surrounding calm play.
    Avg CPL = mean of cp_loss across user moves (still useful as a raw metric).
    """
    # White-POV win percent for every position (start + after each move).
    win_pcts: list[float] = []
    first_before = next(
        (m for m in moves if m.eval_before_cp is not None),
        None,
    )
    if first_before is not None and first_before.eval_before_cp is not None:
        win_pcts.append(_win_percent(_clamp_eval_cp(first_before.eval_before_cp)))
    for m in moves:
        if m.eval_after_cp is not None:
            win_pcts.append(_win_percent(_clamp_eval_cp(m.eval_after_cp)))
        elif win_pcts:
            win_pcts.append(win_pcts[-1])

    user_accs: list[tuple[int, float]] = []
    cpl_values: list[int] = []
    wp_idx = 0
    for m in moves:
        here = wp_idx
        wp_idx += 1
        if not m.is_user_move:
            continue
        if m.eval_before_cp is None or m.eval_after_cp is None:
            continue
        cb = _clamp_eval_cp(m.eval_before_cp)
        ca = _clamp_eval_cp(m.eval_after_cp)
        mover_is_white = m.ply % 2 == 1
        user_accs.append((here, _move_accuracy(cb, ca, mover_is_white)))
        if m.cp_loss is not None:
            cpl_values.append(min(m.cp_loss, 1000))

    if not user_accs:
        return 0.0, 0.0, 0
    avg_acc = round(_lichess_accuracy(win_pcts, user_accs), 1)
    avg_cpl = round(sum(cpl_values) / len(cpl_values), 1) if cpl_values else 0.0
    return avg_acc, avg_cpl, len(user_accs)


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
