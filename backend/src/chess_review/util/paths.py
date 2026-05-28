"""PyInstaller-aware path resolution."""

import os
import sys
from pathlib import Path

_APP_NAME = "ChessReview"


def get_base_dir() -> Path:
    """Return the base directory of the application.

    PyInstaller bundle: directory containing the exe.
    Development: repository root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[4]


def get_app_data_dir() -> Path:
    """Return the persistent app data directory.

    Always ``%LOCALAPPDATA%/ChessReview`` (or ``~/AppData/Local/ChessReview``
    if ``LOCALAPPDATA`` is unset). Dev mode (``uvicorn`` un-frozen) and the
    packaged ``.exe`` share the same directory by design — switching between
    them should not change which database, log, or downloaded engine you're
    looking at.
    """
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    d = base / _APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_stockfish_dir() -> Path:
    """Directory where auto-downloaded Stockfish binaries live."""
    d = get_app_data_dir() / "engine"
    d.mkdir(exist_ok=True)
    return d


def _find_stockfish_in(dir_: Path) -> Path | None:
    if not dir_.exists():
        return None
    for f in dir_.iterdir():
        if f.name.startswith("stockfish") and f.suffix == ".exe":
            return f
    return None


def get_stockfish_path() -> Path:
    """Locate the Stockfish binary.

    Only looks at ``%LOCALAPPDATA%/ChessReview/engine/`` — where the auto
    downloader caches a CPU-tier-matched build on first launch. If nothing
    is cached yet, returns the target path so the downloader knows where
    to put it.
    """
    sf_dir = get_stockfish_dir()
    found = _find_stockfish_in(sf_dir)
    if found is not None:
        return found
    return sf_dir / "stockfish.exe"


def get_db_path() -> Path:
    return get_app_data_dir() / "chess_review.db"


def get_static_dir() -> Path:
    """Return path to the built React frontend assets."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "static"  # type: ignore[attr-defined]
    return get_base_dir() / "frontend" / "dist"
