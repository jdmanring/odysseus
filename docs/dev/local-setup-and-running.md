# Local Setup and Running

## Prerequisites

- Python 3.10+
- `pip` / virtualenv
- `aria2c` (optional — auto-installed by `BinManager` if missing)

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
