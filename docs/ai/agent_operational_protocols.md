# Agent Context — Odysseus Fork

Read this first. It takes 60 seconds and tells you everything you need to operate correctly.

---

## What This Is

A fork of `pewdiepie-archdaemon/odysseus` — a self-hosted AI workspace (FastAPI backend,
browser-based UI, Python 3.14). James uses this as his personal AI stack. The goal is to
run a full-featured AI workspace locally on KDE/Artix Linux, and contribute improvements
back to the upstream project over time.

**James's fork:** `github.com/jdmanring/odysseus` (remote: `origin`)  
**Upstream source:** `github.com/pewdiepie-archdaemon/odysseus` (remote: `upstream`)

These are entirely separate repositories. Pushing to `origin` is routine development.
Sending **anything** to `upstream` (issues, PRs, comments) requires James's explicit
per-action authorization. An agent never files upstream issues or PRs directly.

---

## Branch Structure

| Branch | Purpose |
|--------|---------|
| `upstream-mirror` | Reset to `upstream/dev` on every sync — never commit here |
| `integration` | Vetted upstream changes that passed all pipeline gates |
| `develop` | Active fork development — primary working branch |
| `main` | Stable release of the fork |
| `feat/*` / `fix/*` | Feature and fix branches — merge to `develop` when complete |

Upstream has its own two-branch model: `dev` (all PRs land here) and `main` (stable).
All upstream PRs target `upstream:dev`, never `upstream:main`.

---

## Key Tools and What They Do

| Tool / Component | What It Is |
|-----------------|------------|
| `linux_wrapper.py` | PyQt6 app — wraps Odysseus web UI in a native Qt window. Manages server lifecycle, GPU flags, crash recovery, logging. The native desktop entry point. |
| `QWebEngineView` | Qt's Chromium browser widget — renders the Odysseus web UI inside the native window |
| `QWebChannel` | Qt mechanism for bidirectional JS↔Python messaging — used to bridge web UI to native OS APIs (e.g. color picker dialog) |
| `tooling/bin_manager.py` | Manages external binaries (auto-install if missing, path discovery). Currently used for `aria2c`. |
| `aria2c` | Multi-protocol download utility. Used by the aria2c downloader to fetch HuggingFace model weights with 16 parallel connections and resume support. Replaces the unreliable `hf_transfer` Rust accelerator. |
| `tooling/aria2c_download.py` | Entry point for the aria2c download feature. Resolves the binary via BinManager, the URL via HfUrlResolver, then builds and runs the aria2c command itself. Invoked as a script from `routes/cookbook_routes.py`, not imported. |
| `tooling/sync-upstreams/upstream_ingest_pipeline.py` | Syncs `upstream/dev` through 3 gates (syntax, lint, tests) before promoting to `integration` branch. Run this, never cherry-pick upstream directly to `develop`. |
| `static/js/qt-bridge.js` | Non-module script that sets up QWebChannel and exposes `window.qtBridge` for native OS calls from web JS |
| `IntersectionObserver` | Browser API used for DOM virtualization — loads older chat messages on scroll, no new dependencies needed |

---

## Hard Rules

1. **No sudo.** Write `! sudo <command>` for James to run. Never execute elevated commands directly.
2. **Verify before coding.** Read the relevant source first; report findings before implementing.
3. **Report before implementing** non-trivial changes. James confirms direction first.
4. **Never file upstream issues or PRs.** Stage them in `docs/fork/contributions/upstream/`. James files.
5. **Never push to `upstream-mirror`.** This branch is reset-only; commits there are lost.
6. **Never cherry-pick from upstream directly to `develop`.** Use the pipeline via `integration`.

---

## Where Things Live

| What | Where |
|------|-------|
| Active issue tracking | `docs/fork/issues/ISSUE_LOG.md` |
| Upstream contribution drafts | `docs/fork/contributions/upstream/NN-name.md` |
| Internal (fork-only) contribution docs | `docs/fork/contributions/internal/NN-name.md` |
| Upstream contribution workflow & rules | `docs/fork/UPSTREAM_CONTRIBUTION_WORKFLOW.md` |
| Staging index (all PRs at a glance) | `docs/fork/PR_STAGING.md` |
| Testing standards | `docs/fork/testing.md` |
| Change history | `docs/fork/CHANGELOG.md` |
| DOM virtualization plan | `personal_docs/plan-dom-virtualization.md` |
| Crash recovery plan (implemented) | `personal_docs/plan-crash-recovery.md` |
| Build/install reference | `docs/fork/build-linux-app.md` |

---

## Active Work (as of 2026-06-07)

| Item | Branch | Status |
|------|--------|--------|
| DOM virtualization — Phase 1 (load pagination) | `fix/dom-oom-virtualization` | In progress |
| DOM virtualization — Phase 2 (live pruning) | `fix/dom-oom-virtualization` | Pending |
| aria2c downloader | `develop` | Complete — upstream PR staged |
| streamingTTS scope fix | `develop` | Complete — upstream PR staged |
| Crash recovery handler | `develop` | Complete (commit `564dd5c`) |
| Native Linux app | `develop` | Active development |

---

## Local Install

- Python 3.14.5 at `/usr/bin/python3`, venv at `venv/`
- App server: `venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000`
- Native wrapper: `/usr/bin/python3 linux_wrapper.py` (starts server + opens Qt window)
- Logs: `logs/wrapper_system.log` (all Chromium + Python output), `logs/server_access.log`
- Data: `data/app.db` (SQLite), `data/chroma/` (ChromaDB), `data/settings.json`
