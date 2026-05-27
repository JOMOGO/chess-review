"""Application entry point. Launches native window with embedded backend."""

import os
import socket
import threading
import time

import httpx
import uvicorn

from chess_review.main import app  # direct import — works in frozen exe
from chess_review.util.paths import get_app_data_dir


def _pin_webview2_user_data_dir() -> None:
    """Make WebView2 store its profile under %LOCALAPPDATA%/ChessReview/webview/.

    Without this, Edge WebView2 keeps its user-data folder next to the .exe
    (``<dist>/EBWebView``). Every clean rebuild wipes ``dist/``, which wipes
    that folder — so localStorage (saved player, theme, etc.) is lost on
    every new build. Pinning the folder to app-data keeps it across rebuilds.

    Must run BEFORE ``import webview`` because pywebview reads the env var
    when the WebView2 control initialises.
    """
    if "WEBVIEW2_USER_DATA_FOLDER" not in os.environ:
        webview_dir = get_app_data_dir() / "webview"
        webview_dir.mkdir(parents=True, exist_ok=True)
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(webview_dir)


_pin_webview2_user_data_dir()

import webview  # noqa: E402 — must be imported after env var is set


def _find_free_port() -> int:
    """Pick a port, preferring ``settings.port`` so localStorage persists.

    WebView2 keys ``localStorage`` per origin, and the origin includes the
    port — so a random port on every launch gives every launch a different
    origin and an empty ``localStorage`` (no stored player, no theme, no
    nothing). Sticking to a fixed port keeps the origin stable across
    launches. Fall back to an OS-assigned free port if the configured one
    is genuinely busy (another instance already running, or another app
    holding it).
    """
    from chess_review.config import settings

    preferred = settings.port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", preferred))
        return preferred
    except OSError:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 30.0) -> bool:
    """Poll the health endpoint until the server is up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url}/api/health", timeout=2.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main() -> None:
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    server = uvicorn.Server(
        uvicorn.Config(
            app,  # pass app object directly
            host="127.0.0.1",
            port=port,
            log_level="info",
        )
    )

    # Run uvicorn in a background thread
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be fully ready (DB, Stockfish pool, etc.)
    if not _wait_for_server(url):
        print("Server failed to start within 30 seconds")
        return

    # Open native window
    window = webview.create_window(
        "Chess Review",
        url,
        width=1280,
        height=860,
        min_size=(900, 600),
    )
    webview.start(private_mode=False)

    # Window closed — shut down server
    server.should_exit = True
    thread.join(timeout=5)


if __name__ == "__main__":
    main()
