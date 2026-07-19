# DOM-virtualization manual pass — scripted checklist (plan 3.5 remainder)

The five items automation cannot cover: real input hardware, human perception, and the
QtWebEngine runtime. Everything else is already asserted by the suites (soak, paging,
Playwright, a11y). One pass through this list, ~10 minutes, with the Qt app open.

Record results by ticking the boxes and filling the date line at the bottom; the plan's
3.6 exit check points here.

## Setup (once, ~1 minute)

1. Odysseus running (the Qt app, not a browser tab) on a checkout of current `develop`.
2. Open your longest real session (150+ messages — e.g. the 308-message agent session
   from the OOM investigation). Real content beats seeded content here; that's the point
   of the manual pass.
3. Optional measurement aid, in a terminal (read-only, RSS + DOM counters one-shot).
   Paste exactly this line — do NOT include backticks or quotes; in zsh, backticks
   execute the command and then try to run its *output* as a command:

   ```
   venv/bin/python tooling/mem-probe.py counters
   ```

   For a live DOM-children + distance-from-bottom readout while you scroll (one line
   per second for 60 seconds), paste this in a second terminal:

   ```
   venv/bin/python tooling/mem-probe.py chatdom -d 60
   ```

   Children should stay ≤ ~145 no matter how far you scroll; "px from bottom: 0" means
   you're pinned to the newest message.

## The five checks

### 1. Touch/wheel input feel
- [ ] Wheel-scroll up through history at reading speed: older batches page in **in
      place** — the content under your cursor does not jump or reflow away.
- [ ] Flick fast to the top repeatedly: no stutter, no blank white regions that linger,
      no scroll position "fighting back."
- [ ] If you have a touchpad: two-finger scroll both directions, same criteria (inertial
      scrolling is the case Chromium's synthetic wheel events can't reproduce).
- [ ] Scroll up *while a reply is streaming*, then back down: stream continues, no jump.

**Pass:** paging is invisible except for content appearing; no perceptible hitch.

### 2. Flash-on-reload perception
- [ ] Switch away to another session and back, 3-4 times.
- [ ] Watch the instant of load: the view must land at the **bottom** (newest message)
      with no visible intermediate state — no flash of the top of history, no
      top-then-snap-down, no white flash longer than a frame.

**Pass:** every switch lands composed at the bottom in one visual step.

### 3. Lazy-image decode on real large images
- [ ] Use (or make) a session containing several large images — paste 2-3 multi-MB
      screenshots into a throwaway session and exchange a dozen messages after them so
      they start off-window.
- [ ] Scroll up into the image region at reading speed: images decode without shoving
      your scroll position (the img.onload re-snap compensation should absorb layout
      shifts).
- [ ] Scroll past them to the very top, then back down: no permanent blank boxes.

**Pass:** no scroll displacement you notice, no unrecovered blanks.

### 4. Scroll-to-bottom affordance discoverability
- [ ] Scroll far up into history. Without hunting: is the scroll-to-bottom button
      visible and obviously "take me back to now"?
- [ ] Click it: lands at the newest message (drains all intermediate batches, no
      stopping partway), and stays pinned when the next reply streams in.

**Pass:** you'd find the button without being told, and one click ends at the true
bottom.

### 5. QtWebEngine ecological validity (runs alongside 1-4)
- [ ] All of the above was done in the Qt app itself — that *is* the check; the suites
      run stock Chromium.
- [ ] Glance at memory while doing it: run the mem-probe counters line from Setup step 3
      before and after checks 1-4 on the long session. RSS should be flat-ish (tens of
      MB drift is normal), not stepping up hundreds of MB as you page through history.
- [ ] If you exchange 80+ messages in one sitting eventually: confirm the eviction
      notice ("↑ N earlier messages not shown — reload session to see all") reads
      correctly when it appears. Not required for this pass; the soak asserts the
      mechanics, only the wording/placement needs human eyes once.

**Pass:** no Qt-specific misbehavior vs. what the suites show in Chromium; memory flat.

## Result

- Date of pass: ____________
- Checkout (develop commit): ____________
- Outcome: PASS / issues found (file a fork issue per item and list here):
