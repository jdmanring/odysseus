# Upstream Issue Draft: fix-notes-quick-idle-quiescence

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-notes-quick-idle-quiescence.md`
**Branch:** `fix/notes-quick-idle-quiescence`
**Type:** Performance

---

## Title

`perf(notes): quick-add pulse/caret animate perpetually — pause when the window is backgrounded`

---

## Body

**Area:** UI / Notes / performance

**Problem**

The notes quick-add box runs two perpetual decorative animations — `notes-quick-pulse` (idle
glow) and `notes-quick-caret` (a fake blinking caret hint) — that only pause on hover/focus.
While the Notes panel is open they animate forever, keeping the compositor awake even when the
window is **backgrounded/unfocused** and nobody is looking. A small battery/power cost, and one
of several ambient animations that summed badly under software rendering.

**Expected:** a backgrounded/unfocused window should not run decorative animations.

**Fix:** add a small global signal — toggle `html.app-blurred` on window blur / page hide
(`visibilitychange` + `hasFocus`) — and pause the quick-add animations under it via
`animation-play-state: paused`. Reusable primitive for other ambient animations.

**Affected:** `static/js/ui.js`, `static/style.css`.
