# AI Onboarding — Odysseus Fork

> **Start here.** This primer gives you the code mental model and fork context.
> Hard rules are in `AI_RULES.md` and `CLAUDE.md` (auto-loaded). Active work: `docs/fork/active-work.md`.
> Branch and pipeline rules: `docs/dev/git-branch-workflow.md` — read before touching any branch.

> **Fork purpose:** This fork is a contribution workbench, not a divergent product. Every fix,
> feature, and document — including this file — defaults to upstream-candidate. Fork-only is
> the narrow exception: the sync pipeline, fork CI, and fork management docs. See `CLAUDE.md`
> for the full list. When in doubt, assume upstream-candidate.

---

## What It Is

Self-hosted AI workspace. FastAPI backend + browser UI, running locally at
`127.0.0.1:8000`. Supports chat (Ollama/OpenAI/Anthropic), Agent mode (tool use),
Plan mode, memory (RAG via ChromaDB), model downloads, TTS/STT, MCP servers,
calendar, email, notes, documents, gallery. Single-user.

On Linux it also runs as a native Qt app (`linux_wrapper.py`) — PyQt6 wraps the
web UI in `QWebEngineView`, manages server lifecycle, GPU flags, crash recovery.

---

## How a Chat Request Flows

```
User types → chat.js → POST /api/chat_stream
  → chat_routes.py → src/llm_core.py → LLM API (Ollama/OpenAI)
  → SSE stream back → chatStream.js renders tokens live
  → on complete: message saved to SQLite via core/database.py
```

Agent mode replaces `llm_core.py` with `src/agent_loop.py`, which calls tools,
feeds results back, and loops until the model stops calling tools.

---

## Code Layout

**Backend**

| Path | Role |
|------|------|
| `app.py` | Thin FastAPI orchestrator — imports all routers, configures middleware, serves static |
| `core/database.py` | SQLAlchemy models + SQLite session factory. All persistent data except embeddings |
| `core/models.py` | Pydantic models shared across routes |
| `core/auth.py` | Auth middleware (optional — off by default in `.env`) |
| `routes/` | One file per feature area. Each registers an `APIRouter` included by `app.py` |
| `src/` | Business logic called by routes — `llm_core.py`, `agent_loop.py`, `embeddings.py` |
| `mcp_servers/` | MCP server implementations (email, image gen, memory, RAG) |
| `tooling/` | Standalone utilities — `aria2c_download.py`, `bin_manager.py`, `hf_url_resolver.py` |

**Frontend**

No bundler. Plain ES modules loaded directly from `static/js/`. `static/index.html`
is the SPA shell. `init.js` boots the UI.

| File | Role |
|------|------|
| `init.js` | App bootstrap — event wiring, initial state load |
| `chat.js` | Chat input, send logic, session switching |
| `chatStream.js` | SSE consumer — feeds tokens to renderer |
| `chatRenderer.js` | Turns message objects into DOM |
| `cookbook*.js` | Model management UI (6 files — see Cookbook below) |
| `theme.js` + `colorPicker.js` | Theme system and color picker |
| `qt-bridge.js` | Non-module — sets up `window.qtBridge` for native Qt calls |
| `platform.js` | Detects `window.__QT_WRAPPER__` to gate Qt-only features |

---

## Configuration

| Item | Location | Note |
|------|-----------|------|
| API Keys / Secrets | `.env` | Base environment variables (see `.env.example`) |
| App Settings | `data/settings.json` | Persistent user-configurable settings |
| Port Config | `app.py` / `.env` | Default is `8000` |

## Data Storage

| What | Where |
|------|-------|
| Conversations, sessions, messages | SQLite `data/app.db` via SQLAlchemy |
| Memory / RAG embeddings | ChromaDB `data/chroma/` |
| User preferences | `data/settings.json` |
| User profile data (theme, etc.) | `data/user_prefs.json` — per-user keyed by email |
| Custom themes | `data/user_prefs.json` → `custom-themes` per-user, also in browser localStorage synced via `/api/prefs/custom-themes` |
| Current theme (active) | `data/user_prefs.json` → `theme.name` per-user |
| Current theme colors | `data/user_prefs.json` → `theme.colors` per-user (includes `advanced` overrides) |
| Uploaded files | `uploads/` |
| HuggingFace model cache | `~/.cache/huggingface/hub/` (standard HF layout) |

**Critical: `data/user_prefs.json` is the source of truth for the active theme.** When asked to update a theme or find current colors, read this file first. Do not guess colors — look them up from the user's actual profile data.

---

## The Cookbook (most complex subsystem)

Lets users download, serve, and manage local AI models.

| JS File | Role |
|---------|------|
| `cookbook.js` | Entry point, model list, tab switching |
| `cookbookDownload.js` | Download form, initiates downloads |
| `cookbookRunning.js` | Live download cards — polls `/api/cookbook/download/status`, renders aria2c progress |
| `cookbookServe.js` | Serve/stop model, port management |
| `cookbookSchedule.js` | Scheduled download jobs |
| `cookbookProgressSignal.js` | Stale-download detection |

**Download pipeline:** `cookbookDownload.js` → `POST /api/cookbook/download/start` →
`cookbook_routes.py` spawns `aria2c_download.py` as a subprocess →
`cookbookRunning.js` polls `GET /api/cookbook/download/status/{session_id}` every 2s →
parses aria2c stdout, updates progress cards in-place. Supports gated models (via token injection) and deep GGUF subdirectory resolution.

**aria2c progress format** (non-obvious — will bite you):
Lines look like `·[#a1b2c3 1GiB/5GiB(21%) CN:4 DL:50MiB ETA:1m20s]` followed by
`·FILE: /path/to/file`. The leading space before `[#` is literal — regexes must use
`^\s*\[#` not `^\[#`.

---

## Fork Additions (James's code, not in upstream)

**Entirely new files:**
- `linux_wrapper.py` — the entire Qt native app
- `static/js/qt-bridge.js` — QWebChannel setup
- `tooling/aria2c_download.py` — HF download via aria2c
- `tooling/bin_manager.py` — auto-install external binaries
- `tooling/hf_url_resolver.py` — resolve HuggingFace signed URLs

**Heavily modified from upstream:**
- `static/js/cookbookRunning.js` — download card UI, per-file rows, `_dlFileTracker`
- `static/js/colorPicker.js` — eyedropper uses Qt native dialog via `qtBridge`

Full divergence record: `docs/fork/changes-from-upstream.md`

---

## Things That Will Bite You

- **No bundler.** A new JS file needs a `<script>` tag in `index.html`. ES imports
  between `static/js/` files work; `node_modules` doesn't exist.

- **`linux_wrapper.py` starts the server.** When running the native app, don't also
  run uvicorn — the wrapper spawns it and owns its lifecycle.

- **`QWebEngineView` is Chromium but not a browser.** Web EyeDropper API is missing.
  Check Qt compat when adding UI features touching Qt code paths.

- **`_dlFileTracker` is module-level state.** Persists across poll ticks to accumulate
  completed-file bytes. Resetting it breaks the overall model progress percentage.

- **HF signed URLs expire.** `hf_url_resolver.py` re-resolves fresh on every download
  start. Never cache resolved URLs across sessions.

---

## Tooling Index

The `tooling/` directory contains critical utilities. Check here before writing new scripts:
- `aria2c_download.py`: Specialized HF download logic with progress parsing.
- `bin_manager.py`: Handles external binary installation/verification.
- `hf_url_resolver.py`: Resolves signed HF URLs.

## Fork Pipeline — Mental Model

The fork has three main operations. All three are covered with exact commands in
`AI_RULES.md` under "Fork Operations — Step-by-Step Procedures".

**Ingest upstream changes:**
```
upstream/dev → upstream-mirror → sync/staging-* → (3 gates) → integration → develop
```
Run: `git checkout integration && python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --skip-tests`
Then: `git checkout develop && git merge integration`

**Rebase a staging branch** (when upstream-mirror has advanced since the branch was created):
```bash
git checkout fix/branch-name
git rebase upstream-mirror
# Resolve conflicts: keep our fix + keep upstream's other changes (not just one or the other)
# Then verify: git diff upstream-mirror fix/branch-name
```

**Create new upstream-candidate work** (branch from upstream-mirror, NEVER from develop):
```bash
git checkout -b fix/new-thing upstream-mirror
# ... do work, commit ...
git checkout develop && git cherry-pick <hash>   # put it in develop too
```

**Branch health check** — run this before any pipeline operation:
```bash
git fetch upstream
git log --oneline upstream/dev ^upstream-mirror        # new upstream commits to ingest?
git log --oneline integration ^develop                  # integration ahead of develop?
git log --oneline upstream-mirror..fix/branch-name      # staging branch commit count?
```

---

## Where to Go Next

| Need | File |
|------|------|
| What's different from upstream? | `docs/fork/changes-from-upstream.md` |
| What's being worked on? | `docs/fork/active-work.md` |
| Open bugs? | `docs/fork/issue-tracker.md` |
| How to contribute upstream? | `docs/fork/upstream/how-to-contribute.md` |
| Architecture deep-dive? | `docs/project/architecture.md` |
| Things that will surprise you? | `docs/project/non-obvious-behaviors.md` |
| Git workflow and branches? | `docs/dev/git-branch-workflow.md` |
| Running locally? | `docs/dev/local-setup-and-running.md` |
| **Fork pipeline procedures (exact commands)** | **`AI_RULES.md` — Fork Operations section** |
| **Where user theme/profile data lives** | **`data/user_prefs.json`** (see Data Storage above) |

## Lessons Learned (things that bit us — read before repeating)

**Never edit `develop` directly for upstream-candidate work.** Always work on the proper branch (from `upstream-mirror`), commit there, then cherry-pick to `develop`. Editing develop directly creates untracked work that has no branch, no issue, and no PR staging. If you find yourself editing develop, stop — you're on the wrong branch.

**Always look up user data from `data/user_prefs.json` before guessing.** Theme colors, user preferences, and profile data are stored there. Do not invent colors or use colors from a different theme. Read the file, extract the exact values the user is actually using, then apply them.

**The running app's user profile is the source of truth.** If a user says "I'm using theme X", the exact colors are in `data/user_prefs.json` under their email → `theme.colors`. For custom themes, also check `custom-themes` under their email.
