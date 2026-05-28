"""Opening tree construction with leak detection."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chess_review.models import Game, GameMove

logger = logging.getLogger(__name__)


@dataclass
class TreeNode:
    fen_key: str
    san: str
    # Every game that passes through this move increments ``visits``. That
    # includes opponent replies — without this, opponent-move nodes had zero
    # visits and got filtered out, collapsing the tree to depth-1 entries.
    visits: int = 0
    # Subset of ``visits`` that were the user's own moves. CPL only makes
    # sense for user moves, so avg_cp_loss divides by this.
    user_move_count: int = 0
    total_cp_loss: int = 0
    # Outcomes of every game that visited this node. ``score_rate`` is
    # (wins + 0.5*draws) / visits — the chess-standard performance score.
    wins: int = 0
    draws: int = 0
    losses: int = 0
    children: dict[str, "TreeNode"] = field(default_factory=dict)

    @property
    def avg_cp_loss(self) -> float:
        if self.user_move_count <= 0:
            return 0.0
        return self.total_cp_loss / self.user_move_count

    @property
    def score_rate(self) -> float:
        if self.visits <= 0:
            return 0.0
        return (self.wins + 0.5 * self.draws) / self.visits

    def to_dict(self, min_visits: int = 5) -> dict | None:
        if self.visits < min_visits and self.san != "root":
            return None
        children = []
        for child in sorted(
            self.children.values(), key=lambda c: c.visits, reverse=True
        ):
            d = child.to_dict(min_visits)
            if d:
                children.append(d)
        return {
            "fen_key": self.fen_key,
            "san": self.san,
            "visit_count": self.visits,
            "user_move_count": self.user_move_count,
            "avg_cp_loss": round(self.avg_cp_loss, 1),
            "total_cp_loss": self.total_cp_loss,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "score_rate": round(self.score_rate, 3),
            "children": children,
        }


async def build_opening_tree(
    session: AsyncSession,
    player_id: uuid.UUID,
    max_ply: int = 24,
    min_visits: int = 5,
    since: datetime | None = None,
    color: str | None = None,
) -> list[dict]:
    """Build the opening tree for a player's games.

    Walks through every game's first max_ply plies. For every move (user OR
    opponent) we record a visit and attach the game's overall result to the
    node. CPL is only accumulated on user moves.

    When ``color`` is set ("white" or "black"), only games where the user
    played that colour are included. This lets the tree show one repertoire
    at a time instead of mixing the user's own first moves (as white) with
    the opponent's first moves (when the user played black).
    """
    filters = [Game.player_id == player_id, Game.analyzed_at.isnot(None)]
    if since is not None:
        filters.append(Game.played_at >= since)
    if color in ("white", "black"):
        filters.append(Game.user_color == color)
    games = (await session.execute(
        select(Game)
        .where(and_(*filters))
        .options(
            selectinload(Game.moves).selectinload(GameMove.position_after),
        )
    )).scalars().all()

    root = TreeNode(fen_key="start", san="root")

    for game in games:
        moves = sorted(game.moves, key=lambda m: m.ply)
        current = root
        outcome = game.user_result

        for move in moves:
            if move.ply > max_ply:
                break
            # Key each child by the RESULTING position, not the source position.
            # All first moves share the same starting position, so keying by
            # position_before would collapse e4/d4/c4 into a single node. The
            # position AFTER a move uniquely identifies which move was played,
            # and naturally merges transpositions deeper in the tree.
            key = move.position_after.fen_key if move.position_after else move.san
            if key not in current.children:
                current.children[key] = TreeNode(fen_key=key, san=move.san)
            node = current.children[key]
            node.visits += 1
            if outcome == "win":
                node.wins += 1
            elif outcome == "draw":
                node.draws += 1
            elif outcome == "loss":
                node.losses += 1
            if move.is_user_move:
                node.user_move_count += 1
                node.total_cp_loss += move.cp_loss or 0
            current = node

    # Flatten root's children as the top-level nodes
    top: list[dict] = []
    for child in sorted(root.children.values(), key=lambda c: c.visits, reverse=True):
        d = child.to_dict(min_visits)
        if d:
            top.append(d)

    return top
