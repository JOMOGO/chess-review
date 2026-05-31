"""Pydantic request/response models for the API."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    db: bool
    engine: str
    queue: bool


class CreatePlayerRequest(BaseModel):
    provider: str = "chesscom"
    username: str


class PlayerOut(BaseModel):
    id: uuid.UUID
    provider: str
    username: str
    display_name: str | None
    created_at: datetime
    last_imported_at: datetime | None
    total_games_imported: int

    model_config = {"from_attributes": True}


class ImportStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    total_games: int
    imported_games: int
    analyzed_positions: int
    total_positions: int
    analyzed_games: int
    cache_hits: int
    cloud_hits: int
    tablebase_hits: int
    engine_hits: int
    error: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class GameListItem(BaseModel):
    id: str
    white_username: str
    black_username: str
    white_rating: int | None
    black_rating: int | None
    user_color: str
    result: str
    user_result: str
    time_control: str
    time_class: str
    eco: str | None
    opening_name: str | None
    played_at: datetime
    ply_count: int
    analyzed_at: datetime | None

    model_config = {"from_attributes": True}


class GameMoveOut(BaseModel):
    ply: int
    san: str
    uci: str
    fen_before: str | None = None
    fen_after: str | None = None
    clock_remaining_ms: int | None
    eval_before_cp: int | None
    eval_after_cp: int | None
    cp_loss: int | None
    classification: str | None
    phase: str | None
    is_user_move: bool

    model_config = {"from_attributes": True}


class GameDetail(BaseModel):
    id: str
    white_username: str
    black_username: str
    white_rating: int | None
    black_rating: int | None
    user_color: str
    result: str
    user_result: str
    time_control: str
    time_class: str
    eco: str | None
    opening_name: str | None
    played_at: datetime
    ply_count: int
    pgn: str
    moves: list[GameMoveOut]

    model_config = {"from_attributes": True}


class AnalyzePositionRequest(BaseModel):
    fen: str
    multipv: int = 3
    depth: int = 18


class AnalyzeLine(BaseModel):
    """One engine line for an interactively-analysed position. Evals are from
    White's perspective, matching the stored per-game evals and the eval bar."""

    rank: int
    eval_cp: int | None
    eval_mate: int | None
    best_move_uci: str | None
    best_move_san: str | None
    pv_san: list[str]
    depth: int


class AnalyzePositionResponse(BaseModel):
    fen: str
    turn: str  # "white" | "black" — side to move
    game_over: bool
    lines: list[AnalyzeLine]
    # True when an import was in flight, so the engine ran on reduced threads.
    reduced: bool = False


class OpeningTreeNode(BaseModel):
    fen_key: str
    san: str
    visit_count: int
    avg_cp_loss: float
    total_cp_loss: int
    children: list["OpeningTreeNode"] = []


class InsightPhasePerformance(BaseModel):
    phase: str
    color: str | None
    sample_size: int
    avg_cpl: float
    blunder_rate: float
    mistake_rate: float
    inaccuracy_rate: float


class InsightTimePressure(BaseModel):
    bucket: str
    sample_size: int
    avg_cpl: float
    blunder_rate: float
