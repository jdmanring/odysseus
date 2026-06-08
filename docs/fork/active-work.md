# Active Work

Current in-progress items as of 2026-06-08.

---

## In Progress

*(nothing currently in progress)*

---

## Recently Completed

| Item | Branch | Notes |
|------|--------|-------|
| DOM virtualization (load pagination + live pruning) | `develop` | `chatHistory.js` applied from `fix/dom-oom-virtualization`; `sessions.js`, `index.html`, `style.css` patched. Upstream PR staged — needs screenshots before filing. |
| External links / buttons not navigating (ISSUE-003) | `develop` | `OdysseusPage` subclass in `linux_wrapper.py` — routes external URLs to system browser |
| Crash recovery reload fix | `develop` | Changed from `triggerAction(Reload)` to `setUrl()` for clean post-crash navigation |
| Documentation restructure | `develop` | `CLAUDE.md`, `AI_ONBOARDING.md`, `docs/fork/` reorganized |
| Download progress display — per-file rows, accurate model total | `develop` | — |
| aria2c configuration hardening | `develop` | — |
| Crash recovery handler | `develop` | `564dd5c` |
| Native Linux app (`linux_wrapper.py`) | `develop` | Active development |
| streamingTTS scope fix | `develop` | `9fabdc6` — upstream PR staged |
| aria2c downloader | `develop` | Complete — upstream PR staged |

---

## Staged for Upstream (awaiting James to file)

See `upstream/pr-status.md` for full status of all upstream PRs.
