"""Build script: compiles frontend, then packages with PyInstaller."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f">>> {' '.join(cmd)}")
    # shell=True on Windows so npm.cmd / npx.cmd resolve via PATHEXT.
    subprocess.check_call(cmd, cwd=cwd, shell=sys.platform == "win32")


def main() -> None:
    frontend = ROOT / "frontend"
    dist = frontend / "dist"

    # 1. Build frontend
    print("\n=== Building frontend ===")
    run(["npm", "ci"], cwd=frontend)
    run(["npm", "run", "build"], cwd=frontend)
    if not (dist / "index.html").exists():
        print("ERROR: frontend build did not produce dist/index.html")
        sys.exit(1)

    # 2. PyInstaller
    print("\n=== Running PyInstaller ===")
    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        str(ROOT / "chess_review.spec"),
    ], cwd=ROOT)

    # Stockfish is auto-downloaded by sf_download.py on first launch into
    # %LOCALAPPDATA%/ChessReview/engine/ (CPU-tier-matched build, ~30 MB).
    # We don't bundle it — that kept the repo / .exe ~80 MB lighter and
    # avoided the source-vs-output stockfish/ folder duplication.

    print("\n=== Build complete ===")
    print(f"Distribution at: {ROOT / 'dist'}")


if __name__ == "__main__":
    main()
