# Implementation Plan: Windows Native Wrapper

**Fork issue:** [#44](https://github.com/jdmanring/odysseus/issues/44)
**Branch origin:** `upstream-mirror` (upstream-candidate)
**Branch name:** `feat/qt-native-windows-app`
**Depends on:** Issue #14 / `feat/qt-native-linux-app` merged upstream first (shared JS bridge files)

---

## Overview

Create `windows_wrapper.py` and `build-windows-app.ps1`: a native Windows desktop
wrapper using PyQt6, modeled on `qt_wrapper.py`. The core architecture is identical;
Windows requires different subprocess management, signal handling, fd redirection, GPU
flags, and path conventions.

---

## Files to Create

### `windows_wrapper.py`

Start from `qt_wrapper.py` and apply the following changes:

**1. LOG_DIR**: change log location to Windows AppData convention:
```python
_appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
LOG_DIR = os.path.join(_appdata, "Odysseus", "logs")
```

**2. Remove `os.dup2` fd redirect block**: Windows Chromium renderer subprocesses
do not inherit fd 1/2 via `os.dup2` reliably. Replace with a log file opened for
`sys.stdout`/`sys.stderr` only:
```python
os.makedirs(LOG_DIR, exist_ok=True)
_log_file = open(os.path.join(LOG_DIR, "wrapper_system.log"), "a", buffering=1)
sys.stdout = _log_file
sys.stderr = _log_file
# os.dup2 calls removed — not used on Windows
```

**3. Remove `QTWEBENGINE_FORCE_USE_GBM`**: Linux-only Qt regression guard:
```python
# Remove this line entirely:
os.environ.setdefault("QTWEBENGINE_FORCE_USE_GBM", "0")
```

**4. Chromium flags**: replace with Windows/ANGLE flags:
```python
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--ignore-gpu-blocklist "
    "--enable-gpu-rasterization "
    "--use-angle=d3d11 "            # force ANGLE DirectX 11 backend
    "--enable-features=WebGPU,SharedArrayBuffer "
    "--enable-logging=stderr --log-level=1 "
    "--remote-debugging-port=9222"
)
```
Flags removed vs Linux: `--no-sandbox`, all Vulkan/GBM guards.

**5. Imports**: remove D-Bus, add `ctypes` for Windows process management:
```python
# Remove:
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
# Add (at the top with other stdlib imports):
import ctypes
```

**6. PORT default**: 7000 (no AirPlay conflict on Windows):
```python
PORT = os.environ.get("APP_PORT", "7000")
```

**7. VENV_PYTHON**: Windows venv uses `Scripts\python.exe`, not `bin/python`:
```python
VENV_PYTHON = os.path.join(INSTALL_DIR, "venv", "Scripts", "python.exe")
```

**8. `kill_zombies()`**: replace `pkill` with Windows `taskkill`:
```python
def kill_zombies():
    subprocess.run(
        ["taskkill", "/F", "/FI", f"WINDOWTITLE eq {_UVICORN_PATTERN}"],
        check=False, capture_output=True
    )
    # Also kill by command line match via WMIC if taskkill misses it:
    subprocess.run(
        ["wmic", "process", "where",
         f"CommandLine like '%{_UVICORN_PATTERN}%'", "delete"],
        check=False, capture_output=True
    )
```

**9. Signal handling**: `SIGTERM` is not supported on Windows. Use only `SIGINT`:
```python
signal.signal(signal.SIGINT, _signal_handler)
# SIGTERM: not available on Windows — omit
# SIGBREAK (Ctrl+Break): optional addition for Windows console users:
try:
    signal.signal(signal.SIGBREAK, _signal_handler)
except AttributeError:
    pass  # SIGBREAK only exists on Windows; AttributeError on Linux/macOS
```

**10. NativeBridge**: replace D-Bus portal with direct `QColorDialog`:
```python
class NativeBridge(QObject):
    colorPicked = pyqtSignal(str)

    @pyqtSlot()
    def openColorPicker(self):
        color = QColorDialog.getColor()
        self.colorPicked.emit(color.name() if color.isValid() else '')
```

**11. `_log_renderer_memory()`**: replace `pgrep` with Windows `tasklist`:
```python
def _log_renderer_memory():
    try:
        import subprocess as _sp
        r = _sp.run(
            ["tasklist", "/FI", "IMAGENAME eq QtWebEngineProcess.exe", "/FO", "CSV"],
            capture_output=True, text=True
        )
        for line in r.stdout.strip().splitlines()[1:]:  # skip header
            parts = line.strip('"').split('","')
            if len(parts) >= 5:
                pid_s, mem_s = parts[1], parts[4]
                print(f'[MEM] pid={pid_s} WorkingSet={mem_s}', flush=True)
    except Exception as e:
        print(f'[MEM] error: {e}', flush=True)
```

**12. `app.setDesktopFileName()`**: not available on Windows. Replace with:
```python
app.setApplicationName("Odysseus")
app.setOrganizationName("Odysseus")
```

**13. QSettings**: no change. Qt automatically writes to the Windows Registry under
`HKCU\Software\Odysseus\odysseus` when using `QSettings("odysseus", "odysseus")`.

### `build-windows-app.ps1`

```powershell
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m venv venv
.\venv\Scripts\pip install --quiet PyQt6 PyQt6-WebEngine PyQt6-sip

& .\venv\Scripts\python.exe windows_wrapper.py @args
```

---

## Files Already Present (no changes needed)

These were added by `feat/qt-native-linux-app` and work on Windows without modification:

- `static/js/qt-bridge.js`: the `window.__QT_WRAPPER__` guard is platform-neutral
- `static/index.html`: the `<script>` injection is platform-neutral
- `static/js/colorPicker.js`: the `window.qtBridge.openColorPicker()` call is neutral

---

## Implementation Steps

1. `git checkout upstream-mirror && git checkout -b feat/qt-native-windows-app`
2. Create `windows_wrapper.py` per the spec above
3. Create `build-windows-app.ps1`
4. Run `.\build-windows-app.ps1` on a Windows machine; verify the window appears
5. Test: login state persists; external links open in system browser; color picker
   opens `QColorDialog`; window size/maximized state restores
6. Verify port: confirm Task Manager or `netstat -an` shows uvicorn on port 7000
7. Verify logs appear in `%APPDATA%\Odysseus\logs\`
8. Test zombie cleanup: kill the uvicorn process manually, relaunch; confirm no
   "port already in use" error
9. Screenshot the running app for the PR
10. Write PR draft at `docs/fork/upstream/pr-drafts/feat-qt-native-windows-app.md`
    (model it on `feat-qt-native-linux-app.md`; reference issue #44 and upstream #3528)
11. Cherry-pick to `develop`; mark issue #44 in-progress

---

## Windows-Specific Risk Areas

**`taskkill` zombie cleanup:** The WMIC approach is deprecated in recent Windows builds.
If WMIC is unavailable, fall back to iterating `psutil.process_iter()`, but that adds
a dependency. Try `taskkill` + WMIC first; if both fail, leave zombie cleanup as best-effort
(the Popen handle approach in `stop_server()` already terminates the tracked process).

**DirectX/ANGLE flags:** `--use-angle=d3d11` is the most compatible choice for Windows
10/11. If hardware is old or drivers are broken, `--use-angle=d3d9` is the fallback.
Test on at least one AMD and one Intel GPU, not only NVIDIA.

**PyQt6 on Windows:** Available via pip; no system dependency. However, PyQt6-WebEngine
downloads a large Chromium binary (~250 MB) on first install. `build-windows-app.ps1`
should note the expected download size so users aren't surprised.

**Code signing:** Windows Defender SmartScreen will warn on unsigned `.exe` files.
For initial PR, the `.ps1` launch script is sufficient (PowerShell scripts don't trigger
SmartScreen the same way). Distribution packaging with PyInstaller + signing is a
follow-up.

---

## Testing Checklist

- [ ] App launches; Odysseus UI loads in a native Windows window
- [ ] Server starts on port 7000; `netstat -an | findstr 7000` confirms
- [ ] Login persists after closing and reopening
- [ ] External link opens in system browser (Edge/Chrome), not inside the wrapper
- [ ] Color picker opens `QColorDialog` (no crash, no silent fail)
- [ ] Window size and maximized state restore correctly on reopen
- [ ] Chrome DevTools available at `http://localhost:9222`
- [ ] Logs appear in `%APPDATA%\Odysseus\logs\`
- [ ] Taskbar groups correctly; shows Odysseus icon (not Python icon)
- [ ] `build-windows-app.ps1` runs cleanly from a fresh clone
- [ ] Killing uvicorn externally and relaunching doesn't leave a zombie port

---

## PR Filing Notes

- Depends on `feat/qt-native-linux-app` (issue #14) being merged upstream first.
  If filing before #14 merges: include the shared JS files and note the dependency.
- Reference upstream issue #3528 (Windows desktop wrapper) and issue #606
  (standalone native app) and PR #3310 (Electron wrapper) as prior art.
  In the PR description, explain why Qt WebEngine is preferable to Electron:
  same Chromium engine, 35-50% less RAM (180 MB vs 400 MB measured on
  constrained hardware), no bundled Node.js runtime, direct Python integration,
  and full server lifecycle management (PR #3310 requires the server to already
  be running; this wrapper starts and manages it).
- Must be tested on real Windows hardware before filing. Wine/VM testing is not
  sufficient for validating GPU flags and window management.
- Note in the PR that `build-windows-app.ps1` requires PowerShell execution policy
  to allow local scripts: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
