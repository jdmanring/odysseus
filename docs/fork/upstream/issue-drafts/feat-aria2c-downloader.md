# Upstream Issue Draft: feat-aria2c-downloader

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-aria2c-downloader.md`
**Branch:** `feat/aria2c-downloader`
**Type:** Enhancement
**References:** Related to #359 (download percentage request); Related to #4059 (downloader stalls silently on large files)

---

## Title

`[Cookbook] Replace hf_transfer with aria2c for parallel downloads with real-time progress, pause, resume, and cancellation`

---

## Body

**Area:** Cookbook / Model Downloads

**Problem / Motivation:**
The current download system (`hf_transfer`) provides no user-visible progress — users see only a spinner with no percentage, speed, or time estimate (related: #359). More significantly, downloads cannot be paused, resumed, or cancelled once started. A failed or interrupted download requires restarting from zero, and there is no way to run multiple downloads in parallel. For large models (10–70 GB), these limitations make the Cookbook unreliable for production use.

**Proposed Solution:**
Replace `hf_transfer` with `aria2c` as the download backend. aria2c supports parallel chunk downloading, resume-on-restart, and real-time JSON-RPC status. The integration adds:

- **Real-time progress:** per-file percentage, download speed, ETA, and bytes transferred — updated every poll cycle in the UI
- **Pause and resume:** mid-download pause without losing progress; resume picks up from where the transfer stopped
- **Cancellation:** cancel mid-download; partially downloaded files are cleaned up
- **Multi-file downloads:** all files in a model download run in parallel; per-file and aggregate progress displayed
- **Circuit breaker:** rapid-failure detection to prevent retry storms on bad connections
- **Split-file size controls:** configurable chunk count and minimum chunk size
- **Graceful fallback:** if aria2c is not installed, falls back to the existing hf_transfer path with a warning

No change to how models are selected, stored, or used. The download pipeline is the only thing replaced.

**Alternatives Considered:**
- Enhance `hf_transfer` directly: the library does not expose pause/resume or per-file progress callbacks.
- `wget` / `curl`: no parallel chunk support; would require custom progress parsing.
- aria2c: widely available via package managers on all platforms, well-documented JSON-RPC interface, native parallel chunk support and resume.
