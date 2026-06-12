# Architecture — Odysseus

A self-hosted AI workspace. FastAPI backend serves a plain-JS SPA at `127.0.0.1:8000`.
No bundler. No framework on the frontend. Single-user.

---

## Request Path (Chat)

```
User types → chat.js → POST /api/chat_stream
  → routes/chat_routes.py
  → src/llm_core.py → LLM API (Ollama / OpenAI / Anthropic)
  → SSE stream back → chatStream.js renders tokens live
  → complete → message saved to SQLite via core/database.py
```

Agent mode replaces `llm_core.py` with `src/agent_loop.py`:
```
agent_loop.py ──► calls tools ──► appends tool results ──► loops until model stops
```
Tool results are appended as `{"role": "system", "content": "[Tool execution results]\n\n..."}`.
The Anthropic payload builder has a special case for these — see `src/llm_core.py:_build_anthropic_payload`.

---

## Backend Layout

```
app.py                    ← FastAPI orchestrator — imports routers, configures middleware
routes/                   ← One APIRouter per feature area
  chat_routes.py          ← /api/chat_stream, /api/chat
  cookbook_routes.py      ← /api/cookbook/* (model download, serve)
  settings_routes.py      ← /api/settings
  ...
src/                      ← Business logic (called by routes, not imported by each other)
  llm_core.py             ← LLM dispatch — builds provider payloads, streams responses
  agent_loop.py           ← Agentic loop — tool calls, result injection, iteration limit
  embeddings.py           ← ChromaDB interface for RAG
  settings.py             ← DEFAULT_SETTINGS dict + load/save helpers
core/
  database.py             ← SQLAlchemy models + SQLite session factory
  models.py               ← Pydantic request/response models
  auth.py                 ← Optional auth middleware (off by default)
mcp_servers/              ← MCP server implementations (memory, RAG, image gen, email)
tooling/                  ← Standalone utilities (subprocess-safe, no FastAPI dependency)
  aria2c_download.py      ← HF model download via aria2c subprocess
  bin_manager.py          ← Auto-install external binaries (aria2c, ffmpeg, etc.)
  hf_url_resolver.py      ← SINGLE SOURCE OF TRUTH for HuggingFace signed URLs and file resolution (used by routes and downloaders)
```

---

## Frontend Layout

No bundler. All files are plain ES modules (or non-module scripts) served directly.
`static/index.html` is the SPA shell. `static/js/init.js` boots the UI.

```
static/js/
  init.js               ← App bootstrap — event wiring, initial state load
  chat.js               ← Chat input, send logic, session switching
  chatStream.js         ← SSE consumer — feeds tokens to renderer
  chatRenderer.js       ← Turns message objects into DOM nodes
  chatHistory.js        ← Non-module script — MessageWindow virtualization class
  sessions.js           ← Session list, create/delete, selectSession()
  cookbook*.js          ← Model management (6 files — see Cookbook section)
  theme.js              ← Theme system
  colorPicker.js        ← Color picker — uses Qt native dialog when in wrapper
  qt-bridge.js          ← Non-module — sets up window.qtBridge for native calls
  platform.js           ← Detects window.__QT_WRAPPER__ to gate Qt-only features
```

A new `.js` file needs a `<script>` tag in `index.html` — there's no automatic discovery.
Non-module scripts (`chatHistory.js`, `qt-bridge.js`) must load before any modules that use them.

---

## Data Storage

| What | Where |
|------|-------|
| Conversations, sessions, messages | SQLite `data/app.db` |
| Memory / RAG embeddings | ChromaDB `data/chroma/` |
| User preferences | `data/settings.json` |
| Uploaded files | `uploads/` |
| HuggingFace model cache | `~/.cache/huggingface/hub/` |

`data/` is gitignored entirely. `data/settings.json` overrides `src/settings.py`'s
`DEFAULT_SETTINGS` at runtime — test against `DEFAULT_SETTINGS` first when debugging
settings-related issues.

---

## Cookbook (Most Complex Subsystem)

Download, serve, and manage local AI models.

```
cookbookDownload.js  →  POST /api/cookbook/download/start
  →  cookbook_routes.py spawns tooling/aria2c_download.py as subprocess
  →  cookbookRunning.js polls GET /api/cookbook/download/status/{session_id} every 2s
  →  parses aria2c stdout, updates progress cards in-place
```

Progress lines from aria2c look like (leading space before `[` is literal):
```
·[#a1b2c3 1GiB/5GiB(21%) CN:4 DL:50MiB ETA:1m20s]
·FILE: /path/to/file
```
Regexes must use `^\s*\[#` — not `^\[#`.

`_dlFileTracker` in `cookbookRunning.js` is module-level state that accumulates
completed-file bytes across poll ticks. It is not reset between ticks by design.

---

## Native Linux App (Fork Addition)

`qt_wrapper.py` wraps the web UI in `QWebEngineView` (PyQt6):

```
qt_wrapper.py starts → spawns uvicorn → loads http://127.0.0.1:8000 in QWebEngineView
```

`OdysseusPage(QWebEnginePage)` subclass:
- `acceptNavigationRequest` — external links open in system browser via `QDesktopServices`
- `createWindow` — `target="_blank"` links also go to system browser
- Crash recovery — `renderProcessTerminated` handler calls `setUrl()` to reload

`QWebEngineView` is Chromium but **not a browser** — the Web EyeDropper API is missing.
`colorPicker.js` uses `qtBridge.openColorDialog()` instead when running in the wrapper.

Do not run uvicorn separately when using the native app — `qt_wrapper.py` owns the server lifecycle.

---

## Provider Payload Building

`src/llm_core.py` has three payload builders:
- `_build_openai_payload()` — works with any OpenAI-compatible API (Ollama included)
- `_build_anthropic_payload()` — extracts `role=system` messages into Anthropic's top-level `system` field, **except** tool results (prefixed with `[Tool execution results]`), which stay inline at their temporal position
- Conversation messages are `{"role": "user"|"assistant"|"system", "content": "..."}`

The Anthropic exception matters: collapsing tool results into the top-level system prompt loses round ordering and breaks multi-turn agent sessions.
