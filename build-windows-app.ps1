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

# --- Install PyQt6 WebEngine ---
# pythonw.exe suppresses the console window when launching the Qt wrapper.
# PyQt6-WebEngine downloads ~250 MB Chromium binary on first install.
Write-Host "Installing PyQt6 WebEngine (~250 MB on first run)..."
& $pip install --quiet PyQt6 PyQt6-WebEngine PyQt6-sip

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
# Shortcuts require .ico format. Convert from SVG if Inkscape/ImageMagick available;
# otherwise skip (shortcut uses pythonw.exe default icon).
$icoPath = Join-Path $RepoDir "assets\odysseus.ico"
if (-not (Test-Path $icoPath)) {
    $svgPath = Join-Path $RepoDir "assets\odysseus.svg"
    if ((Test-Path $svgPath) -and (Get-Command "inkscape" -ErrorAction SilentlyContinue)) {
        Write-Host "Converting SVG icon to ICO via Inkscape..."
        $pngTmp = Join-Path $env:TEMP "odysseus_512.png"
        inkscape --export-type=png --export-filename=$pngTmp --export-width=256 $svgPath 2>$null
        if (Get-Command "magick" -ErrorAction SilentlyContinue) {
            magick $pngTmp -define icon:auto-resize="256,128,64,48,32,16" $icoPath 2>$null
        }
    }
    if (-not (Test-Path $icoPath)) {
        Write-Warning "No .ico found at $icoPath — shortcut will use default Python icon."
        $icoPath = $null
    }
}

# --- Create shortcuts via WScript.Shell ---
$shell = New-Object -ComObject WScript.Shell

function New-OdysseusShortcut {
    param([string]$ShortcutPath)
    $sc = $shell.CreateShortcut($ShortcutPath)
    $sc.TargetPath       = $pythonw           # pythonw suppresses the console window
    $sc.Arguments        = "`"$wrapper`""
    $sc.WorkingDirectory = $RepoDir
    $sc.Description      = "Personal AI Workspace"
    if ($icoPath) { $sc.IconLocation = $icoPath }
    $sc.Save()
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
Write-Host "Logs: $env:APPDATA\Odysseus\logs\"
