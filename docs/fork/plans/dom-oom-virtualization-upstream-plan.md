# Plan: make `fix/dom-oom-virtualization` (#2) a perfect, provable upstream contribution

Goal: turn the chat-history virtualization into a contribution that can be filed upstream
with confidence next to open PR #4661, where every claim of independence and superiority is
documented, measured, and backed by verified sources, and where the user-facing behaviour is
correct and pleasant. Nothing here is filed by an agent; this prepares the artifact for the
human to file.

Status of inputs (already done):
- Branch contamination removed (the fork PR-draft `.md` is no longer on the branch).
- Provenance settled (Part 1.2 — the only framing to use, anywhere).

---

## Part 1 — Provenance and attribution (make it irrefutable, and honest)

The claim must be exactly true, no more and no less, because a reviewer can read both diffs.

1.1 **Timeline (primary evidence, author dates).** First branch commit `31d0bbb5` ("virtual
message window and scroll fixes"): authored 2026-06-11 20:47 UTC. #4661 opened
2026-06-20 21:07 UTC (`gh pr view 4661 --json createdAt`; OPEN). The architecture predates
#4661 by nine days.

1.2 **Relationship to #4661 — SETTLED. State it exactly this way, everywhere, always:**
- The `MessageWindow` architecture, bidirectional windowing, eviction model, and
  message-count caps are independent work that predates #4661's existence (1.1).
- The per-node teardown is described by what it does: it clears this app's own
  `_waveInterval`/`_elapsedTicker` handles (which any code removing these nodes must
  clear), releases `_streamRenderer`, disconnects the IntersectionObserver, and releases
  hljs-defer references. #4661's `_trimChatHistoryDOM` is not used — it destroys this
  implementation's control elements.
- #4661 is acknowledged as parallel work on the same problem. No adaptation claim, no
  attribution, no provenance discussion beyond these facts — in code, drafts, or docs.

1.3 **Exit check:** before filing, grep the draft and all fork docs for `4661`; every
reference must match 1.2 verbatim in substance. Nothing may claim adaptation from #4661 and
nothing may argue about influence.
**Run 2026-07-18: PASS** (draft, decision record, pr-status, eviction draft all conform;
the one nonconforming phrase found — this plan's own closing line said "and credit" — was
corrected to the 1.2 framing). The streaming-throttle branch's genuine adaptation credits
are a different branch and are out of scope. Re-run once more at file time.

1.4 **Exit check:** a reviewer comparing the two diffs finds every claim verifiable and
nothing argued about provenance beyond the 1.2 facts.

---

## Part 2 — Comparative superiority, proven (every way ours is better)

Each advantage needs three things: the mechanism (code), a measurement (numbers), and a
verified citation explaining why it matters. No claim ships without all three.

2.1 **Comparison matrix** (ours vs #4661 vs unpatched baseline) across: bounded DOM under
long sessions; detached-node/observer/renderer leakage; scroll-up reload; scroll-down
behaviour; review size; risk.
**DONE (2026-07-18).** Matrix built from the published artifact and placed in the PR
draft ("Measured evidence" section). Key result: #4661 bounds the steady state
(~1.19k nodes at every n) but its click-reload path restores the full history with no
re-trim until the next message (n=5000: 39k nodes / 122.9 MB USS ≈ unpatched) and loses
scroll position; ours holds ~2.2k nodes / 62.5 MB USS at the top of a 5000-message
history. Decision record and active-work corrected to match the measurement.

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
**DONE (2026-07-18)** — implemented as the `tests/bench/` harness with vendored arms
(including #4661's trim/reload, `trimChatHistory_4661.js`, faithfulness-guarded by
`tests/test_bench_vendor_4661.py`) rather than branch checkouts; published artifact
`tests/bench/results/bench.{json,md}`. Measurements that did not favour us are kept and
disclosed in the artifact (recent scroll-back inverts toward detach; deep scroll-back
cells withheld with self-describing reasons; network bias noted).

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
**Verified 2026-07-18 — the old counts were stale and understated our size.** Measured:
#4661's trim is 142 lines (the vendored file); the branch's source diff is ~1,432
insertions across 5 files, plus ~2,202 test lines
(`git diff --shortstat upstream-mirror...fix/dom-oom-virtualization`). Draft matrix row
and prose corrected to the measured numbers. Re-measure after the Part-5 rebuild (the
fold will grow the diff further). **Re-measured post-rebuild 2026-07-18: 1,486 source
insertions / 140 deletions across 5 files, 2,826 test lines (11 files total); draft
matrix updated to ~1,490 / ~2,830.**

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

> **AUTOMATED (2026-07-18) — the core of this gate no longer needs a human or a live
> model.** `tests/test_chat_history_longsession_playwright.py` + `tests/bench/mock_llm.py`
> (stdlib-only OpenAI-compatible SSE server; the app treats unknown hosts as
> OpenAI-compatible, so the REAL send path runs unmodified): 55 real composer→
> `/api/chat_stream`→SSE→render exchanges in headless Chromium. Asserts per exchange:
> completion (ACK marker), DOM bound (≤145 children across the live-prune threshold —
> 110 messages streamed), auto-follow; plus both thinking indicators (initial
> `.ai-spinner`, mid-stream `.agent-thinking-dots` overlay — closing 3.3's "needs a live
> model" leg), scroll-up walk to message 0 bounded, scroll-to-bottom re-pin, zero page
> errors. ~90s; three consecutive green runs; on develop and converged to the staged
> branch (send-path skip-probe there). **Its first run caught a real ingested upstream
> bug: every `/api/chat_stream` 500'd (`_explicit_web_intent` NameError, upstream
> `264da651` removed the definition and kept 3 reads; only static AST tests covered the
> route). Fixed: fork #134, branch `fix/chat-stream-web-intent-nameerror` (from
> upstream-mirror, staged for upstream), cherry-picked to develop with a symtable
> undefined-global-read guard closing the class.**
>
> **Still genuinely manual (eyes/hardware, one short pass):** touch/wheel input feel
> (trusted touch events can't be synthesized), flash-on-reload perception, lazy-image
> decode timing on real large images, scroll-to-bottom affordance discoverability, and
> QtWebEngine ecological validity (the suite runs stock Chromium, not the Qt runtime).
> Scripted checklist with setup, per-item steps, and pass criteria:
> `docs/fork/plans/dom-oom-manual-pass-checklist.md` (~10 minutes with the app open;
> record the result there — 3.6 points to it).

3.6 **Exit check:** 3.1-3.5 all pass with reproducible steps; new regression tests cover the
scroll-down, snap-transition, and overlay behaviours.

---

## Part 4 — Audit

4.1 **Code audit** of `chatHistory.js`: edge cases (empty history, single message, rapid
session switching, eviction during streaming), correctness of `_endIdx`/`_startIdx`
bookkeeping, and that every removal path tears down the full reference set from Part 1.2.
**DONE (2026-07-18, commit `81b462c7` on develop, converged to the branch).** Full-file
read with those lenses. Passed clean: empty/single-message load, streaming eviction
(the newest ~60 nodes always survive `_evictLive`'s count arithmetic), index
bookkeeping (all paths track via `data-ch-idx`, boundary peeks included). Four real
defects found and fixed: (1) the inline Phase-3 prunes in `_loadOlder`/`_loadNewer`
removed nodes with NO teardown while registering every rendered batch with the
hljs-defer observer — unbounded detached-subtree retention on deep scroll, the exact
leak class the branch closes; all seven removal sites now go through a single
`_teardownNode` helper. (2) `scrollToBottom()` with nothing to drain latched
`_draining=true` forever (suppressed bottom spacer; next scroll-up prune's rAF
re-entered drain and yanked the user to the bottom). (3) stale-generation rAFs touched
`_clearBusy`/`_draining` before the gen check, clobbering new-session state. (4)
`_pruneBottom` was dead code (zero call sites — the inline prune superseded it and lost
its teardown en route); deleted, with a guard test preventing return. Static guards
updated (123 pass); bench snapshot re-vendored; full suite + convergence guard green.

4.2 **Test-coverage audit:** the branch has 109 static-analysis tests plus 11 Playwright
functions. Confirm they actually exercise scroll-down windowing, the snap transition, and
teardown completeness; add tests where they do not. (Note: the draft's counts were corrected
in the stale-count audit; keep them accurate as tests are added.)
**DONE (2026-07-18).** Scroll-down windowing was already covered at runtime
(`test_bidi_cap_held_during_scroll_down`, `test_load_newer_fires_on_bottom_sentinel`); the
drain/snap transition and teardown were static-only. Added two Playwright tests:
`test_scroll_to_bottom_drains_to_newest_and_stays_bounded` (drain from deep history reaches
`_endIdx == n`, clears `_draining`, lands at the bottom with the newest message rendered,
DOM stays ≤ BIDI_CAP + batch) and `test_teardown_fires_at_runtime_when_nodes_are_pruned`
(armed node's `_waveInterval`/`_streamRenderer` nulled and `hljsDeferForgetNode` called when
Phase-2 pruning removes it; non-vacuity asserted — the node is confirmed removed first).
Suite now 123 static + 16 Playwright + 8 a11y; draft's test plan updated to match.

4.3 **Cleanliness audit:** branch carries only source and tests (contamination removed,
verified). Re-verify before filing.
**Re-verified 2026-07-18:** `git diff --name-only upstream-mirror...fix/dom-oom-virtualization`
lists exactly 5 source files + 3 test files; no fork-management or bench-infra files.
(Re-verify once more at file time, after the Part-5 rebuild.)

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

> **STATUS UPDATE (2026-07-18): Part 4.5 fold and Part 5 rebuild are DONE.** The staged
> branch's merge-base turned out to be the PRE-INGEST upstream mirror (`16026741`) — the
> current mirror (`c67deaa6`, post-#5283) already ships upstream's own paginated
> `/api/history` (`has_more_before`), `_historyUrl`, and a prepend-only pager cluster the
> old branch never saw. Instead of a 21-commit rebase, the contribution was rebuilt clean
> on the current mirror (`wip/dom-oom-rebuild`) and `fix/dom-oom-virtualization` repointed
> to it (old tip preserved at `backup/prerebuild-dom-oom-virtualization`): a 2-commit
> series (`e22d3dde` core + suites, `ddc4e4f2` end-to-end paging suite + infra). The
> rebuild also removed a history commit whose message violated the Part-1 provenance
> framing. sessions.js now wires `olderLoader` against upstream's own pagination contract
> and keeps upstream's `_displayHistoryContent`/`_stripUserVisionBlocks` filters (develop's
> extracted mapper had dropped them — regression fixed on develop, `3b4d1d2b`). The paging
> suite probes the backend at startup and SKIPS until the #125 route-shadowing fix (staged
> separately) unblocks the paginated endpoint; with #125 applied locally: 152 passed,
> exit 0; without it: 147 passed + 5 skipped, exit 0. Convergence guard expanded to 7
> files (adds the paging suite, `live_app.py`, `scroll_driver.js`). Remaining before
> filing: 3.5 manual long-session pass (human) and the file-time exit-check re-runs.

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
we measure against, acknowledged as parallel work per Part 1.2.
