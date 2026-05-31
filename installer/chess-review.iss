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
; Detect a running instance / locked files on upgrade and offer to close them.
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

[Files]
; Pull the entire one-dir output recursively: chess-review.exe + _internal\.
Source: "..\dist\chess-review\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Chess Review";           Filename: "{app}\chess-review.exe"
Name: "{userdesktop}\Chess Review";     Filename: "{app}\chess-review.exe"; Tasks: desktopicon
Name: "{group}\Uninstall Chess Review"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\chess-review.exe"; Description: "Launch Chess Review"; Flags: nowait postinstall skipifsilent

; NOTE: deliberately NO [UninstallDelete] for user data — %LOCALAPPDATA%\ChessReview\
; (DB, log, downloaded Stockfish, WebView2 profile) is left intact on uninstall.
