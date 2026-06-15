# Implementation Plan: macOS Native Wrapper (pywebview / WKWebView)

**Fork issue:** [#43](https://github.com/jdmanring/odysseus/issues/43)
**Branch origin:** `upstream-mirror` (upstream-candidate)
**Branch name:** `feat/native-macos-app` (not `feat/qt-native-macos-app` — no Qt)
**Depends on:** Issue #14 / `feat/qt-native-linux-app` merged upstream first (shared JS bridge files)

> **Note:** Issue #43 was filed as a Qt wrapper. Update the issue title to "Native macOS wrapper (pywebview / WKWebView)" before branching.

---

## Why pywebview, not PyQt6

macOS ships WKWebView (Apple's native engine) on every machine — no installation required.
PyQt6 on macOS bundles Chromium via Qt WebEngine (a ~150 MB dependency), replicating
what the existing `build-macos-app.sh` already does by opening Chrome in `--app` mode.
pywebview with its Cocoa backend uses WKWebView directly: native browser engine, Metal
rendering, Apple codecs, smaller footprint, better battery life.

The trade-off vs the Qt wrapper: no `QWebChannel`, no `QWebEngineScript`, no crash recovery.
The bridge becomes `js_api` (Promise-based method calls). Simpler, acceptable for macOS.

---

## Architecture

| Concern | Linux (PyQt6) | macOS (pywebview) |
|---------|--------------|-------------------|
| Web engine | Chromium (Qt WebEngine) | WKWebView (Cocoa) |
| Python bridge | `QWebChannel` + signals | `js_api` + Promises |
| Script injection | `QWebEngineScript` (DocumentCreation) | `window.events.loaded` callback |
| Color picker | D-Bus portal / `QColorDialog` | `subprocess osascript` / tkinter |
| Window state | `QSettings` | JSON file |
| GPU flags | `QTWEBENGINE_CHROMIUM_FLAGS` | None needed |
| Crash recovery | `renderProcessTerminated` signal | None (WKWebView is stable) |
| Log dir | `~/.local/share/odysseus/logs/` | `~/Library/Logs/Odysseus/` |
| Port default | 7000 | 7860 (AirPlay Receiver holds 7000) |
| Server lifecycle | `subprocess.Popen` (same) | `subprocess.Popen` (same) |

---

## Files to Create

### `mac_wrapper.py`

```python
import os
import sys
import json
import signal
import subprocess
import time
import webview

LOG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Logs", "Odysseus")
os.makedirs(LOG_DIR, exist_ok=True)

_log_file = open(os.path.join(LOG_DIR, "wrapper_system.log"), "a", buffering=1)
sys.stdout = _log_file
sys.stderr = _log_file

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(INSTALL_DIR, "venv", "bin", "python")
PORT = os.environ.get("APP_PORT", "7860")
WINDOW_TITLE = "Odysseus"
STATE_FILE = os.path.expanduser("~/.config/odysseus/window_state.json")

_UVICORN_PATTERN = "uvicorn app:app"
_server_proc = None

# --- server lifecycle (same pattern as linux_wrapper.py) ---

def kill_zombies():
    result = subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)
    if result.returncode == 0:
        print("Killed stale uvicorn process(es)...")
        time.sleep(1)

def start_server():
    global _server_proc
    print(f"Starting Odysseus server on port {PORT}...")
    cmd = [VENV_PYTHON, "-m", "uvicorn", "app:app",
           "--host", "127.0.0.1", "--port", PORT, "--access-log"]
    env = os.environ.copy()
    env["ODYSSEUS_LOG_FILE"] = os.path.join(LOG_DIR, "server.log")
    _access_log = open(os.path.join(LOG_DIR, "server_access.log"), "a", buffering=1)
    _server_proc = subprocess.Popen(
        cmd, cwd=INSTALL_DIR, env=env,
        stdout=_access_log, stderr=_access_log,
        start_new_session=True,
    )
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{PORT}", timeout=1)
            print("Server ready.")
            return True
        except Exception:
            time.sleep(0.5)
    print("Server slow to start, proceeding anyway.")
    return False

def stop_server():
    global _server_proc
    if _server_proc is not None:
        try:
            _server_proc.terminate()
            _server_proc.wait(timeout=5)
        except Exception:
            try:
                _server_proc.kill()
            except Exception:
                pass
        _server_proc = None
    subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)

# --- window state (JSON, no QSettings) ---

def load_window_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_window_state(win):
    try:
        state = {
            "width": win.width,
            "height": win.height,
            "maximized": win.maximized,
        }
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"[STATE] save error: {e}")

# --- native bridge (js_api) ---

class NativeBridge:
    """Methods here are callable from JS as pywebview.api.method()."""

    def openColorPicker(self):
        try:
            result = subprocess.run(
                ["osascript", "-e", "choose color"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                # AppleScript returns e.g. "{65535, 32768, 0}" (0–65535 per channel)
                parts = result.stdout.strip().strip("{}").split(",")
                r, g, b = [round(int(p.strip()) / 65535 * 255) for p in parts]
                return "#{:02x}{:02x}{:02x}".format(r, g, b)
        except Exception as e:
            print(f"[COLOR] osascript error: {e}")
        # tkinter fallback
        try:
            import tkinter as tk
            from tkinter import colorchooser
            root = tk.Tk()
            root.withdraw()
            color = colorchooser.askcolor(title="Pick a color")
            root.destroy()
            return color[1] if color[0] else ""
        except Exception as e:
            print(f"[COLOR] tkinter error: {e}")
        return ""

    def openExternalUrl(self, url):
        subprocess.run(["open", url], check=False)
```

**Main block:**

```python
if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda sig, frame: (stop_server(), sys.exit(0)))
    signal.signal(signal.SIGINT,  lambda sig, frame: (stop_server(), sys.exit(0)))

    kill_zombies()
    start_server()

    state = load_window_state()
    bridge = NativeBridge()

    win = webview.create_window(
        WINDOW_TITLE,
        f"http://localhost:{PORT}",
        js_api=bridge,
        width=state.get("width", 1280),
        height=state.get("height", 800),
        min_size=(800, 600),
    )

    def on_loaded():
        # Post-load injection — sets wrapper flag and external link routing.
        # Not DocumentCreation, but colorPicker.js checks this on user click,
        # not at module init, so the timing is safe.
        win.evaluate_js("window.__PYWEBVIEW_WRAPPER__ = true;")

    def on_closing():
        save_window_state(win)
        stop_server()

    win.events.loaded += on_loaded
    win.events.closing += on_closing

    webview.start(
        debug=False,
        # Force Cocoa backend on macOS (WKWebView)
        # No equivalent of Chromium flags needed
    )
```

---

## Files to Modify

### `static/js/colorPicker.js`

Add a pywebview branch alongside the existing Qt branch. The current code calls
`qtBridge.openColorPicker()` which triggers a signal. The pywebview equivalent returns
a Promise:

```javascript
// After the existing Qt block:
} else if (typeof pywebview !== 'undefined' && window.__PYWEBVIEW_WRAPPER__) {
    pywebview.api.openColorPicker().then(color => {
        if (color) applyColor(color);
    });
}
```

The exact diff depends on how `colorPicker.js` is structured after `feat/qt-native-linux-app`.
Read the file before implementing.

---

## Files Already Present (no changes needed)

- `static/index.html` — `<script>` injection added by `feat/qt-native-linux-app` is platform-neutral
- Server lifecycle pattern — reused unchanged from `linux_wrapper.py`

---

## Dependencies

pywebview on macOS uses its Cocoa backend (WKWebView) by default. Dependencies installed
via pip:

```
pywebview>=4.3
```

pywebview automatically installs `pyobjc-core`, `pyobjc-framework-WebKit`, and
`pyobjc-framework-Cocoa` on macOS. No system packages needed.

---

### `build-mac-app.sh`

Separate from the existing `build-macos-app.sh` (which builds a Chrome-based .app bundle).
This new script sets up pywebview and creates a simple launcher:

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -f venv/bin/python ]; then
    echo "ERROR: venv not found. Run setup first." >&2
    exit 1
fi

echo "Installing macOS wrapper dependencies..."
venv/bin/pip install --quiet "pywebview>=4.3"

echo "Done. Run with:  venv/bin/python mac_wrapper.py"
```

> **Note:** The existing `build-macos-app.sh` builds a Chrome-based .app bundle. This
> new script is a lighter native alternative. Both can coexist; the PR description
> should explain the distinction.

---

## Implementation Steps

1. Update issue #43 title to "Native macOS wrapper (pywebview / WKWebView)"
2. `git checkout upstream-mirror && git checkout -b feat/native-macos-app`
3. Create `mac_wrapper.py` per the spec above
4. Create `build-mac-app.sh` and `chmod +x build-mac-app.sh`
5. Modify `static/js/colorPicker.js` to add pywebview branch
6. Run `bash build-mac-app.sh` then `python mac_wrapper.py` on a macOS machine
7. Test checklist below
8. Screenshot the running app (WKWebView window)
9. Write PR draft at `docs/fork/upstream/pr-drafts/feat-native-macos-app.md`
10. Cherry-pick to `develop`; mark issue #43 in-progress

---

## Testing Checklist

- [ ] App launches; Odysseus UI loads in a native macOS window (not a browser tab)
- [ ] Server starts on port 7860; no conflict with AirPlay Receiver
- [ ] Login persists after closing and reopening
- [ ] External link calls `openExternalUrl()` → opens in system browser
- [ ] Color picker: `osascript choose color` dialog appears; color applied correctly
- [ ] Color picker tkinter fallback: test by temporarily breaking osascript path
- [ ] Window size restores on reopen (check `~/.config/odysseus/window_state.json`)
- [ ] Logs appear in `~/Library/Logs/Odysseus/`
- [ ] `build-mac-app.sh` runs cleanly from a clean venv (no pre-installed pywebview)
- [ ] App icon appears in Dock (set via `Info.plist` if distributing as .app)

---

## PR Filing Notes

- Depends on `feat/qt-native-linux-app` (issue #14) being merged upstream first.
  If filing before: include the shared JS files and note the dependency.
- Reference the existing `build-macos-app.sh` in the PR description; explain that this
  PR adds a WKWebView-native alternative (not a replacement).
- Reference upstream issue #3528 (Windows desktop wrapper) as prior art.
- `colorPicker.js` changes are additive; the existing Qt branch is unchanged.
- Must be tested on a real macOS machine before filing.
