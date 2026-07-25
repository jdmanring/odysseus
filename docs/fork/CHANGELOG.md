# Fork Change Log

This document tracks all modifications, fixes, and additions made specifically to the Odysseus fork. This is an internal record for the fork and is not intended for upstream contribution to prevent polluting the main project with fork-specific documentation.

## [2026-06-07]: Download UI Overhaul + Parallel Downloads + Pause/Resume
### Cookbook / Download
- **Structured download card:** Replaced the raw `<pre>` terminal output for download tasks with a purpose-built progress card showing phase (initializing -> resolving -> downloading -> paused -> done/error), progress bar, per-file index, size, speed, ETA, and connection count badge. All phase sections live in the DOM; CSS `[data-dl-phase]` selects which is visible, so no re-render flicker.
- **Parallel file downloads:** `aria2c_download.py` now uses aria2c's `--input-file` mode to download up to 4 files simultaneously (4 connections each, 16 total, the same bandwidth budget as the old sequential approach). Multi-shard models (e.g. 4x 4.6 GB shards) complete significantly faster end-to-end since large files can download in parallel.
- **Pause / Resume:** The download card shows a Pause button during the downloading phase. Pause sends C-c to the aria2c process in the tmux pane, which exits gracefully and writes `.aria2` sidecar files. The card transitions to a persistent "paused" state with a Resume button. Resume re-runs the download; aria2c's `--continue=true` picks up from the sidecar files; no bytes are lost.
- **Parallel progress aggregation:** `_parseDownloadState` now collects all `[#gid ...]` blocks from the aria2c summary window, sums dl/total bytes and speed across all active downloads, and calculates an accurate overall progress percentage. Adds helpers `_parseIecBytes`, `_fmtIecBytes`, `_fmtSpeed`, `_fmtEtaSecs` for numeric byte/speed manipulation.
- **Redesigned progress bar:** Height increased 5 -> 8 px; gradient fill from a dim accent at 0% to full accent at 100%. Percentage label shown right-aligned next to the bar for at-a-glance readability.
- **aria2c output parser (`_parseDownloadState`):** Parses all sentinel lines (`[*]`, `[!]`, `DOWNLOAD_OK`, `DOWNLOAD_FAILED`) and the `[#gid dl/total(pct%) CN:n DL:speed ETA:eta]` progress format. Parallel mode: aggregates multiple progress blocks for overall accuracy.
- **Live in-place DOM updates:** `_updateDownloadCard()` is called on every `_reconnectTask` poll tick; only the changed attributes are touched, with no `innerHTML` replacement mid-stream. Guard added so the updater is a no-op for paused tasks.
- **Inline Pause/Stop/Resume/Retry buttons:** Download cards have phase-appropriate action buttons directly on the card. Pause + Stop visible when downloading; Resume when paused; Retry when done/error. Stop and Restart removed from the three-dot menu for download tasks to avoid duplication.
- **Collapsible raw log:** A "Show log / Hide log" toggle reveals the full tmux capture-pane output for debugging without cluttering the default view.
- **Queued state card:** Download tasks in queued state show their queue position and an inline "Start now" button.
- **Middle-truncation:** Long filenames are mid-truncated (`filen…ame.safetensors`) so both ends remain readable in the fixed-width file-info row.
- **CSS:** `.dl-*` classes in `style.css`: spinner animation, phase-gated visibility, gradient progress track, pct label, stats row, connection badge, done/error banners, action buttons (pause/stop/resume/retry), log toggle, queue card, `cookbook-task-paused` badge style.

### Downloader Bug Fixes
- **Fixed 500 errors on `/api/model/download`:** Three `UnboundLocalError` / `TypeError` bugs in `cookbook_routes.py` caused all download requests to fail silently. Fixed variable hoisting (`remote`, `is_windows`), corrected kwarg name (`local_dir` -> `output_path`), added `include` parameter to `model_downloader.start_download`. Added `try/except` wrapper + `logger.exception` so future route errors appear in `logs/server.log`.
- **Fixed model not appearing in Serve after download:** `aria2c_download.py` was saving to `~/.cache/huggingface/hub/models/{repo_short}/`, a flat path the `scan_hf()` scanner skips. Changed default destination to `models--{org}--{repo}/snapshots/{commit_sha}/` with `refs/main` containing the real commit SHA. `HfUrlResolver.get_commit_hash()` fetches the SHA before downloading so the layout is fully HF-library-compatible: `snapshot_download(repo_id)` resolves to the correct snapshot dir without re-downloading.
- **Model list refresh on download completion:** All three done-transition paths in `_reconnectTask` now call `window.modelsModule.refreshModels(true)` so the downloaded model appears in the Serve picker immediately without a page reload.
- **Fixed "stuck Initializing" bug:** `_updateDownloadCard` was passed the card element (`.dl-card`) instead of the parent task card, so its internal `querySelector('[data-dl-card]')` returned null and all in-place updates were silently dropped. Fixed the call site to pass the task card element.
- **Fixed Stop button invisible during "Initializing":** CSS previously only showed Stop for the `downloading` phase. Added rules for `initializing`, `starting`, `resolving` phases. JS `_updateDownloadCard` updated to match.
- **Fixed log toggle Unicode:** The log toggle chevron was setting `firstChild.textContent = '▶ '` which destroyed the SVG element. Changed to rotate the SVG via `style.transform = 'rotate(90deg)'`.

## [2026-06-09]
### Cookbook / GGUF Resolution
- **Subdirectory GGUF Detection:** Updated `HfUrlResolver` to match `include` patterns against both the full file path and the basename. This ensures `.gguf` files are detected regardless of directory depth (e.g., `gguf/model.gguf`).
- **Unified Resolution Logic:** Refactored `aria2c_download.py` to remove its internal, rigid file-matching implementation. It now imports and utilizes `HfUrlResolver`, ensuring discovery and downloading use the same logic.
- **Gated Model Support:** Modified `cookbook_routes.py` to inject the HuggingFace token into the discovery process, allowing detection of files in gated repositories.
- **Console Noise Reduction:** Changed `aria2c` `--console-log-level` from `debug` to `notice` to remove low-level socket/cache spam from the streaming console.
- **Connection Tuning:** Optimized `aria2c` download concurrency to 4 files with 3 threads per file (12 total connections) to prevent home router instability while maintaining high throughput.

## [2026-06-08]
### Performance & Rendering
- **Linux Display Pipeline Optimization:** Implemented a high-performance OpenGL stack for `linux_wrapper.py`, including `--use-gl=desktop`, `--disable-gpu-compositing`, `--ignore-gpu-blocklist`, `--enable-gpu-rasterization`, and `--enable-zero-copy`.
- **Wayland Native Support:** Added `--ozone-platform-hint=auto` to reduce input lag and improve scaling on Wayland environments.
- **CSS Layer Promotion:** Added `will-change: transform` and `translateZ(0)` to the chat container and input fields to prevent full-page repaints during typing, eliminating micro-stutters.
- **Qt Context Sharing:** Enabled `AA_ShareOpenGLContexts` to optimize GPU resource usage between the wrapper and the WebEngine.

## [2026-06-07]
### UI & Integration
- **Smart Service Lifecycle:** Implemented PID-based tracking for backend services (Odysseus Server, SearXNG, ChromaDB) to prevent zombie processes.
- **Native Wrapper Integration:** Updated `odysseus-app` to act as the master controller, handling startup/shutdown and crash recovery via `~/.odysseus/services.pid`.
- **KDE/s6 Optimization:** Optimized the launch sequence for Artix s6 KDE, ensuring services are user-managed and properly cleaned up on application exit.

## [2026-06-06]
### Agent & Tooling
- **Fixed "Agent Shackle":** Updated `data/settings.json` to set `agent_max_tool_calls` to 20. Previously set to 0, which disabled all tool execution even in Agent mode.
- **Routing Audit:** Verified `routes/chat_routes.py` logic to ensure the distinction between Chat and Agent modes is preserved while ensuring Agent mode has the necessary permissions to operate.

## [Recent Milestones]
### Environment & Core
- **Python 3.14 Compatibility:** Implemented patches for `basicsr` to ensure stability on Python 3.14.
- **HF Token Workaround:** Added `set-hf-token.py` to handle HuggingFace token persistence outside the UI.

### UI & Integration
- **Desktop Wrapper:** Implemented PyQt6 wrapper to allow Odysseus to run as a native desktop application.

### Dependencies
- **Expanded Toolset:** Integrated optional dependencies for enhanced capabilities:
    - `faster-whisper` (Transcription)
    - `markitdown` (Document conversion)
    - `playwright` (Web automation)
    - `realesrgan` (Image upscaling)
