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

### Fix Pending (Full)
- **DOM virtualization** — `MessageWindow` class with IntersectionObserver-based load pagination + live pruning. Detailed plan: `personal_docs/plan-dom-virtualization.md`. Upstream issue filed: pewdiepie-archdaemon/odysseus (see contribution doc `docs/fork/contributions/upstream/06-dom-oom-virtualization.md`).
- **`streamingTTS` scope fix** — secondary bug in `chat.js:2923`, 3-line fix. Upstream issue filed (see `docs/fork/contributions/upstream/07-streamingtts-scope-fix.md`).

### Secondary Bug Found During Investigation
`streamingTTS` declared with `const` inside `try` block (chat.js:1077), referenced in `catch` block (line 2923). `const` is block-scoped — causes `ReferenceError` on every stream error (503, network failure, etc.), aborting the catch handler early. Confirmed 6 occurrences in one session's logs.
