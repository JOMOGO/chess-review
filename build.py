"""Build script: compiles frontend, packages with PyInstaller, then wraps the
one-dir output in an Inno Setup installer."""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f">>> {' '.join(cmd)}")
    # shell=True on Windows so npm.cmd / npx.cmd resolve via PATHEXT.
    subprocess.check_call(cmd, cwd=cwd, shell=sys.platform == "win32")


def read_version() -> str:
    """The single source of truth for the app version (bumped by /release)."""
    with (ROOT / "backend" / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def find_iscc() -> str | None:
    """Locate the Inno Setup compiler: PATH first, then the canonical install path."""
    on_path = shutil.which("ISCC")
    if on_path:
        return on_path
    canonical = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
    return str(canonical) if canonical.exists() else None


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

    # 3. Inno Setup installer (wraps the one-dir dist/chess-review/ folder).
    version = read_version()
    iscc = find_iscc()
    if iscc is None:
        print("\n=== Inno Setup (ISCC) not found — skipping installer build ===")
        print("Install Inno Setup 6 or add ISCC to PATH to produce the installer.")
        print(f"Runnable one-dir build at: {ROOT / 'dist' / 'chess-review'}")
        return

    print("\n=== Building installer (Inno Setup) ===")
    run([
        iscc,
        f"/DAppVersion={version}",
        str(ROOT / "installer" / "chess-review.iss"),
    ])

    print("\n=== Build complete ===")
    print(f"Installer at: {ROOT / 'dist' / f'ChessReview-Setup-v{version}.exe'}")


if __name__ == "__main__":
    main()
