# Decision Record — Chat-History Rendering Architecture

**Status:** Decided. The verdict (keep the fork's `MessageWindow`) is stable; the *upstream landscape*
below is live and must be re-checked before filing any upstream PR.
**Scope:** How the fork renders long chat histories, and what we contribute upstream.
**Regression guard:** `tests/test_chat_history_render_paging_playwright.py` (on `develop`).
**Last upstream survey:** 2026-07-08 (issues/PRs/ROADMAP/discussions of `odysseus-dev/odysseus`).

---

## The question

Long chat histories blow up renderer memory (RSS) and cause lag — the fork's whole memory track exists
because RSS/VRAM is the scarce resource. Two implementations of "don't hold the whole history live"
are in play: the fork's own `static/js/chatHistory.js` (`MessageWindow`), and upstream's work. Do we
keep ours, adopt theirs, or blend?

**The test that decides it: is ours better *for the problem the fork actually has* (bounded memory)?**
Yes. Keep `MessageWindow` on `develop`. The rest of this document records the evidence, the honest
places theirs is better, and how our upstream contributions relate to upstream's in-flight work — so
this is not re-litigated and so a merge of upstream's PRs does not blindside us.

## Upstream landscape (surveyed 2026-07-08 — re-check before filing)

| Upstream item | State | What it does | Bounds memory? |
|---|---|---|---|
| Pager `_installHistoryPager` (commit `45ee5a71`, direct to `dev`, **not** a PR) | **merged** | Prepends older pages on scroll-up. Never removes a node. | ❌ DOM grows monotonically |
| Issue **#4644** "browser OOM during long agent interactions" | **open** | Asks explicitly that old messages be *"collapsed or removed from the DOM."* The canonical OOM issue. | — (the ask) |
| Issue **#2869** "Chat Freeze" after ~20 messages | **open** | Symptom report; no concrete design. | — |
| PR **#4661** "prevent browser OOM during long agent interactions" (Fixes #4644) | **open** | "Show N older" bar: server paging (`?limit`/`total`/`has_more_before`) + throttled thinking render + `_trimChatHistoryDOM()`: 150-child DOM cap with real removal, per-node teardown, and image data-URI blanking, re-applied on each append. | ⚠️ bounds *steady state* (measured: ~1.19k nodes at every n, vendored arm in `tests/bench/`), but the "Show older" click-reload path restores the full history with **no re-trim until the next message** — at top of history it equals naive (n=5000: 39k nodes, 122.9 MB USS vs naive's 119.8) — and it does not preserve scroll position |
| PR **#4998** "virtualize #chat-history to fix long-chat lag" (`chatVirtualizer.js`) | **open** | Per-message IntersectionObserver: for far-off-screen nodes, **detaches child nodes into a JS array and pins the wrapper height**, restores on scroll-back. Preserves `<details>`/highlight/listeners. | ⚠️ bounds *layout/paint* (lag), **not RSS** — detached children stay referenced in heap, one shell per message retained forever |
| ROADMAP.md | — | No chat-history / virtualization / renderer-memory item at all. Has a generic "Accessibility pass (incl. reduced motion)". | — |

**Consequence:** upstream's *merged* code still has no bounded-DOM story — our supersession claim holds
against `dev`. But two open PRs and an open issue are now circling this exact area. Neither open PR
fully bounds memory: #4661 bounds the steady state (its `_trimChatHistoryDOM` really removes nodes)
but its click-reload path is transiently unbounded — reading old history restores everything and
nothing evicts until the next message re-trims — and it loses scroll position; #4998 targets lag and
keeps detached nodes in heap. So the fork's requirement — a memory bound that *holds while reading
old history*, via windowed removal + server refetch — is **unmet by everything upstream, merged or
in-flight.** That is the specific, on-the-record justification for the divergence (answers
"a workbench shouldn't diverge": we diverge exactly where upstream has no solution to the fork's
scarce-resource problem).

## The comparison (read the code, not the vibes)

| | Upstream `_installHistoryPager` (`45ee5a71`, merged) | Upstream `chatVirtualizer.js` (PR #4998, open) | Fork `MessageWindow` (`chatHistory.js`, ~1000 L) |
|---|---|---|---|
| Defers full render on open | ✅ | n/a (windows existing DOM) | ✅ |
| Pages **older** from server | ✅ (prepend) | ❌ (no server involvement) | ✅ (`_fetchOlderFromServer`) |
| Pages **newer** back in | ❌ | n/a | ✅ (`_loadNewer`) |
| **Removes nodes from the DOM** | ❌ | ⚠️ detaches *children*, keeps wrapper + heap refs | ✅ (`_pruneTop`/`_evictLive`) |
| **Bounds RSS** (nodes truly gone) | ❌ | ❌ (detached subtrees retained) | ✅ |
| Preserves per-node state on scroll-back | ✅ (never removed) | ✅ (detach/restore, no re-render) | ❌ (re-renders via `addMessage`) |
| Lines of code | ~60 | ~95 | ~1000 |

**Honest two-axis verdict.** Ours wins decisively on the memory/OOM bound — the fork's actual
requirement, and the one #4998 does *not* satisfy (its detached children remain in heap). #4998 wins on
simplicity and on state-preservation (its detach-and-restore avoids the re-render/refetch ours pays on
scroll-back). They are closer to *complementary* than competing: #4998 = lag (layout/paint), ours =
memory. Keeping `MessageWindow` on `develop` is the correct call for a memory-constrained runtime.

## The convergence path — BUILT, MEASURED, REFUTED (2026-07-09)

The plan above was to combine the two: a warm band using #4998's detach-preserve over a cold tail using
our eviction, expected to Pareto-dominate both. **It was built (`tests/bench/vendor/hybrid_bench.js`),
tested (`tests/test_chat_history_hybrid_bench_js.py`, 5 Chromium guards), benchmarked, and it lost.**
Numbers: `tests/bench/results/bench.md` (generated; never transcribed here).

**The hybrid buys nothing over eviction alone at any history length that matters.** Stated precisely,
because the honest version is narrower than "strictly worse":

- At **n = 1000 and n = 2000** eviction wins on renderer USS by a margin well outside measurement
  spread (+9.1MB and +5.1MB respectively).
- At **n = 250** and **n = 5000** the two arms' USS is **within combined spread** — indistinguishable,
  which is a null result and not a win for either. (At n=250 all strategies sit inside Chromium's
  renderer baseline; at n=5000 both bounded arms have converged to a flat window.)
- At **every length**, eviction holds ~2.5× fewer retained nodes. This is the structural metric and it
  never inverts.
- The hybrid's one theoretical advantage — cheap warm-band restore — is **beaten by eviction's zero**,
  because the live window already covers that range without detaching anything.

The reasons are structural rather than a tuning failure, so **do not attempt to rescue this by tuning
band sizes**:

1. **Detach-preserve retains a superset of what eviction retains** over the same window: it keeps every
   collapsed message's children alive in `__vChildren`. Eviction can therefore never lose to it on
   memory, at any band size.
2. **A live window already subsumes detach's only real advantage.** #4998's value proposition is instant
   recent scroll-back. But `MessageWindow` keeps the recent `BIDI_MSG_CAP` messages *fully live*, so
   recent scroll-back costs zero work **and** zero network — strictly better than a warm band, which
   detached those same messages and must re-attach them. Beyond the window, everyone re-renders from the
   cold tail anyway. Any hybrid tuned toward eviction's zero-work recent scroll-back converges *to*
   eviction.

This is a stronger position than a contrived winner: we implemented their idea on top of ours, measured
it honestly, and it added nothing. The refuted arm and its tests are **kept, not deleted** — a tested
refutation with data is the deliverable. Known defect in that arm: fork issue #126 (top-spacer height
drifts; its deep-scroll-back timing cells are withheld by the harness's completeness guard rather than
published). The refutation does not depend on those cells.

**Known defect in the kept architecture:** fork issue #127 — the scrollbar misrepresents history.
Measured across the length curve (2026-07-17, probe + raw data inlined in the issue): reported
`scrollHeight` is a *constant* (8,401 px at load, 13,420 px after paging the full history in) for
n=100..5000, so scrollbar honesty is ~50/n — 50% at n=100 down to 1% at n=5000. The prune-spacer
contribution caps at ~5,019 px regardless of how many messages were pruned, so a fix cannot reuse the
`_pruneTop` spacer arithmetic; the estimator must own the entire unrendered range (and #126 documents
how such an estimator drifts). This is a UX defect, not a memory one — it does not weaken the RSS
argument above, but it is a real cost of eviction that detach-preserve (#4998) does not pay, and it
must be stated wherever this decision is defended.

**Revisit only if** upstream ships real DOM eviction of its own, or if the network cost of cold-tail
refetch is shown to dominate — the one axis the harness excludes (it serves cold pages from memory,
which biases *against* eviction, the honest direction).

**2026-07-17 — the network axis is now measured and it does not dominate.**
`tests/bench/network_arm_bench.py` (real `app.py` under uvicorn, real `/api/history`, the real
`MessageWindow` + `olderLoader` wiring, RTT emulated via CDP): deep scroll-back's added cost is
serialized pages × RTT, confirmed empirically at both lengths, with server handler cost ~2 ms/page
and a full 2000-message walk costing 19 requests / ~50 kB gzipped. At mobile-class RTT that is
seconds per *full-history* walk, incurred only when the user actually walks; #4998's zero-network
scroll-back is real but bounded by this slope. Current numbers live in the generated
`tests/bench/results/network_arm.md` — do not transcribe them here. The revisit clause above is
therefore resolved in eviction's favour on present evidence.

**But the same measurement found the decision's premise failing in the real app (fork issue #129):**
during a sustained scroll-up walk, `MessageWindow` never pruned — the DOM reached ~1,980 of 2,000
messages at the top. The RSS bound this document's whole argument rests on holds in the synthetic
harness but **not on the real scroll-up paging path**. #129 must be fixed (and guarded by a
constant-bound assertion, not the existing `< N` one) for this decision to stand on its stated
grounds. A related trigger defect, #130 (one-shot IntersectionObserver dead-end at the top), was
found on the same walk.

**2026-07-17, later — #129 fixed and the premise re-verified.** Root cause was not a missing prune
but a corrupted index space: `_fetchOlderFromServer` shifted `_startIdx`/`_endIdx` on prepend without
retagging rendered nodes' `data-ch-idx`, so tags from successive pages collided and the Phase-3 prune
broke at the first stale tag. Fixed by retagging on prepend (develop merge `dd645129`); the real-app
n=2000 walk now holds exactly `BIDI_MSG_CAP` (80) messages in DOM with a coherent tag space, and
scroll-down after real pruning reaches the newest message cleanly. Guarded by a constant-bound (130)
+ tag-coherence regression test in `test_chat_history_render_paging_playwright.py`, red-verified
against the unfixed code. The RSS-bound premise of this decision holds in the real app again.
#130 remains open.

**2026-07-17, later still — #130 fixed.** The dead-end was not the one-shot disconnect dance: the
sentinel observer's callback read `entries[0]` — the oldest queued entry — and IO batches a
leave+enter pair into one delivery when the main thread is busy rendering a batch, so the stale
leave was read and the enter discarded, leaving an armed observer that could never fire again
(captured live: one delivery with `isIntersecting [false, true]`). Fixed by reading the newest
entry (`entries[entries.length-1]`). A 9-cell RTT × pin-cadence probe sweep dead-ended in 2 cells
pre-fix and completes in all 9 post-fix; guarded by a pinned-top full-walk Playwright test plus a
deterministic static guard. Note the reach: this bug needs no server paging (busy main thread is
the trigger), so it also lives in the staged #2 snapshot — recorded in plan Part 4.5.

**2026-07-17, last — #127 fixed; the scrollbar is honest.** Estimator spacers now own the whole
unrendered range on BOTH edges (a top-only first cut collapsed back to 4% honesty at walk end —
caught by the walk-stability regression before commit). Design against #126's drift lessons:
idempotent recompute (never incremental accumulation), exact prune-pass heights keyed by absolute
DB index, estimator average movable only inside compensated contexts. Measured honesty at load:
1.01/1.00/1.00 for n=300/2000/5000 against walk-end ground truth (was 0.50/0.03/0.01; uniform
corpus — heterogeneous chats estimate looser at load and converge as prunes record exact heights).
Verification surfaced and fixed two adjacent defects: the height-delta scroll compensation
double-compensated under Chromium's native scroll anchoring (measured +36 px on the boundary
batch; replaced with idempotent anchor-restore, net-formula fallback in blank spacer where
anchoring is suppressed) — note this corrects this document's earlier "coexists harmlessly with
our manual math" claim, which held only while the net delta was ~0 — and the deep-drag catch-up
chain over-triggered on a proximity margin (now gated on blank-actually-in-viewport; the sentinel
owns the one-batch lookahead). The staged #2 branch was converged to the maintained
chatHistory.js + test pairing (`463526b0`), retiring the snapshot-lag defect class there.

## What we learned from theirs

- **#4998's detach-and-preserve** round-trips node state (`<details>`, highlight, listeners) with no
  re-render — genuinely cleaner than our destroy-and-refetch on that axis. Measured and refuted as an
  addition to eviction (above): the live window already delivers that benefit more cheaply.
- **The one thing we can give #4998's author.** Their scroll jank has a single root cause: `collapse()`
  reads `node.offsetHeight` inside the IntersectionObserver callback, forcing a synchronous layout per
  collapsing node — a reflow storm during a scroll. The height is already on
  `entry.boundingClientRect.height`, for free. Deferring the collapse to a batched rAF pass compounds
  the win. This is a discrete, self-contained improvement to *their* PR and should be offered as such
  (a review comment on #4998, not a competing claim). Demonstrated in `hybrid_bench.js`'s `collapse()`.
- **Upstream's prepend scroll-anchor** (capture `scrollHeight`, add the delta back to `scrollTop`) —
  `MessageWindow` already does the equivalent for prepend *and* eviction.

## What goes upstream (we stage; the human files — hard rule)

We do **not** ask upstream to undo their pager. Two cooperative contributions on
`fix/chat-history-dom-eviction` (cut from `upstream-mirror`):

1. **Route-shadowing fix (#125).** A legacy `GET /api/history/{sid}` on the sessions router shadows the
   paginated endpoint, so upstream's *own* pager never receives `has_more_before` and is inert. This
   fix makes their merged feature actually run — a pure gift.
   Draft: `docs/fork/upstream/pr-drafts/fix-history-route-shadowing.md`.
2. **Bounded-DOM eviction (#2).** Attach to the **existing upstream issue #4644** (it explicitly
   requests DOM removal), not a new issue — per CONTRIBUTING's issue-first rule. The PR's exact shape is
   **reassessed at file-time** (a human decision) depending on whether #4661/#4998 have merged: if
   #4998 lands, file eviction as a layer on their virtualizer; if not, the standalone eviction pass.
   Draft: `docs/fork/upstream/pr-drafts/fix-chat-history-dom-eviction.md`.

**CONTRIBUTING constraints these PRs must satisfy** (upstream `CONTRIBUTING.md`, surveyed 2026-07-08):
base branch `dev`; one fix per PR; **large feature → open/point to an issue first**; agent-authored
PRs must be **issue-first and human-filed** (bulk agent PRs are closed unreviewed — Claude Code is named
explicitly); any `static/js/` DOM change is "visual" → **run the app + attach desktop and mobile
screenshots**, reuse existing CSS vars/components, **no emoji** (inline SVG only); run `pytest`,
`py_compile`, and `node --check` and state so in the PR body. Per the issue-lifecycle rule, #125 and #2
stay open until those upstream PRs are filed.

## Gold-standard audit (2026-07-08)

Audited `MessageWindow` against current virtualization/reverse-scroll best practice (MDN, web.dev,
TanStack Virtual, WAI-ARIA APG). **The mechanical core is gold-standard:** prepend/eviction scroll
anchoring, height-matched spacers, timer/listener/hljs teardown on every removal path, `_gen`
generation guards, `_fetching` single-flight, `_isAtBottom`-gated stick-to-bottom, and a
`content-visibility:auto` + JS-eviction hybrid all match reference practice.

**The systematic weakness was accessibility** — where hand-rolled virtualizers typically fail. Fixed
this pass (each with a guard test):

- **Live-region churn.** `#chat-history` is `role="log" aria-live="polite"` *and* the mutation target
  for prepend/restore/evict, so a screen reader would announce scroll-up history as new. Fix: set
  `aria-busy="true"` around each `MessageWindow` prune/insert batch and clear it after (ARIA APG),
  **composing** with the streaming `aria-busy` (`chat.js:1449`/`3532`) so the virtualizer never clears
  busy while a stream still owns it. (Validated by a guard test that the busy flag brackets the batch —
  *not* a screen-reader audit, which cannot run here.)
- **Focus loss on eviction.** Each eviction/prune batch (`_pruneTop`, `_evictLive`, and the scroll-up
  and scroll-down inline prunes in `_loadOlder`/`_loadNewer`) captures whether focus was inside the log
  before removing, and — if the focused node was evicted (focus fell to `<body>`) — moves focus to the
  log container instead of dumping keyboard position.
- **Sentinel keyboard/semantics.** The clickable bottom sentinel gets `role="button"`/`tabindex`/Enter;
  decorative spacer/sentinels get `aria-hidden`.

**Deferred and documented (no active bug — do not churn a working system):** intrinsic-size placeholders
in place of the measured-px spacer; stricter read/write batching in prune paths; the #4998
detach-preserve hybrid. **Not a bug, comment corrected only:** `overflow-anchor:none` is applied to
sentinels/spacer, not globally; the target is Chromium-based QtWebEngine where native anchoring targets
the visible bottom and coexists harmlessly with our manual math — the misleading "required globally"
comment was corrected to state the real invariant.

**Dead code removed (develop-only hygiene):** `sessions.js` `_installHistoryPager` /
`_renderHistoryMessage` / `_addHistoryMessageWithFullRenderer` — upstream's pager, orphaned on the fork
by our `olderLoader`, zero call sites and zero test refs. (`upstream-mirror` correctly keeps the pager.)

## Test coverage (2026-07-08)

The `*_js.py` tests are static source-greps (no JS execution); real behavior is covered only by the two
Playwright files. Added this pass:

- **Backend pagination contract** (pytest `TestClient`): `limit`/`offset`/`has_more_before`/
  `has_more_after`, `limit` cap at 100, offset clamp, default offset `total-limit`.
- **Hidden-row + base64/multimodal stripping through the *paginated* DB branch** (previously only the
  fallback branch was grepped).
- **Direct route-shadowing assertion**: exactly one `/api/history/{id}` handler is registered and it is
  the paginated one — a one-line reintroduction of the legacy route would otherwise silently re-break
  paging with no failing test.
- **Real render-path Playwright** extended to seed markdown/fenced-code/image/agent-thread content, not
  just plain strings — closing the `markdownModule`-regression class beyond the trivial shape.
- **A guard test per a11y fix** above.

## When to revisit

- **Before filing** either upstream PR — re-run the upstream survey (#4644/#4661/#4998 states).
- **If #4998 or #4661 merges** — re-open the comparison; pursue the convergence path (eviction on top of
  their virtualizer) rather than defending `MessageWindow`.
- Otherwise the course is set: keep ours on `develop`, ship them the route fix + the eviction concept.
