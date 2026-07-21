> **⚠️ REFRAMED (2026-07-07).** The MessageWindow-port approach was abandoned after
> finding the maintainer's own history pager (`45ee5a71`) owns this code region. The
> problem (unbounded DOM growth, jdmanring#2) is now addressed by a small eviction
> graft on top of that pager — see `fix-history-route-shadowing.md` (prerequisite)
> and branch `fix/chat-history-dom-eviction`. jdmanring#2 is currently CLOSED but is
> upstream-candidate with no PR filed — needs reopening per the issue-lifecycle rule.

# Upstream Issue Draft: fix-dom-oom-virtualization

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-dom-oom-virtualization.md`
**Branch:** `fix/dom-oom-virtualization`
**Type:** Bug

**Related upstream reports (reference in body):**
- #2869 — "Chat Freeze" (freeze after 20 messages in agent chat — same root cause)
- #3746 — "Website crashing" (crash after deep research + continued chatting — same root cause)

---

## Title

`[Chat] Renderer OOM / freeze on long sessions — chat history DOM grows without bound`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Browser (if applicable):** Any Chromium-based renderer (including QtWebEngine)

**Steps to Reproduce:**

**Mode 1 — load crash (existing session):**
1. Run an agentic session that generates 200+ messages (tool calls + responses add 5–7 DOM nodes each).
2. Close the chat and reopen it to reload from the database.

**Mode 2 — accumulation crash (active session):**
1. Leave a long agentic run going without reloading the page.
2. Continue chatting as the run progresses.

**Expected:** The chat history renders and remains interactive regardless of session length.

**Actual:** The renderer runs out of memory and crashes. On Chromium/QtWebEngine the browser console shows a V8 Oilpan OOM error. For sufficiently large sessions, the crash occurs during initial load before any new messages are sent. This is reproducible on sessions saved to the database — any long agent run can produce an unloadable session.

**Logs / Error Output:**
```
V8::FatalProcessOutOfMemory — Oilpan ran out of memory
```
(Chromium / QtWebEngine renderer process crash)

**Additional context:** The chat history DOM is unbounded — every message appended to the session adds nodes permanently with nothing ever removed or recycled. Agent sessions are especially severe: each tool call + result pair produces 5–7 nodes (call block, result block, thinking block, status indicators, connectors). A 100-message agent session easily produces 500–700 DOM nodes, and sessions in the database regularly exceed this.

Related reports: #2869 describes a chat freeze after 20 messages in agent chat. #3746 describes a crash after deep research followed by continued chatting. Both are consistent with unbounded DOM growth as the root cause.
