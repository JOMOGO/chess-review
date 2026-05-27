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
    visits: int = 0
    total_cp_loss: int = 0
    children: dict[str, "TreeNode"] = field(default_factory=dict)

    @property
    def avg_cp_loss(self) -> float:
        return self.total_cp_loss / self.visits if self.visits > 0 else 0.0

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
            "avg_cp_loss": round(self.avg_cp_loss, 1),
            "total_cp_loss": self.total_cp_loss,
            "children": children,
        }


async def build_opening_tree(
    session: AsyncSession,
    player_id: uuid.UUID,
    max_ply: int = 24,
    min_visits: int = 5,
    since: datetime | None = None,
) -> list[dict]:
    """Build the opening tree for a player's games.

    Walks through every game's first max_ply plies.
    For each position where it's the user's turn, record
    the move played and its cp_loss.
    """
    filters = [Game.player_id == player_id, Game.analyzed_at.isnot(None)]
    if since is not None:
        filters.append(Game.played_at >= since)
    games = (await session.execute(
        select(Game)
        .where(and_(*filters))
        .options(
            selectinload(Game.moves).selectinload(GameMove.position_before),
        )
    )).scalars().all()

    root = TreeNode(fen_key="start", san="root")

    for game in games:
        moves = sorted(game.moves, key=lambda m: m.ply)
        current = root

        for move in moves:
            if move.ply > max_ply:
                break
            if not move.is_user_move:
                # Opponent move: navigate down the tree
                key = move.position_before.fen_key if move.position_before else move.san
                if key not in current.children:
                    current.children[key] = TreeNode(
                        fen_key=key, san=move.san
                    )
                current = current.children[key]
                continue

            # User move: record visit and cp_loss
            key = move.position_before.fen_key if move.position_before else move.san
            if key not in current.children:
                current.children[key] = TreeNode(
                    fen_key=key, san=move.san
                )
            node = current.children[key]
            node.visits += 1
            node.total_cp_loss += move.cp_loss or 0
            current = node

    # Flatten root's children as the top-level nodes
    result = []
    for child in sorted(root.children.values(), key=lambda c: c.visits, reverse=True):
        d = child.to_dict(min_visits)
        if d:
            result.append(d)

    return result
