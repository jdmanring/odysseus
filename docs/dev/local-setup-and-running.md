# Local Setup and Running

> For the **native desktop app** (build/install, per-OS architecture, uninstall,
> troubleshooting) see [desktop-wrappers.md](desktop-wrappers.md). The
> one-command setup is `./setup.sh` (Linux/*BSD), `./start-macos.sh` (macOS), or
> `setup.ps1` (Windows).

## Prerequisites

- Python 3.11+
- `pip` / virtualenv
- `aria2c` — **the** Cookbook downloader (the fork's replacement for the flaky
  `hf_transfer`; it is not an optional accelerator). Auto-installed by
  `BinManager` on Linux/Windows; on **macOS** there is no static build, so it is
  installed by `start-macos.sh` (`brew install aria2`; conda-forge also works).
  The built-in Python (`huggingface_hub`) downloader exists only as an emergency
  fallback when aria2c genuinely can't be provisioned.

## Install

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure:
- `AUTH_ENABLED=false` — for local single-user use
- `OPENAI_API_KEY` — if using OpenAI models
- `HF_TOKEN` — for gated HuggingFace models

Note: `.env` must be saved as UTF-8 without BOM. A BOM causes keys to be silently
misread (upstream issue #142).

## Run

**Web app only:**
```bash
venv/bin/uvicorn app:app --host 127.0.0.1 --port 7000
```
Open `http://127.0.0.1:7000` in a browser.

**Linux native wrapper** (requires PyQt6 and PyQt6-WebEngine — install via your distro package manager or `pip install PyQt6 PyQt6-WebEngine`):
```bash
python3 qt_wrapper.py
```
Starts the server and opens a Qt window. Do not also run uvicorn manually — the
wrapper owns the server lifecycle.

## Data locations

| Data | Default path |
|------|-------------|
| SQLite database | `data/app.db` |
| ChromaDB embeddings | `data/chroma/` |
| User settings | `data/settings.json` |
| Uploaded files | `uploads/` |
| HuggingFace model cache | `~/.cache/huggingface/hub/` (standard HF layout) |

## Logs (native wrapper)

| Log | Path |
|-----|------|
| Chromium + Python output | `logs/wrapper_system.log` |
| HTTP access log | `logs/server_access.log` |
