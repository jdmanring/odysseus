# Building the Linux App (Fork)

## Architecture

The Linux native app has two separate Python runtimes:

| Layer | Python | Why |
|-------|--------|-----|
| Display (`linux_wrapper.py`) | `/usr/bin/python3` (system) | Uses system-built PyQt6/WebEngine with native Wayland support |
| Backend (`uvicorn app:app`) | `venv/bin/python` | All server dependencies (FastAPI, ML libs, etc.) live in the venv |

The pip-distributed PyQt6 is built without Wayland ozone support and must not be used for the wrapper.

## Prerequisites

### System packages (pacman)
```bash
sudo pacman -S python-pyqt6 python-pyqt6-webengine
```

These provide native Wayland/ozone support in the Chromium renderer. The pip equivalents (`PyQt6`, `PyQt6-WebEngine`) must not be installed in the venv — remove them if present:
```bash
venv/bin/pip uninstall -y PyQt6 PyQt6-Qt6 PyQt6_sip PyQt6-WebEngine PyQt6-WebEngine-Qt6
```

### Venv (server deps only)
```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## Install

```bash
bash build-linux-app.sh
```

The script:
1. Verifies system PyQt6 with WebEngine is available
2. Installs the launcher at `~/.local/bin/odysseus` (uses `/usr/bin/python3`)
3. Installs `assets/odysseus.svg` to the hicolor scalable icon directory
4. Writes the `.desktop` entry and refreshes icon/desktop caches

Log out and back in after the first install so KDE picks up the new icon.

## Runtime configuration

### Chromium flags (`linux_wrapper.py`)
```
--no-sandbox          required on Artix (user namespaces may not be enabled)
--ozone-platform=wayland   explicit Wayland backend for the Chromium renderer
```

Qt auto-detects Wayland from `WAYLAND_DISPLAY` — no `QT_QPA_PLATFORM` override needed.

### Log files
All logs go to `$REPO/logs/`:
- `wrapper_system.log` — Python wrapper stdout/stderr
- `server.log` — uvicorn/FastAPI (via `ODYSSEUS_LOG_FILE` env var)
- `chrome_debug.log` — Chromium renderer

### Persistent profile
Browser storage (cookies, localStorage, session) lives at:
- `~/.local/share/odysseus/webengine/` — persistent data
- `~/.cache/odysseus/webengine/` — network/GPU cache

## Upstream sync notes

`README.md` is in `PROTECTED_FILES` in the ingest pipeline — upstream's `docs/` media paths will not overwrite our `assets/` paths on sync. Any docs/ media files upstream re-adds are automatically removed by the post-merge cleanup step (canonical copies are in `assets/`).
