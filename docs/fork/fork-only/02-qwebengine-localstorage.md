# [INTERNAL] QWebEngineView LocalStorage Persistence

## Description
Fixes the issue where the native PyQt6 wrapper's `QWebEngineView` used an in-memory profile, wiping `localStorage` (username, theme, etc.) on every exit.

## Fix
Implemented `QWebEngineProfile("odysseus")` with explicit persistent storage paths in `~/.local/share/odysseus/webengine`.

## Status
- [x] Implemented and verified
- [ ] Documented as a dependency for any upstream native wrapper
