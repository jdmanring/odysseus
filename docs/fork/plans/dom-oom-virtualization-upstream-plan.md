# Plan: make `fix/dom-oom-virtualization` (#2) a perfect, provable upstream contribution

Goal: turn the chat-history virtualization into a contribution that can be filed upstream
with confidence next to open PR #4661, where every claim of independence and superiority is
documented, measured, and backed by verified sources, and where the user-facing behaviour is
correct and pleasant. Nothing here is filed by an agent; this prepares the artifact for the
human to file.

Status of inputs (already done):
- Branch contamination removed (the fork PR-draft `.md` is no longer on the branch).
- Provenance reframed to the precise truth (see Part 1). Earlier "full code independence" was
  wrong and is corrected.

---

## Part 1 — Provenance and attribution (make it irrefutable, and honest)

The claim must be exactly true, no more and no less, because a reviewer can read both diffs.

1.1 **Lock the timeline with primary evidence.** Record the exact first commit on
`fix/dom-oom-virtualization` (`31d0bbb5`, 2026-06-20 01:42 UTC) and #4661's PR-open timestamp
(2026-06-20 21:07 UTC). Capture both from authoritative sources (git log; `gh pr view 4661
--json createdAt`). Keep the raw output in the research doc as a citation.

1.2 **Separate independent from adapted, precisely.**
- Independent (predates #4661): the `MessageWindow` architecture, bidirectional windowing,
  the eviction model, the message-count-based caps.
- Adapted from #4661 (credited): the per-node teardown idea of clearing
  `_waveInterval`/`_elapsedTicker` before removing an element (mirrors #4661's
  `_trimChatHistoryDOM()` teardown block).
- Extended beyond #4661 (ours): also releasing `_streamRenderer`, disconnecting the
  IntersectionObserver (`_sObs`), and `hljsDeferForgetNode`.

1.3 **Reconcile every #4661 reference to this framing.** Audit all references (done once;
re-run before filing): the draft, `memory-explosion-research.md`, pr-status, active-work. No
document may claim full independence; all must credit the adapted teardown.

1.4 **Exit check:** a reviewer comparing the two diffs finds nothing we claimed as original
that is actually #4661's, and finds clear credit where we did adapt.

---

## Part 2 — Comparative superiority, proven (every way ours is better)

Each advantage needs three things: the mechanism (code), a measurement (numbers), and a
verified citation explaining why it matters. No claim ships without all three.

2.1 **Comparison matrix** (ours vs #4661 vs unpatched baseline) across: bounded DOM under
long sessions; detached-node/observer/renderer leakage; scroll-up reload; scroll-down
behaviour; review size; risk.

2.2 **Measured evidence (the core of "provable").** Build a reproducible benchmark:
- Three branches: `test/upstream-pr-4661` (theirs), `fix/dom-oom-virtualization` (ours),
  `upstream-mirror` (baseline). These comparison branches already exist.
- Identical scripted workload (a long agent session, or a CDP-driven synthetic message
  stream). Use the CDP method already proven this cycle: `Memory.getDOMCounters` (nodes,
  jsEventListeners), renderer RSS, and a heap-snapshot detached-node tally.
- Report: DOM node ceiling, listener growth, detached-node count after a forced GC, RSS
  plateau. Expect ours to show lower retained listeners/observers than theirs because of the
  extended teardown; document the actual numbers, not the expected ones.
- If a measurement does not favour us, say so and adjust the claim. The benchmark decides,
  not the narrative.

2.3 **Cited, verified sources.** For each technical claim, cite an authoritative source and
verify (open it, confirm it says what we claim, the lesson from the draft-link audit):
- Detached DOM nodes and listener leaks: MDN / web.dev memory-management references.
- IntersectionObserver lifecycle and the need to `disconnect()`: the W3C/WHATWG spec and MDN.
- UI virtualization/windowing as the standard solution for large lists (e.g. the pattern used
  by react-window and by photo apps such as Immich, which #4852 already cites): use as prior
  art for the approach, not as our source.
- Oilpan / embedded-Chromium GC behaviour for the "why GC matters here" context.
Record each citation with the exact URL and a one-line quote, and a note that it was opened
and verified.

2.4 **Honest tradeoff, stated up front.** Ours is ~873 lines vs #4661's ~145. Cite the
maintainability cost honestly; do not bury it. The pitch is "more complete and measured,"
not "theirs is bad."

2.5 **Exit check:** every row of the matrix has a number and a verified citation, and the
tradeoff is stated.

---

## Part 3 — Behaviour verification (prove it is perfect), including the known bugs

The virtualization is not submittable until behaviour is correct. Known issues from user
testing:

3.1 **Scroll-down inverse behaviour is wrong (bug).** Scroll-up correctly reads in older
content at the top and prunes the bottom. Scroll-down should be the inverse (read in newer
content at the bottom, prune the top), but currently behaves like the existing "scroll to
bottom" (it drains via `scrollToBottom()` instead of incremental `_loadNewer()` + top
prune). Investigate the scroll-down handler vs the sentinel-driven `_loadNewer()` and the
`scrollToBottom()` draining path (`chatHistory.js`: `_loadNewer`, `scrollToBottom`,
`BIDI_CAP`, the bottom sentinel). Fix so downward scrolling mirrors upward scrolling:
incremental, position-preserving, not a jump to bottom.

3.2 **Snap-to-bottom hardening for the Thinking-box transition (bug).** When sticky-to-bottom
is active, a "Thinking" box appears, grows the content, then is removed before the real
message renders. The bottom position moves twice (grow, then shrink, then grow), and the
current settling loop (`chatHistory.js`:101-116, which re-snaps only while `scrollHeight`
grows) does not re-attach across the shrink. Harden the sticky logic to track intended-sticky
state across rapid bottom-position transitions and re-attach after the Thinking box is
swapped for the message. Add a regression test that simulates grow/shrink/grow.

3.3 **Thinking message as an overlay (improvement, after 3.2).** Render the live "Thinking"
indicator as an absolutely-positioned overlay rather than an in-flow chat box, so it does not
change the document's bottom position. The real message then replaces it with no layout jump,
which also makes 3.2 easier to keep correct. Verify it does not regress the thinking-block
rendering on completion (`chatRenderer.js` `processWithThinking`).

3.4 **Usability / user-friendliness sweep.** A dedicated pass for the chat scroll experience:
- No visible jump when eviction or load fires (scroll position is preserved to the pixel).
- Reload of evicted messages on scroll-up is fast and does not flash.
- The "new messages" / scroll-to-bottom affordance is discoverable and behaves predictably.
- Keyboard and wheel and touch scrolling all behave consistently.
- Behaviour during active streaming (auto-follow) vs when the user has scrolled up (do not
  yank them to the bottom).
- Lazy-loaded images do not cause late jumps (the settling loop already addresses some of
  this; verify).
Produce a checklist with expected behaviour for each, verified manually in the running app.

3.5 **In-app long-session verification.** Run a long agent session; confirm the DOM node
count stays bounded, scroll-up reload works, and the snap behaviour is correct throughout.
This is the gate active-work has always flagged.

3.6 **Exit check:** 3.1-3.5 all pass with reproducible steps; new regression tests cover the
scroll-down, snap-transition, and overlay behaviours.

---

## Part 4 — Audit

4.1 **Code audit** of `chatHistory.js`: edge cases (empty history, single message, rapid
session switching, eviction during streaming), correctness of `_endIdx`/`_startIdx`
bookkeeping, and that every removal path tears down the full reference set from Part 1.2.

4.2 **Test-coverage audit:** the branch has 109 static-analysis tests plus 11 Playwright
functions. Confirm they actually exercise scroll-down windowing, the snap transition, and
teardown completeness; add tests where they do not. (Note: the draft's counts were corrected
in the stale-count audit; keep them accurate as tests are added.)

4.3 **Cleanliness audit:** branch carries only source and tests (contamination removed,
verified). Re-verify before filing.

---

## Part 4.5 — Server-paging fold: MANDATORY companion fixes (added 2026-07-17)

The staged snapshot pre-dates server paging and walks only the in-memory buffer. The plan of
record folds the server-paging work (`fix/chat-history-server-paging`, develop `6fac912d`)
into this branch at rebuild time so a filed PR does not dead-end at the backend's 100-message
page cap. **That fold carries a known defect unless two companions travel with it:**

- **The chIdx retag fix (fork #129, develop `ac18291a`).** `_fetchOlderFromServer` shifts the
  `_all` index space on every prepend; without retagging rendered nodes, tags from successive
  pages collide and the Phase-3 scroll-up prune silently removes nothing (measured in the
  real app: ~1,980 of 2,000 messages live in DOM — the exact unbounded-DOM failure this
  contribution exists to fix). The bug is invisible to the in-memory harness; only the
  server-paging path triggers it.
- **Its regression test** (`test_scrollup_dom_stays_bounded`: constant DOM bound + tag-space
  coherence `maxTag == _endIdx-1`, driven over real server paging via `tests/bench/live_app.py`
  + `tests/bench/scroll_driver.js`, which fold in as test infrastructure). The coherence
  assertion is the load-bearing one — a bare count bound passes trivially on the broken code.

- **The sentinel newest-entry fix (fork #130).** The top-sentinel observer callback must read
  `entries[entries.length-1]`, not `entries[0]`: IO batches a leave+enter pair into one
  delivery under a busy main thread, and reading the stale oldest entry discards the enter,
  dead-ending scroll-up paging permanently at the top (captured live). Companions: its
  Playwright regression `test_pinned_top_walk_completes` and static guard
  `test_sentinel_observer_reads_newest_entry`. **Unlike #129, this defect was in the CURRENT
  staged snapshot** (the trigger is a busy main thread during a batch render — no server
  paging required, so in-memory scroll-up dead-ends the same way). **APPLIED to the branch
  directly (commit `661be326`, 2026-07-17): code fix + static guard, worded without fork
  issue numbers.** At fold time, carry the Playwright pinned-top walk regression alongside
  the server-paging infra (it needs `live_app.py`/`scroll_driver.js`).

Known open defects in the same code to re-check at fold time: #127 (scrollbar spacer).
Filing with #127 open is a disclosure decision, not a blocker; filing with #129 or #130
unfixed would ship defects we have already measured, named, and fixed.

## Part 5 — Sequencing and exit criteria

Recommended order (each is its own fork issue + branch where it is a code change; issue
first):
1. Provenance lock (Part 1) — documentation only.
2. Fix scroll-down inverse windowing (3.1).
3. Harden snap-to-bottom (3.2).
4. Thinking overlay (3.3).
5. Usability sweep + fixes (3.4).
6. Benchmark + cited evidence (Part 2).
7. Final code/test/cleanliness audit (Part 4) + long-session verification (3.5).

**Submittable when, and only when, all of these are true:**
- The server-paging fold includes the #129 retag fix and its regression test (Part 4.5).
- Provenance is precise and every #4661 reference matches it (Part 1 exit check).
- Every superiority claim has a number and a verified citation; the tradeoff is stated
  (Part 2 exit check).
- Scroll-up, scroll-down, snap-to-bottom, and the Thinking overlay all behave correctly, with
  regression tests (Part 3 exit check).
- Code/test/cleanliness audit passes (Part 4).
- The draft reads as a professional, fact-backed contribution (no AI tells, no unbacked
  claims, no fork-internal leaks).

Until then the branch stays unfiled. #4661 being open is not a blocker; it is the reference
we measure against and credit.
