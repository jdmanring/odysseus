# Chat scroll / stick-to-bottom research

Research and lessons for the chat auto-scroll work. Companion to
`memory-explosion-research.md` (that doc covers memory; this one covers scroll
behaviour). Records the drift taxonomy, the architecture chosen, the external
prior art it is measured against, and the lessons learned.

Related issues and branches:

- `#49` `fix/chat-auto-scroll-threshold` — adaptive viewport-based distance
  guard (`max(300, 1.5 x viewport)`) replacing a rigid 300px threshold in
  `_smoothScrollStep()`. The stick-to-bottom work reuses this same distance as
  its pin threshold so the two mechanisms agree.
- `#103` `fix/chat-history-virtualization` scroll-down fix — `_loadNewer`
  cascade gated on `_draining` only, so scrolling down loads one batch instead
  of behaving like a scroll-to-bottom button.
- `#104` `fix/chat-stick-to-bottom` — one observer is the source of truth for
  staying pinned: it re-pins on any geometry change while pinned, covering both
  late layout growth (image decode, highlight reflow, the final block) and the
  mid-stream "Thinking" box shrink/grow. Stacks on `#49` (its pin threshold
  matches the #49 follow distance). **Supersedes the earlier
  `scrollHistorySettle` / `fix/chat-thinking-snap` approach**, which used a
  separate timed re-snap for the Thinking box only; that mechanism was folded
  into the observer so there is one mechanism, not several overlapping ones.

## Drift taxonomy

Three distinct ways the view leaves the bottom during normal operation (no
deliberate user scroll):

1. **Mid-stream placeholder transition.** The `.agent-thinking-dots` box
   appears during a streaming pause, then is removed and replaced by the real
   message (grow/shrink/grow within a few hundred ms). The throttled smooth
   scroll drops re-snaps inside its 500ms window and stops once it reaches the
   bottom. The box removal and the message growth are both geometry changes the
   observer catches (the loop has gone idle during the pause, so the observer is
   active rather than deferring).
2. **Late async growth.** Content that resizes *after* the follow loop has
   already stopped, so no scroll call follows the growth:
   - image decode replacing a fixed-size skeleton (`chatRenderer.js` `_reveal`
     reveals the `<img>` on `load` with no re-scroll),
   - syntax-highlight reflow (`deferHighlightAll` runs after render via
     rAF/idle and grows code blocks),
   - the final streamed block landing after the last `scrollHistory()` call.
3. **Single-frame overshoot.** `_smoothScrollStep` bails when the bottom is
   more than `max(300, 1.5 x viewport)` away in one frame (the #49 guard).
   During streaming the next chunk re-arms the loop, but the *last* large block
   has no follow-up call, so the view is stranded.

## Key finding: `autoScrollEnabled` was a dead gate

`autoScrollEnabled` (in `ui.js`) is set `true` at submit (`chat.js`) and is
**never set `false`** anywhere in the codebase. Nothing toggles it on user
scroll. Consequences:

- The only thing that respected "user scrolled away" was the incidental
  `maxAllowedDiff` distance bail inside `_smoothScrollStep` — not a clean
  signal.
- Any guard written as `if (!autoScrollEnabled) return;` (including the first
  version of `scrollHistorySettle`) is a no-op. The claim "gated on auto-follow
  so a user who scrolled up is never yanked" was therefore false; it worked in
  practice only because the settle fired mid-stream when the user was usually
  already pinned.

Fix: introduce a real `isPinned` flag, updated on every scroll event from the
actual distance to the bottom, and have the stick-to-bottom observer read it.
This converts the dead gate into the real source of truth.

## Architecture (stick-to-bottom observer, `ui.js`)

- `isPinned` — set on each `scroll` event: `true` when within
  `_followDistance(box)` (= `max(300, clientHeight * 1.5)`, matching the #49
  guard) of the bottom. Matching the follow distance matters: the lerp leaves
  transient gaps while catching up, so a tighter threshold would flip
  `isPinned` false mid-stream and break following.
- A `MutationObserver` on `#chat-history` (childList + subtree + characterData)
  plus a per-child `ResizeObserver`. `#chat-history` is a fixed-height scroll
  container whose messages are *direct children* with no inner wrapper, so a
  `ResizeObserver` on the container alone never fires on content growth; the
  `MutationObserver` catches DOM-driven growth (image reveal style/childList
  change, highlight reflow, new blocks) and attaches a `ResizeObserver` to each
  added child for pure layout growth.
- Re-pin is coalesced through one `requestAnimationFrame`, and **only fires
  when `isPinned` was true before the growth** — read from the last scroll
  position, never recomputed after the growth (a single large block that lands
  below the fold would otherwise measure as "far from bottom" and fail to
  re-pin precisely when needed).
- The observer **defers only while the smooth follow loop is actively
  animating** (`_scrollRafId` set) — **not** for the whole 500ms throttle
  window. This is the subtlety that lets one mechanism cover everything: during
  continuous streaming the loop stays armed (each token grows the content, so
  `diff > 1` and the rAF chain keeps running), so the observer defers and the
  gentle lerp owns the animation; during a pause the loop catches up and goes
  idle (`_scrollRafId` cleared), so the observer is active and catches the
  Thinking-box removal and any late growth. An earlier draft also deferred on
  `_scrollThrottleTimer`, which would have left the Thinking-box transition
  uncovered after folding in the old settle, so it was narrowed to
  `_scrollRafId` only.

### Why this replaced the separate `scrollHistorySettle`

The first pass (`#104`, `fix/chat-thinking-snap`) used a separate timed re-snap
(`scrollHistorySettle`) called from `_removeThinkingSpinner` to hold the bottom
across the Thinking-box transition only. Once the observer exists, that box
removal is just another geometry change it already catches, so two mechanisms
were doing overlapping work. The senior call was to consolidate *down* to the
one correct primitive rather than keep both: `scrollHistorySettle` and its call
site were removed and the behaviour folded into the observer. The alternative —
adopting the full `use-stick-to-bottom` velocity-spring engine — was rejected:
its animation polish is imperceptible under our 500ms throttle and QtWebEngine
runtime, it is a React port with a license-attribution burden, and as an
upstream PR it would rewrite the maintainer's existing scroll animation (the
`#49` loop) rather than extend it. We take the one idea that engine got right
(observer as single source of truth) without its costs.

## External prior art (measured against)

The approach matches the mainstream pattern for AI-chat stick-to-bottom:

- **`use-stick-to-bottom`** (stackblitz-labs) — the widely used React hook for
  AI chat. Uses `ResizeObserver` exclusively to detect content resize, supports
  content *shrinking* without losing stickiness, lets the user cancel
  stickiness by scrolling up, and uses a velocity-based spring scroll
  animation. Source:
  https://github.com/stackblitz-labs/use-stick-to-bottom (README:
  https://github.com/stackblitz-labs/use-stick-to-bottom/blob/main/README.md)
- **WICG ResizeObserver "chat" example** — the canonical demonstration of
  scrolling to the bottom on every resize when the user is at the bottom.
  Source: https://rawgit.com/WICG/ResizeObserver/master/examples/chat.html
- **`vue-stick-to-bottom`** (cwandev) — Vue port of the same idea. Source:
  https://github.com/cwandev/vue-stick-to-bottom
- **"Anchor scroll at the bottom of the container with dynamic content"**
  (dev.to/hugaidas) — bottom-anchor + observer pattern writeup. Source:
  https://dev.to/hugaidas/anchor-scroll-at-the-bottom-of-the-container-with-dynamic-content-2knj
- **"Intuitive Scrolling for Chatbot Message Streaming"** (tuffstuff9) —
  distinguishing user vs programmatic scroll without debouncing. Source:
  https://tuffstuff9.hashnode.dev/intuitive-scrolling-for-chatbot-message-streaming
- **`overflow-anchor` / scroll anchoring** (CSS-Tricks almanac) — the native
  CSS feature that prevents content *above* the viewport from shifting the
  view; complementary to bottom-pinning but not a substitute (no Safari
  support, and it does not pull the view *to* the bottom). Source:
  https://css-tricks.com/almanac/properties/o/overflow-anchor/

Where this implementation differs deliberately: `use-stick-to-bottom` runs its
own velocity-spring scroll animation and a debounce-free user-intent detector.
Here the existing `_smoothScrollStep` lerp already owns the streaming animation,
so the observer does not animate — it only fills the late-growth gap the lerp
leaves, and defers to the lerp while it runs. User intent is read from the
`isPinned` distance flag rather than a velocity heuristic. This is a simpler
mechanism justified by the narrower job; the trade-off is that it cannot
distinguish a fast programmatic scroll from a user scroll as precisely as a
velocity model, which is acceptable because the only programmatic scroller (the
lerp) stays within the pin distance and the observer defers while it runs.

## Lessons learned

- **Verify a "flag" is actually toggled before relying on it.** A guard that
  reads a variable nothing ever sets is dead code that *looks* like a
  safeguard. Grep every assignment, not just the read site, before claiming a
  behaviour is gated.
- **Source-text tests prove presence, not behaviour.** The pytest guards for
  this work assert that the code strings exist; they cannot prove the view
  holds. Behavioural claims need an in-app before/after with a concrete repro
  (here: a reply ending in a large code block, or a message with an image
  attachment — late-growing content). Record which claims are still
  behaviourally unverified.
- **Re-pin gating must read the pre-growth state.** Measuring distance-to-bottom
  inside the observer callback (after growth) defeats the fix for the exact
  case it targets (a large final block), because the growth has already pushed
  the bottom away.
- **Prefer one growth-driven mechanism over per-producer scroll calls.** A
  single observer covers images, highlight reflow, math, and final blocks at
  once; scattering `scrollHistory()` calls across each producer is fragile and
  was explicitly rejected.

## Verification status

- The Thinking/"Processing request"/"Generating response" transitions were
  behaviourally confirmed to hold the bottom under the earlier
  `scrollHistorySettle` pass. After folding that into the observer, those same
  transitions need a **re-confirmation** under the consolidated mechanism, since
  it is now the observer (not a timed settle) that holds them.
- Stick-to-bottom observer + `isPinned`: **behavioural verification pending.**
  Repro that does not require image generation (which is currently
  inpaint-scoped only — see below): send a prompt whose reply ends in a large
  code block (highlight reflow), or attach/paste an image into a message (decode
  growth), and confirm the view stays pinned through the late growth; also
  re-run an agent/tool turn to confirm the Thinking-box transition still holds.
  Source-text guards only prevent silent deletion.

## Aside: image generation is inpaint-scoped (separate issue)

The Settings → Image Generation panel (`static/js/settings.js` `initImageSettings`)
is scoped to **inpainting** only — it lists inpaint-compatible Stable Diffusion
models and shows hardcoded fallbacks as "(not detected)" when none are served,
with no general provider/model path for chat "generate an image" requests. This
is why image generation cannot be used to test the scroll fix, and is a separate
labelling/UX bug worth its own issue (not part of the scroll work).
