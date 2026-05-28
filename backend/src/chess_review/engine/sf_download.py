"""Auto-download the optimal Stockfish binary on first run."""

import logging
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx

from chess_review.engine.cpu_detect import detect_best_tier
from chess_review.util.paths import get_stockfish_dir, get_stockfish_path

logger = logging.getLogger(__name__)

# GitHub release tag — update when new Stockfish version ships
SF_RELEASE_TAG = "sf_18"
SF_DOWNLOAD_BASE = (
    f"https://github.com/official-stockfish/Stockfish/releases/download/{SF_RELEASE_TAG}"
)


def _download_url(tier: str) -> str:
    return f"{SF_DOWNLOAD_BASE}/stockfish-windows-x86-64-{tier}.zip"


def _sf_dir() -> Path:
    return get_stockfish_dir()


def _find_existing() -> Path | None:
    """Return an existing Stockfish exe in the app's engine cache, if any."""
    target = get_stockfish_path()
    if target.exists() and target.is_file():
        return target
    sf_dir = _sf_dir()
    for f in sf_dir.iterdir():
        if f.name.startswith("stockfish") and f.suffix == ".exe":
            return f
    return None


def _verify_binary(path: Path) -> bool:
    """Check that the binary starts and responds to UCI."""
    try:
        kwargs: dict[str, object] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            [str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs,
        )
        stdout, _ = proc.communicate(input=b"uci\nquit\n", timeout=10)
        return b"uciok" in stdout
    except Exception:
        logger.debug("Binary verification failed for %s", path, exc_info=True)
        return False


def _download_and_extract(tier: str) -> Path | None:
    """Download a Stockfish zip for the given tier and extract the exe."""
    url = _download_url(tier)
    sf_dir = _sf_dir()
    logger.info("Downloading Stockfish (%s) from %s", tier, url)

    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)

        with zipfile.ZipFile(tmp_path) as zf:
            # Find the stockfish exe inside the zip
            exe_names = [n for n in zf.namelist() if n.endswith(".exe")]
            if not exe_names:
                logger.error("No .exe found in downloaded zip")
                return None

            # Extract to stockfish dir
            for name in exe_names:
                data = zf.read(name)
                # Use just the filename, not any subdirectory path
                out_path = sf_dir / Path(name).name
                out_path.write_bytes(data)
                logger.info("Extracted %s (%d MB)", out_path.name, len(data) // (1024 * 1024))
                return out_path

    except httpx.HTTPStatusError as e:
        logger.warning("Download failed for tier %s: HTTP %d", tier, e.response.status_code)
        return None
    except Exception:
        logger.exception("Download failed for tier %s", tier)
        return None
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    return None


async def ensure_stockfish() -> Path | None:
    """Ensure a working Stockfish binary exists. Downloads if needed.

    Returns the path to the binary, or None if unavailable.
    """
    # Check if already present
    existing = _find_existing()
    if existing and _verify_binary(existing):
        logger.info("Using existing Stockfish: %s", existing)
        return existing

    # Detect best CPU tier
    tier = detect_best_tier()
    logger.info("Detected best Stockfish tier: %s", tier)

    # Try downloading the detected tier
    path = _download_and_extract(tier)
    if path and _verify_binary(path):
        logger.info("Stockfish %s verified OK", tier)
        return path

    # If detected tier failed, remove it and try x86-64 as fallback
    if path:
        path.unlink(missing_ok=True)

    if tier != "x86-64":
        logger.warning("Tier %s failed verification, falling back to x86-64", tier)
        path = _download_and_extract("x86-64")
        if path and _verify_binary(path):
            logger.info("Stockfish x86-64 fallback verified OK")
            return path
        if path:
            path.unlink(missing_ok=True)

    logger.error("Could not obtain a working Stockfish binary")
    return None
