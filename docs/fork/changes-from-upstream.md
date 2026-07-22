# Changes From Upstream

This is the master record of everything this fork has that upstream doesn't, and
everything we've changed from the upstream source. Updated whenever new divergence
is introduced.

Last updated: 2026-06-10

---

## New Files (no upstream equivalent)

### Native Linux Desktop App
| File | Purpose |
|------|---------|
| `qt_wrapper.py` | PyQt6 app that wraps the Odysseus web UI in a native Qt window. Manages uvicorn server lifecycle, GPU acceleration flags (NVIDIA/Wayland), crash recovery via `renderProcessTerminated` signal, 60s memory monitor, persistent browser profile. |
| `static/js/qt-bridge.js` | Non-module script injected by the Qt wrapper. Sets up `QWebChannel` and exposes `window.qtBridge` so web JS can call native OS APIs (e.g. color picker dialog). |
| `static/js/platform.js` | Detects `window.__QT_WRAPPER__` to gate Qt-only features from browser-only code paths. |
| `build-linux-app.sh` | Build script for the Linux native app packaging. |

### Model Download Stack
| File | Purpose |
|------|---------|
| `tooling/aria2c_download.py` | Download entry point. Resolves HF signed URLs → writes `--input-file` → spawns single aria2c subprocess. 4 files × 16 connections = 64 total. Resume via `.aria2` sidecar files. No daemon, no RPC. |
| `tooling/bin_manager.py` | Auto-installs external binaries (aria2c) if missing. Fetches static platform builds from GitHub releases, caches in `~/.local/share/odysseus/bin/`. |
| `tooling/hf_url_resolver.py` | Resolves HuggingFace repository snapshot URLs to direct download links. Handles gated models via HF token. Re-resolved fresh on every download start (signed URLs expire). |
| `tooling/sync-upstreams/upstream_ingest_pipeline.py` | Syncs `upstream/dev` through 3 gates (syntax, lint, tests) before promoting to `integration` branch. |

### Documentation System
All files under `docs/fork/`, `docs/project/`, `docs/dev/`, `docs/user/`, `docs/audit/` —
documentation system for managing fork state and enabling AI collaboration.

### Memory / Vector Store (#161, branch `feat/memory-qdrant-nomic`)
- `src/vector_client.py` — Qdrant-backed vector store, shaped to the ChromaDB
  collection API the codebase already speaks. Converts Qdrant's cosine similarity
  back to a Chroma distance (`1 − score`), maps arbitrary string IDs to UUIDv5, and
  translates `where=` equality filters. Replaces the deleted `src/chroma_client.py`.
- `docs/dev/memory-architecture.md` — the locked-in architecture and rationale.

(`tooling/verify_memory_stack.py` is #160's file; #161 modifies it to check
qdrant-client instead of chromadb-client.)

Modified alongside (existed upstream): `src/embeddings.py` (nomic default,
llama.cpp `LlamaCppEmbedClient`, 256-dim Matryoshka + query/doc prefixes),
`src/embedding_lanes.py` (fastembed→llama.cpp fallback, Qdrant client, fingerprint
sidecar), `src/memory_vector.py`, `src/rag_vector.py` (Qdrant + 2048-char chunks).

---

## Modified Files (significant changes from upstream baseline)

### `static/js/cookbookRunning.js`
Heavy modifications to the download card UI:
- Per-file progress rows with individual progress bars (`_buildSingleFileRow`, `data-dl-files` container)
- Module-level `_dlFileTracker` Map — accumulates completed-file bytes across poll ticks for accurate overall model progress (prevents the "stuck at 18/18 GiB (99%)" problem)
- Fixed aria2c progress regex: leading space before `[#gid]` lines requires `^\s*\[#`, not `^\[#`
- Pause button always visible during active phases (not just `downloading`)
- `_midTrunc()` helper for filename display with middle truncation
- `data-dl-phase` CSS architecture for phase-based show/hide

### `static/js/chatHistory.js` (new file)
DOM virtualization — `MessageWindow` class. Load-time pagination: renders only the last 50 messages on session load; `IntersectionObserver` on a top sentinel loads older batches of 25 as the user scrolls up, preserving scroll position via the `scrollHeight` delta technique. Live pruning: caps `#chat-history` at 80 DOM children; prunes oldest 20 nodes to a height-matched spacer, restores via `IntersectionObserver` on scroll. Plain (non-module) script; sets `window.chatHistory`. Constants: `WINDOW_SIZE=50`, `BATCH_SIZE=25`, `PRUNE_AT=80`, `PRUNE_COUNT=20`, `BIDI_CAP=120`.

### `static/js/sessions.js`
- `selectSession()` now calls `window.chatHistory.reset()` before clearing `#chat-history`
- Message-load loop replaced: messages collected into `_preparedMsgs` array then passed to `window.chatHistory.load()` instead of calling `addMessage()` directly in a synchronous for-loop

### `static/index.html`
- `chatHistory.js` script tag added before module scripts (must load first to set `window.chatHistory` before `sessions.js` executes)

### `static/style.css`
- Sentinel/spacer `overflow-anchor: none` rule added — prevents Chrome's scroll-anchor algorithm from double-compensating programmatic `scrollTop` adjustments during history batch loads

### `static/js/colorPicker.js`
- Eyedropper button now uses Qt native color dialog (`window.qtBridge.openColorPicker()`) when running inside the Qt wrapper, with Web EyeDropper API as fallback in regular browsers
- Previously: button was disabled with "Eyedropper not supported in this browser" inside Qt

### `static/style.css`
- Pause button CSS for all active download phases
- Per-file row styles: `.dl-files-list`, `.dl-file-row`, `.dl-file-row-bar`, `.dl-file-row-fill`, `.dl-file-row-stats`

### `tooling/aria2c_download.py`
Beyond being a new file, key hardening vs. any upstream version:
- `--auto-file-renaming=false` — never silently rename existing files
- `--retry-wait=3` — 3s between retries, not immediate hammering
- `--download-result=hide` — suppresses verbose result table at exit
- `--disk-cache=64M` — write buffer reduces disk seeks

### `qt_wrapper.py`
Beyond being a new file, key additions over any upstream version:
- `OdysseusPage(QWebEnginePage)` subclass: `acceptNavigationRequest` opens non-localhost URLs via `QDesktopServices.openUrl()` instead of navigating the app view away; `createWindow` handles `target="_blank"` and `window.open()` by routing to the system browser
- `renderProcessTerminated` crash recovery: auto-reloads via `setUrl()` (clean navigation, not cached `Reload`) on OOM/hard crash; crash-loop guard (second crash within 10s aborts)
- 60s renderer memory snapshot via `/proc/{pid}/status`
- OS-level fd redirect: renderer stderr → `logs/wrapper_system.log`

### `docs/fork/build-linux-app.md` → `linux-build-and-install.md`
Fork-specific build instructions for the Linux native app (no upstream equivalent).

### `static/js/theme.js` — Catppuccin Mocha theme added
Fork has 17 built-in themes vs upstream's 16. Added `catppuccin` using Catppuccin Mocha palette with a mauve accent (`#8565d1`). Default theme is `catppuccin` (fork preference); upstream default is `dark`. The upstream-candidate PR (`feat/catppuccin-theme`, issue #30) proposes adding catppuccin with default remaining `dark`.

---

## Deleted Files (existed upstream or in earlier fork versions, now gone)

| File | Why deleted |
|------|------------|
| `tooling/aria2_manager.py` | Ghost file — RPC daemon manager for old architecture. Never worked, no callers outside its own module group. |
| `tooling/aria2_rpc.py` | Ghost file — JSON-RPC client for old architecture. Same. |
| `tooling/provisioner.py` | Ghost file — coordinator for the above two. Same. |
| `HANDOFF_TO_CLAUDE.md` | Stale AI conversation handoff doc — obsolete with proper memory/CLAUDE.md system. |
| `src/chroma_client.py` | ChromaDB HTTP client — removed in the Qdrant migration (#161). Replaced by `src/vector_client.py`. |

