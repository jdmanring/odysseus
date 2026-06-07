# Fork Change Log

This document tracks all modifications, fixes, and additions made specifically to the Odysseus fork. This is an internal record for the fork and is not intended for upstream contribution to prevent polluting the main project with fork-specific documentation.

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
