"""Single source of truth for the running app version.

The version is declared once in ``backend/pyproject.toml`` (bumped by
``/release``; ``build.py`` reads the same key to stamp the installer filename).
Resolving it at runtime has two cases:

* **Dev (un-frozen):** read ``pyproject.toml`` directly. An editable install's
  ``dist-info`` is written once and goes stale when the version is bumped, so
  ``importlib.metadata`` would lie — the file is the live truth.
* **Frozen ``.exe``:** ``pyproject.toml`` isn't bundled, so fall back to the
  package metadata that ``chess_review.spec`` ships via ``copy_metadata`` (a
  fresh CI install stamps it with the current version).
"""

import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

_FALLBACK = "0.0.0+unknown"


def _from_pyproject() -> str | None:
    # backend/src/chess_review/util/version.py -> backend/pyproject.toml
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        import tomllib

        with pyproject.open("rb") as f:
            value = tomllib.load(f).get("project", {}).get("version")
        return str(value) if value else None
    except Exception:
        return None


def get_version() -> str:
    """Return the running application version, e.g. ``"2.0.0"``."""
    if not getattr(sys, "frozen", False):
        from_file = _from_pyproject()
        if from_file:
            return from_file
    try:
        return _pkg_version("chess-review")
    except PackageNotFoundError:
        return _FALLBACK
