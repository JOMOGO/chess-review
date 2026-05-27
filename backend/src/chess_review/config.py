"""Application configuration via Pydantic settings."""

from pydantic_settings import BaseSettings

from chess_review.util.paths import get_db_path, get_stockfish_path


class Settings(BaseSettings):
    # Database
    database_url: str = ""

    # Stockfish
    stockfish_path: str = ""
    sf_workers: int = 0  # 0 = auto-detect (half of CPU cores)
    sf_hash_mb: int = 0  # 0 = auto-size per pool_size + available RAM
    sf_threads: int = 1
    inventory_depth: int = 14
    deep_depth: int = 25
    swing_threshold_cp: int = 100
    # Per-game cap on positions promoted to the deep pass purely because the
    # engine prefers a move the user didn't play (i.e. potential missed
    # tactics not caught by the eval-swing trigger). Bounded so this doesn't
    # explode on amateur games where played != best is the common case.
    missed_tactic_max_per_game: int = 6

    # Syzygy tablebases (path to folder with .rtbw/.rtbz files)
    syzygy_path: str = ""

    # Lichess cloud
    lichess_cloud_enabled: bool = True
    # Skip cloud lookups for positions past this ply (cloud coverage drops off
    # sharply after the opening; default is conservative so we don't miss hits).
    cloud_max_ply: int = 40

    # chess.com
    chesscom_user_agent: str = "chess-review/0.1"

    # Server
    host: str = "127.0.0.1"
    port: int = 18765
    dev_mode: bool = False

    model_config = {"env_prefix": "CHESS_REVIEW_", "env_file": ".env"}

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{get_db_path()}"

    def get_stockfish_path(self) -> str:
        if self.stockfish_path:
            return self.stockfish_path
        return str(get_stockfish_path())


settings = Settings()
