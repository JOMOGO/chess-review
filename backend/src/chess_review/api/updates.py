"""Update-check and self-update endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from chess_review import updater
from chess_review.schemas import UpdateCheckResponse, UpdateInstallResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/update-check", response_model=UpdateCheckResponse)
async def update_check(force: bool = False) -> UpdateCheckResponse:
    """Report whether a newer release is available on GitHub."""
    info = await updater.check_for_update(force=force)
    return UpdateCheckResponse(
        current=info.current,
        latest=info.latest,
        update_available=info.update_available,
        release_url=info.release_url,
        download_url=info.download_url,
        can_self_install=updater.is_frozen() and bool(info.download_url),
    )


@router.post("/update/install", response_model=UpdateInstallResponse)
async def update_install() -> UpdateInstallResponse:
    """Download the latest installer and launch it to upgrade in place.

    Only works in the packaged app; in dev (or if the release has no installer
    asset) it returns ``started=False`` with the URLs so the UI can open the
    download page instead.
    """
    info = await updater.check_for_update(force=True)
    if not info.update_available:
        raise HTTPException(status_code=409, detail="Already on the latest version")

    if not (updater.is_frozen() and info.download_url):
        return UpdateInstallResponse(
            started=False,
            download_url=info.download_url,
            release_url=info.release_url,
            detail=(
                "Self-install is only available in the installed app — "
                "open the download page to update."
            ),
        )

    try:
        await updater.download_and_launch_installer(info)
    except Exception as exc:
        logger.exception("Self-update failed")
        raise HTTPException(status_code=500, detail=f"Update failed: {exc}") from exc

    return UpdateInstallResponse(
        started=True,
        download_url=info.download_url,
        release_url=info.release_url,
        detail="Installer launched — the app will close and reopen on the new version.",
    )
