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

    Windows: %LOCALAPPDATA%/ChessReview
    Dev mode: <repo>/data
    """
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        d = base / _APP_NAME
    else:
        d = get_base_dir() / "data"
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

    Lookup order:
      1. ``<exe-dir>/stockfish/`` — the binary shipped next to the .exe by
         ``build.py``. Avoids re-downloading on first run.
      2. ``%LOCALAPPDATA%/ChessReview/engine/`` — where the auto-downloader
         caches a CPU-tier-matched build.

    If neither has a binary yet, returns the auto-download target path so the
    downloader knows where to put it.
    """
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "stockfish"
        found = _find_stockfish_in(bundled)
        if found is not None:
            return found

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
