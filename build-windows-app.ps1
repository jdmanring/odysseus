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

# The shortcut must carry the same AppUserModelID the wrapper sets via
# SetCurrentProcessExplicitAppUserModelID (windows_wrapper.py), or Windows
# treats the pinned shortcut and the running window as two different apps
# and shows two taskbar icons instead of reusing the pin. WScript.Shell
# cannot write that property; it lives in the .lnk's property store
# (PKEY_AppUserModel_ID = {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, 5).
$AppUserModelID = "Odysseus.Odysseus"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

[StructLayout(LayoutKind.Sequential, Pack = 4)]
public struct PropertyKey {
    public Guid fmtid; public uint pid;
    public PropertyKey(Guid f, uint p) { fmtid = f; pid = p; }
}

[StructLayout(LayoutKind.Explicit)]
public struct PropVariant {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr pointerValue;
}

[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore {
    void GetCount(out uint count);
    void GetAt(uint iProp, out PropertyKey pkey);
    void GetValue(ref PropertyKey key, out PropVariant pv);
    void SetValue(ref PropertyKey key, ref PropVariant pv);
    void Commit();
}

public static class LnkAumid {
    static readonly PropertyKey PKEY_AppUserModel_ID =
        new PropertyKey(new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), 5);

    public static void Set(string lnkPath, string aumid) {
        var link = (IPersistFile)Activator.CreateInstance(
            Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046")));
        link.Load(lnkPath, 2 /* STGM_READWRITE */);
        var store = (IPropertyStore)link;
        var key = PKEY_AppUserModel_ID;
        var pv = new PropVariant { vt = 31 /* VT_LPWSTR */,
                                   pointerValue = Marshal.StringToCoTaskMemUni(aumid) };
        try {
            store.SetValue(ref key, ref pv);
            store.Commit();
        } finally { Marshal.FreeCoTaskMem(pv.pointerValue); }
        link.Save(lnkPath, true);
    }
}
"@

function New-OdysseusShortcut {
    param([string]$ShortcutPath)
    $sc = $shell.CreateShortcut($ShortcutPath)
    $sc.TargetPath       = $pythonw           # pythonw suppresses the console window
    $sc.Arguments        = "`"$wrapper`""
    $sc.WorkingDirectory = $RepoDir
    $sc.Description      = "Personal AI Workspace"
    if ($icoPath) { $sc.IconLocation = $icoPath }
    $sc.Save()
    [LnkAumid]::Set($ShortcutPath, $AppUserModelID)
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
