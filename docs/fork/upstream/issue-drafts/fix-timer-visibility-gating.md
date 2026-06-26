# Upstream Issue Draft: fix-timer-visibility-gating

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-timer-visibility-gating.md`
**Branch:** `fix/timer-visibility-gating`
**Type:** Performance

## Title
`perf: visibility-gate perpetual background timers (modalManager scan, email/tasks polls)`

## Body
Several timers run regardless of window visibility, keeping a backgrounded app awake:
- `modalManager.js` `setInterval(_scanAndWire, 1000)` runs forever (idempotent re-wiring; nearly every tick wasted).
- `emailInbox.js` unread refresh (60s) and `tasks.js` notif poll (30s) fire network/work while the tab is hidden. `calendar.js` already gates on `document.visibilityState`.

**Fix:** pause the modalManager interval when `document.hidden` (resume with a catch-up scan on `visibilitychange`); early-return the email/tasks polls when not visible (the pattern calendar.js already uses). Behaviour unchanged while visible. Affected: `static/js/modalManager.js`, `static/js/emailInbox.js`, `static/js/tasks.js`.
