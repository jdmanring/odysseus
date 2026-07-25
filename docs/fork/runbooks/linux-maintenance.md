# Linux App: Maintenance Runbook

## Pending: Remove qt6-webengine version pin

**Why it was pinned:** The `qt6-webengine 6.11.1-3` rebuild broke compatibility with
`python-pyqt6-webengine 6.11.0-1`. Pinned in `/etc/pacman.conf` to prevent the broken
upgrade until the Python bindings catch up.

**When to act:** When `python-pyqt6-webengine` updates to `6.11.1` in the repos.

**Check:**
```bash
paru -Si python-pyqt6-webengine | grep Version
```

**Action:** Remove `IgnorePkg = qt6-webengine` from `/etc/pacman.conf`, then:
```bash
sudo paru -Syu
```

---

## System package dependencies

The wrapper requires system-installed PyQt6 (not pip). Install once; no venv involvement:
```bash
sudo pacman -S python-pyqt6 python-pyqt6-webengine
```

`QWebChannel` and `QtDBus` are bundled with `python-pyqt6`; no additional packages needed.

---

## Log locations

| Log | Path |
|-----|------|
| Wrapper (Python/Qt) | `$REPO/logs/wrapper_system.log` |
| Server (uvicorn) | `$REPO/logs/server.log` |
| Chromium renderer | `$REPO/logs/chrome_debug.log` |

---

## Zombie process cleanup

The wrapper kills stale uvicorn processes on launch via `pkill -f "uvicorn app:app"`. If the
app crashes hard without cleanup, kill manually:
```bash
pkill -f "uvicorn app:app"
```

---

## Rebuild / reinstall desktop entry

After any change to the launcher, icon, or `.desktop` file:
```bash
bash build-linux-app.sh
```

Log out and back in if KDE doesn't pick up icon changes immediately.

---

## KDE icon cache issues

If the taskbar still shows the old icon after reinstall:
```bash
kbuildsycoca6 --noincremental
```
