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

1.1 **Timeline locked with primary evidence (re-verified 2026-07-18, author-date precision).**
`31d0bbb5` (first branch commit, "virtual message window and scroll fixes"): AUTHOR date
2026-06-11T13:47:10-07:00 = **2026-06-11 20:47 UTC**; its previously recorded "2026-06-20
01:42 UTC" was the rebase COMMIT date, not authorship. #4661 opened 2026-06-20T21:07:50Z
(`gh pr view 4661 --json createdAt`, re-verified; still OPEN). The architecture therefore
predates #4661 by **nine days**, not 19 hours. The `_evictLive` teardown commit `7c959338`:
author date 2026-06-20T18:55:06-07:00 = **2026-06-21 01:55 UTC**, ~4h48m after #4661 opened.

1.2 **Provenance framing — RESOLVED 2026-07-18 (supersedes the earlier "adapted, credited"
framing; adopts and sharpens the recon §7 retraction).** The draft header's 2026-07-07
retraction and the plan's older "adapted from #4661" instruction contradicted each other;
this is the reconciled, exactly-true statement — every clause verifiable:
- **Independent, timeline-proven:** the `MessageWindow` architecture, bidirectional
  windowing, eviction model, and message-count caps (authored 9 days before #4661 existed).
- **The `_evictLive` teardown: no influence claim in either direction.** Authored ~5h after
  #4661 opened, so timeline proves nothing. The overlapping lines clear this app's own
  `_waveInterval`/`_elapsedTicker` handles — an idiom forced on ANY implementation that
  removes these nodes; #4661's actual mechanism (`_trimChatHistoryDOM`) was never used and
  is architecturally incompatible with the control elements. Ours additionally releases
  `_streamRenderer`, disconnects `_sObs`, and calls `hljsDeferForgetNode` — beyond anything
  in #4661.
- **No in-code #4661 attribution** (the transient attribution comment from `0e9ff11f` was
  dropped at the 463526b0 convergence — correct). The PR description acknowledges #4661 as
  parallel work on the same leak class, states these facts, and claims nothing more.

1.3 **Reconcile every #4661 reference to the 1.2 framing.** Re-run before filing. Audited
2026-07-18: the draft, `memory-explosion-research.md`, pr-status, active-work updated to the
facts-only framing; no document may claim either full independence of the teardown OR
adaptation from #4661 — both overclaim what the evidence supports.

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

3.1 **DONE (2026-07-18, pending only the #2 filing).** Fixed 2026-06-25 (`8fc0dcdc`: drain-only
recursion and end-snap, "newer" wording, static guards) — the fork issue (#103) lagged the fix.
Behavioral verification in the real app surfaced a fresh #127-spacer regression on the same path
(#132: batches inserted below the bottom honesty spacer, order corrupted) — fixed (`4cf6325b`),
DOM-order-coherence regression test red-verified, staged branch re-converged (the #131 guard
fired on its first live drift and forced it). Measured end state: one scroll-down trigger loads
exactly one batch (80→105), stops, no drain, no yank. Original item text kept below for the
record:

~~3.1~~ **Scroll-down inverse behaviour is wrong (bug).** Scroll-up correctly reads in older
content at the top and prunes the bottom. Scroll-down should be the inverse (read in newer
content at the bottom, prune the top), but currently behaves like the existing "scroll to
bottom" (it drains via `scrollToBottom()` instead of incremental `_loadNewer()` + top
prune). Investigate the scroll-down handler vs the sentinel-driven `_loadNewer()` and the
`scrollToBottom()` draining path (`chatHistory.js`: `_loadNewer`, `scrollToBottom`,
`BIDI_CAP`, the bottom sentinel). Fix so downward scrolling mirrors upward scrolling:
incremental, position-preserving, not a jump to bottom.

3.2 **DONE (verified 2026-07-18).** Superseded by the stick-to-bottom observer
(`fix/chat-stick-to-bottom`, #104): one observer is the source of truth for staying pinned
(`isPinned` read from the pre-growth position; MutationObserver + per-child ResizeObserver).
The Thinking-transition path was behaviorally confirmed 2026-06-25; the remaining unconfirmed
leg — the per-child ResizeObserver on pure layout growth — was confirmed 2026-07-18 in the
real app: pinned + late 600px child growth → re-pins; pinned + shrink-then-grow (900px,
the Thinking shape) → re-pins; scrolled-up + same growth → held within 4px, no yank.
Evidence on #104. 8 static guards in `tests/test_chat_stick_to_bottom_js.py`.

3.3 **DONE (2026-07-18, `feat/thinking-overlay` from `upstream-mirror`, develop `163cbc52`;
issue #133; stays open until filed).** The indicator is a zero-footprint sticky overlay:
height:0 `position:sticky` anchor as the log's last child, bubble absolutely positioned above
it. Measured in the running app: scrollHeight and pinned bottom-distance identical across
append/replace/remove; the indicator stays visible at the viewport bottom when scrolled up
(a UX gain the in-flow box never had). `role=status` for AT; `agent-thinking-dots` kept
inside the log so cleanup queries and aria-busy ownership are unchanged; no
transform/will-change. 7 static guards; PR draft `pr-drafts/feat-thinking-overlay.md`.
Verification scope: the probe measured the geometry of the exact structure the function
builds (static guards pin the equivalence); driving `_showThinkingSpinner` end-to-end needs
a live model → on the 3.5 manual-smoke checklist.
`processWithThinking` (thinking-BLOCK rendering) untouched — different subsystem, verified by
the streaming suites. The plan's original 3.2/3.3 texts are preserved in git history.

3.4 **Usability sweep — measured where an agent can measure; the rest is an explicit manual
list (status 2026-07-18):**
- No visible jump on eviction/load: **MEASURED.** Anchor-restore compensation 0px drift at
  mid-history and boundary batches; prune spacer growth exact to the pixel; DOM-order
  coherence after scroll-down (#132 evidence matrix).
- Evicted-message reload speed: **MEASURED.** Handler ~2 ms/page; deep scroll-back cost is
  serialized pages × RTT (network arm). Flash-on-reload: MANUAL — needs eyes on a real
  session.
- Scroll-to-bottom affordance: **PARTIALLY MEASURED.** Bottom sentinel is keyboard-accessible
  (role=button/tabindex/Enter, a11y guards); drain reaches and holds the true bottom
  (scenario C). Discoverability: MANUAL.
- Keyboard/wheel/touch consistency: **MANUAL** — agent cannot generate trusted touch input.
- Streaming auto-follow vs scrolled-up: **MEASURED at the mechanism level** (pinned re-pins,
  unpinned held within 4px — 3.2 evidence). End-to-end with a live model: MANUAL smoke.
- Lazy-image late jumps: **MECHANISM COVERED** (load()'s one-shot img listeners + settle loop
  + the stick observer); decode-timing on real large images: MANUAL.
Manual items above are the 3.5 long-session pass's checklist; nothing else blocks on them.

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

> **STATUS UPDATE (2026-07-17, later): the FILE portion of this fold is DONE.** Commit
> `463526b0` converged the branch's `static/js/chatHistory.js` and its three test suites
> (static contract, browser harness, a11y) to the maintained develop version, byte-identical
> except fork-issue references scrubbed from comments. That carries the #129 retag fix, the
> #130 newest-entry fix, and the #127 honesty estimator (both edges, anchor-restore
> compensation, blank-in-view chain gating) — all verified green on this branch (143 converged
> tests + full suite, exit code checked). The server-paging code is INERT on this branch until
> `load()` is handed an `olderLoader`. **Still remaining at rebuild time:** the sessions.js
> `olderLoader` wiring, the backend paging contract (which depends on the #125 route-shadowing
> fix, staged separately), the `live_app.py`/`scroll_driver.js` test infrastructure, and the
> server-paged Playwright regressions (`test_scrollup_dom_stays_bounded`,
> `test_pinned_top_walk_completes`, `test_scrollbar_honesty_scales_with_history`).

The staged snapshot pre-dated server paging and walks only the in-memory buffer. The plan of
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

All three measured defects in this code (#127 scrollbar honesty, #129 retag, #130 sentinel
newest-entry) are now fixed on develop AND carried by the branch via the `463526b0`
convergence — none remain as disclosure items. At rebuild time, re-verify the convergence is
still current (the snapshot-drift discipline: the branch file must match the then-current
maintained file, fork references scrubbed).

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
