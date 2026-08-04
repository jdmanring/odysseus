# PR Draft: fix/tasks-clock-repaint -> odysseus-dev/odysseus:dev

**Branch:** `fix/tasks-clock-repaint`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 2 commits, 4 files, +72/-2

---

## Title

`fix(tasks): clock at minute resolution, written only on change`

---

## Summary

### Problem

The Tasks panel header clock shows live **seconds**. The Tasks modal is
draggable, so it is its own compositor layer — and the clock shared that layer,
so each one-second `textContent` write re-rastered the whole ~600x848 modal
backing texture and churned a detached text node.

Measured with Tasks open: **~1.75 MB/s**, the dominant residual memory producer
in that state. A purge-recheck confirmed it is reclaimable cache rather than a
leak, but reclaimable churn is still work the machine does forever for a display
nobody reads at second precision.

### Two commits, and the order is the point

**First**, CSS layer isolation: give the clock its own layer so its repaint stops
re-rastering the modal. This cut the per-repaint **area** — and the climb
persisted, because the per-second **frequency** was untouched.

**Then**, the actual fix: drop to minute resolution and write `textContent` only
when the string changes. All but roughly one tick per minute becomes a no-op — no
write, no repaint, no detached node.

That sequence is worth keeping in the history because it is the general lesson:
isolating a repaint makes it cheaper, eliminating the producer makes it free. The
first change is still correct and is retained; it just was not sufficient alone.

---

## Verification

**3 passed**, measured 2026-08-03, across the JS behaviour guard (writes only on
change) and the CSS layer-isolation guard.

---

## Scope

`static/js/tasks.js`, `static/style.css` (+8), two test files.
