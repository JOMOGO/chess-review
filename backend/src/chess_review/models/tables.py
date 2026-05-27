"""ORM models matching the spec's data model (Section 5)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chess_review.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Player(Base):
    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    username_lower: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    last_imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_games_imported: Mapped[int] = mapped_column(Integer, default=0)

    games: Mapped[list["Game"]] = relationship(back_populates="player")
    import_jobs: Mapped[list["ImportJob"]] = relationship(back_populates="player")

    __table_args__ = (
        Index("ix_players_provider_username", "provider", "username_lower", unique=True),
    )


class Game(Base):
    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    player_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("players.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_game_id: Mapped[str] = mapped_column(Text, nullable=False)
    pgn: Mapped[str] = mapped_column(Text, nullable=False)
    white_username: Mapped[str] = mapped_column(Text, nullable=False)
    black_username: Mapped[str] = mapped_column(Text, nullable=False)
    white_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_color: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    user_result: Mapped[str] = mapped_column(Text, nullable=False)
    time_control: Mapped[str] = mapped_column(Text, nullable=False)
    time_class: Mapped[str] = mapped_column(Text, nullable=False)
    eco: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ply_count: Mapped[int] = mapped_column(Integer, nullable=False)
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    player: Mapped["Player"] = relationship(back_populates="games")
    moves: Mapped[list["GameMove"]] = relationship(
        back_populates="game", order_by="GameMove.ply"
    )

    __table_args__ = (
        Index("ix_games_provider_id", "provider", "provider_game_id", unique=True),
    )


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    fen_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    zobrist: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    material: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    evals: Mapped[list["PositionEval"]] = relationship(back_populates="position")


class PositionEval(Base):
    __tablename__ = "position_evals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    position_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("positions.id"), nullable=False
    )
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    eval_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eval_mate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    best_move_uci: Mapped[str] = mapped_column(Text, nullable=False)
    pv: Mapped[str] = mapped_column(Text, nullable=False, default="")
    nodes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    position: Mapped["Position"] = relationship(back_populates="evals")

    __table_args__ = (
        Index("ix_position_evals_pos_depth", "position_id", "depth"),
    )


class GameMove(Base):
    __tablename__ = "game_moves"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    game_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("games.id"), nullable=False
    )
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    san: Mapped[str] = mapped_column(Text, nullable=False)
    uci: Mapped[str] = mapped_column(Text, nullable=False)
    position_before_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("positions.id"), nullable=False
    )
    position_after_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("positions.id"), nullable=False
    )
    clock_remaining_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eval_before_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eval_after_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cp_loss: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    phase: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_user_move: Mapped[bool] = mapped_column(Boolean, nullable=False)

    game: Mapped["Game"] = relationship(back_populates="moves")
    position_before: Mapped["Position"] = relationship(foreign_keys=[position_before_id])
    position_after: Mapped["Position"] = relationship(foreign_keys=[position_after_id])

    __table_args__ = (
        Index("ix_game_moves_game_ply", "game_id", "ply"),
        Index("ix_game_moves_classification", "game_id", "is_user_move", "classification"),
    )


class MoveTactic(Base):
    """A tactical motif detected on a single move.

    One row per (move, motif). A single move can have multiple motifs (e.g. a
    fork that's also a discovered attack). The detector currently writes only
    for moves classified ``mistake``/``blunder``/``miss`` — i.e. tactics the
    user *missed*. Positive cases ("you found a fork") are not yet recorded.
    """

    __tablename__ = "move_tactics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    game_move_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("game_moves.id"), nullable=False
    )
    motif: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    __table_args__ = (
        Index("ix_move_tactics_move_motif", "game_move_id", "motif", unique=True),
        Index("ix_move_tactics_motif", "motif"),
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    player_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("players.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    total_games: Mapped[int] = mapped_column(Integer, default=0)
    imported_games: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_positions: Mapped[int] = mapped_column(Integer, default=0)
    total_positions: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_games: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    cloud_hits: Mapped[int] = mapped_column(Integer, default=0)
    tablebase_hits: Mapped[int] = mapped_column(Integer, default=0)
    engine_hits: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    player: Mapped["Player"] = relationship(back_populates="import_jobs")
