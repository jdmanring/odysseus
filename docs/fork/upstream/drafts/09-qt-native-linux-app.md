# [UPSTREAM] Native Linux Desktop Application (Qt Wrapper)

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: **Implemented on `develop`** / tracking branch `feat/qt-native-linux-app`
- Related fork issues: #14 (umbrella), #3 (external links), #13 (color picker), #17 (localStorage)

## Roadmap alignment

This contribution directly closes open ROADMAP items:
- **"Fresh install smoke tests on Linux, macOS, and Windows"** — provides the complete native Python/Linux install and launch story that was missing
- **"SQUASH BUGS" / crash recovery** — `renderProcessTerminated` handler + `setUrl()` reload addresses the OOM renderer crashes (same class of bug as the DOM virtualization PR #06)
- **"Cookbook reliability on other computers"** — `build-linux-app.sh` gives Linux a reproducible single-command install path
- **"Vendor CDN assets / self-hosted/offline mode"** — Qt wrapper bundles the app natively; no browser dependency, fully local

## Notes

This is a **Feature addition**. Use the **Feature Request** template on GitHub.

**Upstream PR scope** — all of the following belong in one cohesive PR:

| File | Purpose |
|------|---------|
| `linux_wrapper.py` | PyQt6 app: server lifecycle, `QWebEngineView`, GPU flags, crash recovery, memory monitor |
| `static/js/qt-bridge.js` | `QWebChannel` setup; exposes `window.qtBridge` for native OS API calls |
| `static/js/platform.js` | `window.__QT_WRAPPER__` detection for feature-gating Qt-only code paths |
| `build-linux-app.sh` | Single-command install/packaging script |

These in-app fixes are required for a correct experience and ship in the same PR:
- `OdysseusPage(QWebEnginePage)` subclass (in `linux_wrapper.py`): routes external URLs to system browser — without this, clicking any link navigates the app view away or silently fails
- `QWebEngineProfile("odysseus")` persistent profile: localStorage/session state survives app restarts — without this the app forgets the user on every exit
- `static/js/colorPicker.js`: `window.qtBridge.openColorPicker()` call so the eyedropper works inside Qt (Web EyeDropper API is unavailable in `QWebEngineView`)

**What does NOT go upstream:**
- `logs/` directory and `os.dup2` fd-redirect to `logs/wrapper_system.log` — local dev/debug aid; strip from the upstream PR or discuss with maintainer
- Fork-specific paths (`docs/fork/`, CLAUDE.md, etc.)

**Screenshots required before filing:**
- App running in system taskbar (GNOME or KDE)
- Clicking an external link opens the system browser (not the app window)
- Color picker dialog open (native Qt dialog)
- (Optional) DevTools showing bounded DOM child count during an agent session

**Tests:**
- Manual end-to-end: install → launch → send a message → click external link → close app → relaunch → confirm session state persists
- No automated test framework for the Qt wrapper; document the manual test steps in the PR checklist

---

## Staged Issue (Feature Request)
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=feature_request.yml -->

### Is your feature request related to a problem?

Yes. On Linux, Odysseus requires the user to have a separate browser open and navigate to `localhost:7000`. There is no native desktop launch mechanism, no system integration (taskbar, launcher), and no path to a proper native install experience. This is a friction point for users who want a desktop app rather than a web tab.

### Describe the solution you'd like

A native Linux desktop application built with PyQt6 that wraps the existing Odysseus web UI. The wrapper:
- Starts the uvicorn server automatically on launch and stops it on window close
- Embeds `QWebEngineView` (Chromium) to display the existing web UI unchanged
- Integrates with the Linux desktop environment: window manager, taskbar, app switcher
- Routes external links to the system browser instead of navigating the app away
- Persists session state (localStorage, theme, username) across restarts via a named profile
- Enables native OS dialogs (color picker) via a thin `QWebChannel` JS bridge
- Provides crash recovery: auto-reloads on renderer OOM with a crash-loop guard
- Ships a `build-linux-app.sh` packaging script for a reproducible install

No changes to the web UI, server, or any existing functionality — the wrapper is purely additive.

### Alternatives considered

- Electron: heavier dependency tree, not a natural fit for a Python project
- PWA/browser shortcut: no system integration, no crash recovery, no native dialogs

### Additional context

This implementation has been running as the primary Linux interface for this fork for several months. The crash recovery handler was added specifically after confirming two V8 Oilpan OOM crashes (issue #06 / DOM virtualization PR) — the Qt wrapper handles the crash gracefully instead of leaving a blank page.

Addresses ROADMAP items: native Linux install story, crash recovery, self-hosted desktop experience.

**Willing to submit a PR:** Yes — branch `feat/qt-native-linux-app` is ready.

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

- Adds `linux_wrapper.py`: a PyQt6 desktop app that wraps Odysseus in a native window, manages server lifecycle, and provides crash recovery
- Adds `static/js/qt-bridge.js` + `static/js/platform.js`: thin JS bridge for native OS API calls (currently: color picker dialog)
- Adds `build-linux-app.sh`: reproducible single-command install for Linux
- Fixes three issues that must ship together for a correct experience: external link routing, localStorage persistence, and native color picker

No changes to the web UI, server logic, or existing user flows.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] New feature (non-breaking — adds a new capability without touching existing flows)

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to described scope
- [ ] App run locally and fix verified end-to-end *(see How to Test)*
- [ ] Screenshots attached

### How to Test

1. `pip install PyQt6 PyQt6-WebEngine`
2. `bash build-linux-app.sh` (or `python linux_wrapper.py` directly)
3. Confirm the app window opens and the Odysseus UI loads
4. Send a chat message — confirm normal operation
5. Click an external link or button that navigates externally — confirm it opens in the system browser, not in the app window
6. Close and reopen the app — confirm session state (login, theme) persists
7. Open Settings → color picker → eyedropper button — confirm native dialog opens
8. Close the app — confirm the uvicorn server also stops (no orphan process)

### Visual / UI changes
- [x] Screenshots required — see checklist above
- [x] No changes to existing UI components or styles in browser context
- [x] Qt-specific code paths gated behind `window.__QT_WRAPPER__` check in `platform.js`
