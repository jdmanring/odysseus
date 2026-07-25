# Upstream PR Draft: fix-timer-visibility-gating

**Branch:** `fix/timer-visibility-gating` (from `upstream-mirror`)
**Target:** `odysseus-dev/odysseus:dev`
**Fixes:** #_ (file issue-drafts/fix-timer-visibility-gating.md first)
**Filing notes:** One concern (visibility-gate background timers); JS-only.

## Title
`perf: visibility-gate perpetual background timers`

## Description
A backgrounded app should not wake/poll. modalManager pauses its 1s auto-wire scan when `document.hidden` (resumes with a catch-up scan on return); the email unread (60s) and tasks notification (30s) polls early-return when the tab is not visible, matching `calendar.js`. Behaviour unchanged while visible; no modal-wiring regression (the poll logic is untouched, only paused when hidden).

## Tests
`tests/test_timer_visibility_gating.py` (3 static guards): modal scan pause/resume; email + tasks polls gated on `visibilityState`.

## Risk
Low; visible behaviour unchanged; only stops work/wakeups while hidden.
