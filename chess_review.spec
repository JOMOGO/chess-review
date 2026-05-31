# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import copy_metadata

block_cipher = None
base_dir = os.path.abspath('.')

a = Analysis(
    [os.path.join(base_dir, 'backend', 'src', 'chess_review', 'entry.py')],
    pathex=[os.path.join(base_dir, 'backend', 'src')],
    binaries=[],
    datas=[
        (os.path.join(base_dir, 'frontend', 'dist'), 'static'),
    # Ship the package dist-info so importlib.metadata.version('chess-review')
    # resolves at runtime — that's how util/version.py reports the app version
    # (and powers the in-app update check).
    ] + copy_metadata('chess-review'),
    hiddenimports=[
        'aiosqlite',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.sqlite.aiosqlite',
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        'chess',
        'chess.engine',
        'chess.pgn',
        'httpx',
        'httpx._transports.default',
        'httpcore',
        'h11',
        'anyio',
        'anyio._backends._asyncio',
        'sniffio',
        'certifi',
        'email.mime.multipart',
        'email.mime.text',
        'multipart',
        'webview',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
        'bottle',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'PIL'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# One-dir build: the exe stays small and does NOT self-extract to a temp dir
# on every launch (the one-file behaviour that made cold starts take minutes
# while Windows Defender re-scanned the unpacked bundle). Output is a folder,
# dist/chess-review/, containing chess-review.exe + an _internal/ folder; the
# two must be shipped together.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='chess-review',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='chess-review',
)
