# Upstream Issue Draft: fix-brain-panel-oom

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-brain-panel-oom.md`
**Branch:** `fix/brain-panel-oom`
**Type:** Bug / Performance

---

## Title

`[Brain / Notes] Raster-tile accumulation from CSS animations causes memory growth in Qt`

---

## Body

**Install method:** Docker / manual Python / Qt wrapper

**OS / device:** Linux / macOS / Windows with Qt wrapper (most visible in embedded Chromium)

**Summary:**

Four CSS animations in the Brain and Notes panels produce unbounded raster-tile growth in the Qt wrapper. Users report 14–18 GB RSS after opening the Brain panel with many memories visible, or after interacting with the Notes panel while drag mode is active. The app must be restarted to recover.

**Root cause:**

Qt embeds Chromium without the browser process that monitors OS memory pressure. The compositor's tile manager never receives eviction signals. Any animation that produces per-frame raster tiles (main-thread painting) will accumulate those tiles indefinitely during a session.

Four animation patterns have this problem:

**Pattern A — @property --sweep on .memory-item::after (primary):**

The memory-synapse-sweep animation used `@property --sweep` (syntax: `'<percentage>'`) to animate gradient stop positions. Typed registered custom properties participate in computed-value cascading: every change to `--sweep` forces a style recalculation for every element that references `var(--sweep)` in a computed value. At 60 fps with N memories visible, that is 60 * N style recalculations per second, each producing a fresh raster tile. Additionally, `-webkit-mask` on the same pseudo-element added a second compositor pass per item per frame.

A secondary symptom: the hover rule suppressed the animation with `animation: none`, which destroys the promoted compositor layer. The layer was recreated on mouse-leave, producing the gray-frame flash users reported when mousing over memory entries.

**Pattern B — filter: drop-shadow() in @keyframes note-ai-shine:**

Every `.note-card-ai-chip svg` element runs `note-ai-shine`. Animating `filter: drop-shadow()` requires the compositor to reapply the filter every frame as values change, preventing frame elision. With many note cards visible simultaneously the per-frame filter work accumulates raster tiles that are never evicted.

**Pattern C — animation: none on .notes-quick-add hover/focus:**

The hover and focus-within rules set `animation: none` to suppress the `notes-quick-pulse` animation. `animation: none` destroys the promoted compositor layer; it is recreated on mouse-leave and focus-leave, producing a gray-frame flash on every interaction with the quick-add form.

**Pattern D — background-position animation in @keyframes notes-drag-shimmer:**

The notes-drag-shimmer animation on `.note-card::after` animated `background-position` across a 250%-wide gradient. `background-position` is not compositor-promoted; each frame re-rasterizes the gradient on every visible note card. During drag with 30+ cards visible, that is 30+ gradient repaints per frame, each depositing raster tiles the renderer never evicts.

**Expected behavior:**

CSS animations that run continuously should not cause unbounded memory growth in any deployment environment.

**Observed behavior:**

- Opening the Brain panel with many memories visible causes rapid RSS growth.
- Hovering over memory items causes gray-frame flashes.
- Initiating drag in the Notes panel while many cards are visible causes rapid RSS growth.
- The notes quick-add form flashes on hover and focus.

**Reproduction:**

1. Open the Brain panel with 20+ memories visible.
2. Let the app run for 5 minutes without interaction.
3. Check RSS via `ps aux` or Activity Monitor. Growth of several hundred MB confirms the issue.
4. More aggressive: watch the Notes panel with 20+ cards, activate drag mode, then observe RSS.

---
