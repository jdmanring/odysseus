# Implementation Plan: FreeBSD/GhostBSD Qt Wrapper Support

**Fork issue:** [#45](https://github.com/jdmanring/odysseus/issues/45)
**Branch origin:** `upstream-mirror` (upstream-candidate)
**Branch name:** `feat/qt-native-freebsd-app`
**Depends on:** Issue #14 (`feat/qt-native-linux-app`) merged upstream first

---

## Overview

Extend `linux_wrapper.py` with platform-conditional code so it works on FreeBSD
and GhostBSD without changes to its Linux behavior. The wrapper architecture is
already compatible; only the memory monitor uses a Linux-specific `/proc` path.

This is a follow-on PR to #14, not a new file. The change is ~10 lines.

---

## What Already Works on FreeBSD (No Changes Needed)

- `pgrep` / `pkill` — in FreeBSD base system
- `os.dup2` — POSIX syscall, works on FreeBSD
- `signal.SIGTERM` / `signal.SIGINT` — works on FreeBSD
- `QSettings("odysseus", "odysseus")` — Qt respects `XDG_CONFIG_HOME` on FreeBSD,
  defaults to `~/.config/odysseus/odysseus.conf`
- `QDBusConnection.sessionBus()` — D-Bus available on FreeBSD via `devel/dbus` port;
  portal fallback to `QColorDialog` works where portal is absent
- `app.setDesktopFileName("odysseus")` — works on FreeBSD X11/Wayland DEs
- GPU flags after restructure — `_is_nvidia = os.path.exists("/proc/driver/nvidia")`
  returns `False` on FreeBSD (NVIDIA uses a different module path there); Mesa
  (AMD/Intel) path applies, which is correct for most FreeBSD desktops
- `--no-sandbox` — already in flags; correct for FreeBSD where the Chromium sandbox
  (Linux namespaces + seccomp-bpf) definitively does not work

---

## Required Code Change

### Memory monitor platform guard

The only Linux-specific code in the file is `_log_renderer_memory()`, which reads
`/proc/{pid}/status`. FreeBSD's `/proc` has a different layout and is not always
mounted. The function already has `except Exception` wrapping so it fails silently,
but the fix makes it actually work on FreeBSD.

**In `_log_renderer_memory()` inside `OdysseusWindow.__init__`**, replace:

```python
def _log_renderer_memory():
    try:
        import subprocess as _sp
        r = _sp.run(['pgrep', '-f', 'QtWebEngineProcess'], capture_output=True, text=True)
        for pid_s in r.stdout.strip().split():
            try:
                with open(f'/proc/{pid_s}/status') as f:
                    for line in f:
                        if line.startswith(('VmRSS', 'VmPeak')):
                            print(f'[MEM] pid={pid_s} {line.rstrip()}', flush=True)
            except OSError:
                pass
    except Exception as e:
        print(f'[MEM] error: {e}', flush=True)
```

With:

```python
def _log_renderer_memory():
    try:
        import subprocess as _sp
        import platform
        r = _sp.run(['pgrep', '-f', 'QtWebEngineProcess'], capture_output=True, text=True)
        for pid_s in r.stdout.strip().split():
            try:
                if platform.system() == 'Linux':
                    with open(f'/proc/{pid_s}/status') as f:
                        for line in f:
                            if line.startswith(('VmRSS', 'VmPeak')):
                                print(f'[MEM] pid={pid_s} {line.rstrip()}', flush=True)
                else:
                    # FreeBSD/other: ps(1) reports RSS in kilobytes
                    rss = _sp.run(
                        ['ps', '-o', 'rss=', '-p', pid_s],
                        capture_output=True, text=True
                    ).stdout.strip()
                    if rss:
                        print(f'[MEM] pid={pid_s} VmRSS:\t{rss} kB', flush=True)
            except OSError:
                pass
    except Exception as e:
        print(f'[MEM] error: {e}', flush=True)
```

---

## Implementation Steps

1. `git checkout upstream-mirror && git checkout -b feat/qt-native-freebsd-app`
2. Apply the memory monitor platform guard above
3. Verify `linux_wrapper.py` still works unchanged on Linux after the edit
4. Test on a FreeBSD or GhostBSD machine:
   - Install deps: `pkg install py311-qt6-webengine py311-qt6-webchannel py311-dbus-python`
     or `pip install PyQt6 PyQt6-WebEngine PyQt6-sip` into venv
   - Run `python linux_wrapper.py` and confirm the UI loads
   - Confirm memory log lines appear in `logs/wrapper_system.log`
   - Confirm color picker opens (via portal or QColorDialog fallback)
   - Confirm external links open in the system browser
5. Screenshot the running app on FreeBSD/GhostBSD for the PR
6. Write PR draft at `docs/fork/upstream/pr-drafts/feat-qt-native-freebsd-app.md`
7. Cherry-pick to `develop`; mark issue #45 in-progress

---

## Testing Checklist

- [ ] App launches on FreeBSD/GhostBSD; Odysseus UI loads
- [ ] Memory log lines appear in `logs/wrapper_system.log` (using `ps` path)
- [ ] Login state persists across restarts
- [ ] External links open in system browser
- [ ] Color picker opens (XDG portal or QColorDialog fallback; both acceptable)
- [ ] Window size and maximized state restore correctly
- [ ] `logs/wrapper_system.log` contains no traceback on startup
- [ ] Linux behavior unchanged: run the full Linux test suite from #14 after the edit

---

## PR Filing Notes

- Depends on `feat/qt-native-linux-app` (issue #14) merging upstream first.
  Include base wrapper changes if filing before #14 merges.
- The GPU restructure (NVIDIA detection) must also be present; without it,
  `QTWEBENGINE_FORCE_USE_GBM=0` would be set globally and could degrade Mesa
  GPU acceleration on FreeBSD.
- Scope the PR title and description carefully: this is not a separate wrapper,
  it is `linux_wrapper.py` gaining cross-platform support. Suggest title:
  `feat(linux): extend Qt wrapper to support FreeBSD and GhostBSD`
- Note in the PR that OpenBSD is out of scope: Chromium/Qt WebEngine requires
  Linux kernel namespaces and seccomp-bpf that OpenBSD's kernel does not provide.
