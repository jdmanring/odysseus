# System Issue Log

## [ISSUE-001] Renderer OOM Crash — Blank Page After Long Agent Sessions
**Status:** Resolved-Partial  
**Severity:** High  
**Reported:** User (initially as "UI flashing black")  
**Resolved-by:** 2026-06-06 session  

### Root Cause (confirmed)
Two distinct failure modes, both caused by unbounded DOM growth in `#chat-history`:

1. **Gradual accumulation** — a 20-round agent session built up 40+ message bubbles and tool-call DOM subtrees until the V8 Oilpan C++ heap (manages DOM objects) exhausted its virtual address reservation. The GC freed 419 MB → 16 MB just before the fatal allocation, confirming it was a reservation limit not physical RAM.

2. **Bulk session load** — after restarting, `selectSession()` rendered the entire previous session history at once and ran `hljs.highlightElement()` on every code block. A fixed-size Oilpan allocator pool was exhausted at only 78 MB, 11 minutes after startup.

Both crashes confirmed via V8 log evidence: `ERROR:v8_initializer.cc:844] V8 process OOM (Oilpan: Large allocation. Ran out of reservation)`.

### Evidence
- Crash 1: 2026-06-06 20:51:34, renderer pid 13269, ~52 min uptime, 419 MB heap
- Crash 2: 2026-06-06 22:47:12, renderer pid 13699, ~11 min uptime, 78 MB heap  
- Source: `~/.local/share/sddm/wayland-session.log` (Chromium stderr)

### Fix Applied (Partial)
- **`linux_wrapper.py`** (commit `564dd5c`): `renderProcessTerminated` signal handler auto-reloads on crash; 60s memory monitor; OS-level fd redirect so renderer logs go to `logs/wrapper_system.log`; uvicorn access log enabled to `logs/server_access.log`.

### Fix Applied (Partial) — streamingTTS scope
- **`chat.js`** (commit `9fabdc6`): `streamingTTS` hoisted from `const` inside try to `let` before try — fixes ReferenceError in catch block on every stream error.

### Fix Pending — DOM virtualization
- **Branch:** `fix/dom-oom-virtualization` (in progress)
- `MessageWindow` class with IntersectionObserver load pagination + live pruning
- Detailed plan: `personal_docs/plan-dom-virtualization.md`
- Upstream staging: `docs/fork/contributions/upstream/06-dom-oom-virtualization.md`

---

## [ISSUE-002] Project Not Self-Describing for AI Agent Onboarding
**Status:** Open  
**Severity:** Medium  
**Reported:** James (2026-06-07)  

### Problem
When an AI agent starts a new session on this project, it has no intuitive entry point
that tells it: what the project is, what's in progress, what the rules are, and where
to find everything. The agent has to rediscover context from scratch each session —
reading memory files, scanning dirs, looking at git log. This costs time and causes
mistakes (e.g. not knowing aria2c is the turbo downloader's core tool, not understanding
the upstream contribution workflow without reading CONTRIBUTING.md manually).

The project should have a single top-level orientation document that an agent can read
in the first 30 seconds of a session and immediately know:
- What this repo is and what it does
- The two-repo model (fork vs upstream)
- Active branches and what's on each
- Where the rules live (contribution workflow, working conventions)
- Where in-progress work is tracked
- Key tooling and what it does (aria2c, QWebChannel, etc.)
- What NOT to do (never sudo, never file upstream without authorization)

### Fix Needed
Create `docs/fork/AGENT_CONTEXT.md` — a short, dense orientation document that:
1. Describes the project in 2-3 sentences
2. Lists the two remotes and their roles
3. Maps the branch structure
4. Links to: UPSTREAM_CONTRIBUTION_WORKFLOW.md, testing.md, ISSUE_LOG.md, CHANGELOG.md
5. Explains key tools (aria2c = turbo downloader via BinManager; QWebChannel = JS↔Python bridge; QWebEngineView = Qt browser wrapper)
6. States the hard rules (no sudo, no upstream filing without James, verify before coding)
7. Lists active work and where to find task tracking

This file should be the FIRST thing any agent reads after MEMORY.md.
