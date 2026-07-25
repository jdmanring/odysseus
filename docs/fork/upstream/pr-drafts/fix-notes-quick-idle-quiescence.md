# Upstream PR Draft: fix-notes-quick-idle-quiescence

**Branch:** `fix/notes-quick-idle-quiescence` (from `upstream-mirror`)
**Target:** `odysseus-dev/odysseus:dev`
**Fixes:** #_ (file issue-drafts/fix-notes-quick-idle-quiescence.md first)
**Filing notes:** Single concern, one commit. Introduces a reusable `html.app-blurred` primitive.

---

## Title

`perf(notes): pause quick-add ambient animations when the window is backgrounded`

## Description

A backgrounded/unfocused window should not run decorative animations. The notes quick-add pulse
and caret animate perpetually while visible (pausing only on hover/focus).

**Change:**
- `static/js/ui.js`: toggle `html.app-blurred` on window `blur`/`focus` + `visibilitychange`
  (`document.hidden || !document.hasFocus()`). Reusable primitive.
- `static/style.css`: pause the quick-add element and both pseudo-elements
  (`animation-play-state: paused`) under `html.app-blurred`.

`animation-play-state` (not `none`) so it resumes cleanly on refocus.

## Tests

`tests/test_idle_quiescence_css.py` (3 static guards): the toggle fires on blur + visibility;
CSS pauses (not disables) under `app-blurred`; gate covers element + both pseudo-elements.

## Risk
Low: only affects decorative animations, only while backgrounded; pauses (resumes on focus).
