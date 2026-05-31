; Inno Setup script for Chess Review.
;
; Wraps the PyInstaller ONE-DIR output (dist\chess-review\ = chess-review.exe +
; _internal\) into a single per-user installer, so users download one
; ChessReview-Setup-vX.Y.Z.exe instead of a loose folder. One-dir is kept for
; fast startup; the installer hides the _internal\ folder inside the install dir.
;
; Version is injected by build.py / CI:  ISCC /DAppVersion=1.1.4 chess-review.iss

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
; Stable AppId — the upgrade key. NEVER change this once shipped.
AppId={{B7E1F3A2-9C4D-4E6B-8A1F-2D5C7E0A9B34}
AppName=Chess Review
AppVerName=Chess Review {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=Chess Review
; Per-user install, no admin/UAC prompt (same model as the VS Code user setup).
DefaultDirName={localappdata}\Programs\ChessReview
DefaultGroupName=Chess Review
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; On upgrade, close a running instance (freeing locked files) via the Windows
; Restart Manager. We deliberately do NOT use RestartApplications to reopen it:
; RM-driven restart proved unreliable after a /SILENT self-update (the app
; closed but never came back). Instead the [Run] section relaunches the app
; explicitly in silent mode (skipifnotsilent), which is deterministic.
; See backend/src/chess_review/updater.py.
CloseApplications=yes
RestartApplications=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir=..\dist
OutputBaseFilename=ChessReview-Setup-v{#AppVersion}
; No SetupIconFile: repo has no .ico and the exe is built icon=None.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[InstallDelete]
; Wipe the bundled payload before copying the new build. PyInstaller's
; _internal\ contents change between versions (notably the
; chess_review-X.Y.Z.dist-info that importlib.metadata reads for the app
; version), and Inno does not prune files that disappeared between versions —
; so without this, stale files accumulate and two dist-info folders make the
; version lookup ambiguous. User data lives in %LOCALAPPDATA%\ChessReview\, not
; here, so wiping {app}\_internal is safe.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; Pull the entire one-dir output recursively: chess-review.exe + _internal\.
Source: "..\dist\chess-review\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Chess Review";           Filename: "{app}\chess-review.exe"
Name: "{userdesktop}\Chess Review";     Filename: "{app}\chess-review.exe"; Tasks: desktopicon
Name: "{group}\Uninstall Chess Review"; Filename: "{uninstallexe}"

[Run]
; Wizard install: optional "Launch Chess Review" checkbox on the Finished page.
Filename: "{app}\chess-review.exe"; Description: "Launch Chess Review"; Flags: nowait postinstall skipifsilent
; Silent self-update: no Finished page exists to offer a checkbox, so relaunch
; the (just-closed) app explicitly. Runs ONLY in silent mode — the wizard case
; is handled by the entry above, so there's no double launch.
Filename: "{app}\chess-review.exe"; Flags: nowait skipifnotsilent

; NOTE: deliberately NO [UninstallDelete] for user data — %LOCALAPPDATA%\ChessReview\
; (DB, log, downloaded Stockfish, WebView2 profile) is left intact on uninstall.
