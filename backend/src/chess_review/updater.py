"""In-app update support.

Two jobs:
  * :func:`check_for_update` — ask GitHub for the latest release and compare it
    to the running version. Cached so the app can poll cheaply on open.
  * :func:`download_and_launch_installer` — download that release's Inno Setup
    installer and launch it silently. The installer (``CloseApplications`` +
    ``RestartApplications`` in ``installer/chess-review.iss``) uses the Windows
    Restart Manager to close this running ``.exe``, upgrade in place, and
    relaunch it — so the user gets a seamless self-update.

Self-install only makes sense in the packaged app (``sys.frozen``). In dev the
caller should fall back to opening the release page in a browser.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from chess_review.util.paths import get_app_data_dir
from chess_review.util.version import get_version

logger = logging.getLogger(__name__)

GITHUB_REPO = "JOMOGO/chess-review"
_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
# Installer assets are named ChessReview-Setup-vX.Y.Z.exe (see build.py / .iss).
_INSTALLER_PREFIX = "ChessReview-Setup-v"
_CACHE_TTL_S = 6 * 3600.0
# Windows: don't flash a console window when spawning the installer.
_CREATE_NO_WINDOW = 0x08000000


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    latest: str | None
    update_available: bool
    release_url: str | None
    download_url: str | None
    asset_name: str | None


def is_frozen() -> bool:
    """True when running as the packaged PyInstaller ``.exe``."""
    return bool(getattr(sys, "frozen", False))


def _version_key(v: str) -> tuple[int, ...]:
    """Lenient numeric key for comparison. ``"v2.10.0"`` -> ``(2, 10, 0)``.

    Pre-release / build suffixes (``-rc1``, ``+build``) are dropped, so a
    pre-release sorts equal to its final — fine for a coarse "is something
    newer out?" check.
    """
    core = v.strip().lstrip("vV").split("-", 1)[0].split("+", 1)[0]
    parts: list[int] = []
    for chunk in core.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    return tuple(parts) or (0,)


def _is_newer(latest: str, current: str) -> bool:
    return _version_key(latest) > _version_key(current)


_cache: tuple[float, UpdateInfo] | None = None


async def check_for_update(*, force: bool = False) -> UpdateInfo:
    """Return update info, comparing the running version to the latest release.

    Result is cached for ``_CACHE_TTL_S`` so the UI can poll on every app open
    without hammering GitHub's (unauthenticated, rate-limited) API.
    """
    global _cache
    current = get_version()
    if not force and _cache is not None:
        ts, info = _cache
        if time.monotonic() - ts < _CACHE_TTL_S and info.current == current:
            return info
    info = await _fetch_latest(current)
    _cache = (time.monotonic(), info)
    return info


async def _fetch_latest(current: str) -> UpdateInfo:
    none = UpdateInfo(current, None, False, None, None, None)
    try:
        async with httpx.AsyncClient(
            timeout=8.0, headers={"User-Agent": "chess-review"}
        ) as client:
            resp = await client.get(
                _LATEST_URL, headers={"Accept": "application/vnd.github+json"}
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        # Offline, rate-limited, or no releases yet — not an error worth
        # surfacing; the UI just won't show an update prompt.
        logger.info("Update check skipped (network/API issue)", exc_info=True)
        return none

    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        return none

    download_url: str | None = None
    asset_name: str | None = None
    for asset in data.get("assets", []) or []:
        name = str(asset.get("name", ""))
        if name.startswith(_INSTALLER_PREFIX) and name.endswith(".exe"):
            download_url = asset.get("browser_download_url")
            asset_name = name
            break

    return UpdateInfo(
        current=current,
        latest=tag,
        update_available=_is_newer(tag, current),
        release_url=data.get("html_url"),
        download_url=download_url,
        asset_name=asset_name,
    )


async def download_and_launch_installer(info: UpdateInfo) -> Path:
    """Download the release installer to app-data and launch it silently.

    Returns the path it was saved to. Raises on download failure. After the
    installer is launched it closes this process (via Restart Manager) and
    relaunches the upgraded app, so the caller should expect the app to exit
    shortly after this returns.
    """
    if not info.download_url or not info.asset_name:
        raise RuntimeError("Latest release has no installer asset to download")

    dest_dir = get_app_data_dir() / "update"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / info.asset_name
    part = dest.with_name(dest.name + ".part")

    logger.info("Downloading installer %s", info.asset_name)
    async with httpx.AsyncClient(
        timeout=None, follow_redirects=True, headers={"User-Agent": "chess-review"}
    ) as client:
        async with client.stream("GET", info.download_url) as resp:
            resp.raise_for_status()
            with part.open("wb") as f:
                async for chunk in resp.aiter_bytes(1 << 16):
                    f.write(chunk)
    part.replace(dest)
    logger.info("Installer saved to %s; launching silent upgrade", dest)

    # /SILENT shows a progress bar but no wizard pages or prompts. The .iss
    # sets CloseApplications=yes + RestartApplications=yes, so Inno's Restart
    # Manager closes this running exe, installs over it, and relaunches us.
    # /NORESTART suppresses any machine-reboot prompt (unrelated to the app
    # restart). /SUPPRESSMSGBOXES keeps it fully unattended.
    args = [str(dest), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    if sys.platform == "win32":
        subprocess.Popen(args, close_fds=True, creationflags=_CREATE_NO_WINDOW)
    else:
        subprocess.Popen(args, close_fds=True)
    return dest
