#Requires -Version 5.1
# ==============================================================================
# setup.ps1 — one-command from-scratch setup for Windows.
#
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# The Windows counterpart of setup.sh (Linux/*BSD) and start-macos.sh (macOS):
# a fresh checkout goes to an installed app in one command. It:
#   1. checks for Python 3.11+ (guides you to install it if missing),
#   2. builds the venv, installs requirements.txt, and installs PyQt6/WebEngine
#      (via install.bat -> build-windows-app.ps1),
#   3. creates the Start Menu + Desktop shortcuts,
#   4. runs first-run setup (data dirs + initial admin password).
#
# Unlike Linux/*BSD, Windows uses pip-installed PyQt6 inside the venv (a single
# interpreter) — there is no system Qt to lean on — so no privileged step is
# needed once Python is present.
# ==============================================================================
$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoDir

Write-Host "==> Odysseus setup (Windows)"

# 1. Python 3.11+. The Microsoft Store 'python' alias is a stub that exits 9009
#    with an ad, so verify a real interpreter reports a version we accept.
function Get-Python311 {
    foreach ($cmd in @("python", "py -3.13", "py -3.12", "py -3.11", "py -3")) {
        try {
            $parts = $cmd.Split(" ")
            $ver = & $parts[0] $parts[1..($parts.Length - 1)] -c `
                "import sys; print('%d.%d' % sys.version_info[:2]) if sys.version_info[:2] >= (3,11) else sys.exit(1)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) { return $cmd }
        } catch { }
    }
    return $null
}
$py = Get-Python311
if (-not $py) {
    Write-Host ""
    Write-Warning "Python 3.11+ was not found."
    Write-Host "  Install it, then re-run this script:"
    Write-Host "    winget install Python.Python.3.12"
    Write-Host "  (or download from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH')"
    exit 1
}
Write-Host "   ok Python: $py"

# 2 + 3. Build the venv, install requirements + PyQt6, create shortcuts. This is
#        exactly what a normal install does, so we reuse it rather than duplicate.
Write-Host "==> Building the app (venv, requirements, PyQt6, shortcuts)..."
& "$RepoDir\install.bat"
if ($LASTEXITCODE -ne 0) { Write-Error "install.bat failed (exit $LASTEXITCODE)"; exit 1 }

# 4. First-run setup (data dirs + initial admin password; idempotent).
$venvPy = Join-Path $RepoDir "venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    Write-Host "==> Preparing Odysseus..."
    $env:ODYSSEUS_SKIP_RUN_HINT = "1"
    & $venvPy "$RepoDir\setup.py"
}

Write-Host ""
Write-Host "Done. Launch Odysseus from the Start Menu or the Desktop shortcut."
