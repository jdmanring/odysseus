# AI Onboarding — Odysseus Fork

## What This Project Is

Odysseus is a self-hosted AI workspace: FastAPI backend, browser-based chat UI, SQLite +
ChromaDB storage, running locally at `127.0.0.1:8000`. James runs it on KDE/Artix Linux
as his personal AI stack. This repo is a fork of `pewdiepie-archdaemon/odysseus`.

The native desktop entry point is `linux_wrapper.py` — a PyQt6 app that wraps the web UI
in a Qt window, manages server lifecycle, GPU acceleration flags, and crash recovery.

Core capabilities: chat with LLMs (Ollama/OpenAI), Plan mode, Agent mode with tools,
memory (ChromaDB RAG), model download and serving via the Cookbook, skills/slash commands.

---

## Read This First

Before writing a single line of code, read in order:

1. **`docs/fork/AGENT_CONTEXT.md`** — 60 seconds. Branch map, key tools glossary, hard
   rules, where things live, active work. This is the authoritative technical orientation.
2. **`docs/ai/agent_operational_protocols.md`** — How to collaborate with James.
3. **`docs/dev/tribal_knowledge.md`** — Non-obvious behaviors that will surprise you.
4. **`docs/audit/friction_points.md`** — Known UX problems; don't introduce more.

---

## How James Works

- **Verify before coding.** Read the relevant source first. Report what you find, then
  wait for direction before implementing. Don't assume — ask if the direction is unclear.
- **Concise responses.** No trailing summaries ("I've completed X and updated Y..."). James
  reads the diff. One or two sentences at the end max.
- **No surprises.** State your plan before executing non-trivial changes.
- **Local only.** No remote hosts unless James says so. SSH wrappers in older code are
  legacy artifacts.
- **No sudo.** Write `! sudo <command>` for James to run in his terminal.
- **No unnecessary files.** Don't create planning or analysis docs unless asked.

---

## Hard Rules

| Rule | Detail |
|------|--------|
| Nothing to upstream without authorization | No issues, PRs, comments, or pushes to `pewdiepie-archdaemon/odysseus` without James's explicit per-action approval |
| No direct upstream cherry-picks | Always go through the pipeline on `integration` branch |
| Never commit to `upstream-mirror` | It is reset-only; commits there are lost |
| No sudo | Write the command for James to run |

---

## Documentation System

This project uses a structured doc-first approach. Check here before proposing changes:

| Question | Where to look |
|----------|--------------|
| Overall architecture? | `docs/architecture/system_overview.md` |
| What's implemented vs. documented? | `docs/audit/feature_matrix.md` |
| Known friction points? | `docs/audit/friction_points.md` |
| What needs work most urgently? | `docs/audit/prioritization_matrix.md` |
| Non-obvious behaviors? | `docs/dev/tribal_knowledge.md` |
| Current bugs and active issues? | `docs/fork/issues/ISSUE_LOG.md` |
| Past failures to avoid repeating? | `docs/lessons_learned/` |
| Upstream contribution drafts? | `docs/fork/contributions/upstream/` |
| Fork-only contributions? | `docs/fork/contributions/internal/` |

---

## Key Architecture Points

| Component | Detail |
|-----------|--------|
| Backend | FastAPI at `app.py`, routes in `routes/`, SQLite at `data/app.db` |
| Frontend | Vanilla JS ES modules in `static/js/`, no build step |
| AI models | Served via Ollama, managed through the Cookbook tab |
| Downloads | `tooling/aria2c_download.py` — parallel aria2c, 4 files × 16 connections, resume via `.aria2` sidecars. No daemon, no RPC. |
| Cookbook | Background job runner using tmux sessions. Each download/serve task = one tmux session, polled every 3s via `capture-pane` |
| Memory | ChromaDB at `data/chroma/`, accessed via `routes/memory_routes.py` |
| Native app | `linux_wrapper.py` — PyQt6, starts server, opens Qt window, handles GPU flags |
| Binary management | `tooling/bin_manager.py` — auto-installs `aria2c` if missing |

---

## What NOT to Do

- Do not assume any `aria2_manager.py`, `aria2_rpc.py`, or `provisioner.py` files exist.
  They were deleted — ghosts of a discarded RPC-based architecture.
- Do not invent documentation. Only document what you can verify in the code.
- Do not file issues or PRs upstream. Stage them in `docs/fork/contributions/upstream/`.
- Do not commit without being asked.
