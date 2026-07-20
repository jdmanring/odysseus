#Requires -Version 5.1
# ==============================================================================
# build-windows-app.ps1
#
# Installs Odysseus as a native Windows desktop application.
# Creates Start Menu and Desktop shortcuts pointing to windows_wrapper.py.
#
# Run with:
#   powershell -ExecutionPolicy Bypass -File .\build-windows-app.ps1
#
# Or set execution policy once (no admin rights required):
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
# ==============================================================================

$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Building Odysseus native Windows app..."
Write-Host "  Repo: $RepoDir"

# --- Set up venv ---
$VenvDir  = Join-Path $RepoDir "venv"
$pip      = Join-Path $VenvDir "Scripts\pip.exe"
$pythonw  = Join-Path $VenvDir "Scripts\pythonw.exe"
$wrapper  = Join-Path $RepoDir "windows_wrapper.py"

if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    Write-Host "Creating venv..."
    python -m venv $VenvDir
}

# --- Install dependencies ---
# Server deps first (a fresh venv has no FastAPI/uvicorn, so the app cannot
# start on PyQt alone), then the desktop pieces. websocket-client backs the
# wrapper's CDP calls; pywin32 provides the property-store API used below to
# stamp the AppUserModelID onto the shortcuts.
# PyQt6-WebEngine downloads ~250 MB Chromium binary on first install.
$req = Join-Path $RepoDir "requirements.txt"
if (Test-Path $req) {
    Write-Host "Installing server dependencies (requirements.txt)..."
    & $pip install --quiet -r $req
}
Write-Host "Installing PyQt6 WebEngine (~250 MB on first run)..."
& $pip install --quiet PyQt6 PyQt6-WebEngine PyQt6-sip websocket-client pywin32

if (-not (Test-Path $pythonw)) {
    Write-Error "pythonw.exe not found at $pythonw after venv creation."
    exit 1
}

Write-Host "PyQt6 WebEngine: OK"

if (-not (Test-Path $wrapper)) {
    Write-Warning "windows_wrapper.py not found at $wrapper."
    Write-Warning "Shortcuts will be created but will not launch until the wrapper is present."
    Write-Warning "(windows_wrapper.py requires Windows hardware for testing — see docs/fork/plans/windows-wrapper-plan.md)"
}

# --- Icon (.ico) ---
# The repo ships static\icon.ico: multi-resolution (16-256px), built from the
# 512px brand icon with the artwork recentred at ~92% fill so it matches peer
# app icons on the taskbar instead of rendering undersized. The wrapper loads
# the same file for setWindowIcon, so shortcut and window stay identical.
$icoPath = Join-Path $RepoDir "static\icon.ico"
if (-not (Test-Path $icoPath)) {
    Write-Warning "No .ico found at $icoPath — shortcut will use default Python icon."
    $icoPath = $null
}

# --- Create shortcuts via WScript.Shell ---
$shell = New-Object -ComObject WScript.Shell

# The shortcut must carry the same AppUserModelID the wrapper sets via
# SetCurrentProcessExplicitAppUserModelID (windows_wrapper.py), or Windows
# treats the pinned shortcut and the running window as two different apps
# and shows two taskbar icons instead of reusing the pin. WScript.Shell
# cannot write that property; it lives in the .lnk's property store
# (PKEY_AppUserModel_ID = {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, 5).
$AppUserModelID = "Odysseus.Odysseus"

# Stamping uses pywin32's propsys (installed into the venv above) rather than
# an Add-Type C# IPropertyStore shim: the shim variant failed silently on the
# live bench (property read back unset), while the propsys route persisted and
# verified. The store handle must be released before any readback reopen.
$py = Join-Path $VenvDir "Scripts\python.exe"
$stamper = @'
import sys
import pythoncom
from win32com.propsys import propsys, pscon
GPS_READWRITE = 2
path, aumid = sys.argv[1], sys.argv[2]
store = propsys.SHGetPropertyStoreFromParsingName(
    path, None, GPS_READWRITE, propsys.IID_IPropertyStore)
store.SetValue(pscon.PKEY_AppUserModel_ID,
               propsys.PROPVARIANTType(aumid, pythoncom.VT_LPWSTR))
store.Commit()
del store
rd = propsys.SHGetPropertyStoreFromParsingName(
    path, None, 0, propsys.IID_IPropertyStore)
assert rd.GetValue(pscon.PKEY_AppUserModel_ID).GetValue() == aumid, "AUMID readback mismatch"
'@
$stamperFile = Join-Path $env:TEMP "odysseus_stamp_aumid.py"
Set-Content -Path $stamperFile -Value $stamper

function New-OdysseusShortcut {
    param([string]$ShortcutPath)
    $sc = $shell.CreateShortcut($ShortcutPath)
    $sc.TargetPath       = $pythonw           # pythonw suppresses the console window
    $sc.Arguments        = "`"$wrapper`""
    $sc.WorkingDirectory = $RepoDir
    $sc.Description      = "Personal AI Workspace"
    if ($icoPath) { $sc.IconLocation = $icoPath }
    $sc.Save()
    & $py $stamperFile $ShortcutPath $AppUserModelID
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "AppUserModelID stamp failed for $ShortcutPath — pinned-icon reuse will not work."
    }
}

# Start Menu shortcut
$startMenuPrograms = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
New-Item -ItemType Directory -Force -Path $startMenuPrograms | Out-Null
$smShortcut = Join-Path $startMenuPrograms "Odysseus.lnk"
New-OdysseusShortcut -ShortcutPath $smShortcut
Write-Host "Start Menu shortcut: $smShortcut"

# Desktop shortcut
$dtShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Odysseus.lnk"
New-OdysseusShortcut -ShortcutPath $dtShortcut
Write-Host "Desktop shortcut:    $dtShortcut"

Write-Host ""
Write-Host "Done. Launch Odysseus from the Start Menu or Desktop shortcut."
Write-Host "Logs: $(Join-Path $RepoDir 'logs')"
