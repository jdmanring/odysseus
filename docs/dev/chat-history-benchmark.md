# Chat-History Virtualization Benchmark — Methodology

**Purpose.** Produce a reproducible, apples-to-apples comparison of chat-history rendering strategies
on the two axes that matter — **renderer memory** and **layout/paint cost (lag)** — plus the axis the
memory-bound strategies trade away — **scroll-back latency**. The output is an artifact a skeptic
(upstream maintainer) can re-run and get the same *shape*, so the conclusion is not deniable.

**Non-goal.** A chart that only flatters one strategy. Every strategy's genuine win is reported.

**The hypothesis this benchmark was built to prove was refuted by it.** The design below anticipated a
`hybrid` arm that Pareto-dominates — bounded memory *and* low layout cost *and* instant recent
scroll-back. The hybrid was built, tested, and measured; **it buys nothing over eviction alone.** Stated
to the precision the data supports: eviction wins renderer USS outside measurement spread at n=1000 and
n=2000; at n=250 and n=5000 the two arms are *within* spread (a null result, not a win for either); and
eviction holds ~2.5× fewer retained nodes at every length. The refutation rests on a structural argument
— detach-preserve retains a superset of what eviction retains — not on those margins. The
reasoning is recorded in `docs/fork/chat-history-architecture-decision.md` and the numbers in
`tests/bench/results/bench.md`. The arm is kept, relabelled: a tested refutation with data is a result,
not a failure. Read the sections below as the *method*, not as a prediction that held.

---

## Strategies compared (real code, no strawmen)

| Arm | Source | Mechanism | Bounds |
|-----|--------|-----------|--------|
| `naive` | upstream merged pager (`45ee5a71`) shape | render page, prepend older on scroll-up, never remove | nothing (baseline) |
| `detach` | **vendored** upstream PR **#4998** `chatVirtualizer.js` (verbatim, with provenance) | off-screen: detach children into a JS array, pin wrapper height; restore on scroll-back | layout/paint only |
| `evict` | **vendored** snapshot of the fork's `MessageWindow` (`tests/bench/vendor/messageWindow_fork.js`) — see the warning below | remove off-screen nodes; refetch from server on scroll-back | rendered DOM nodes (but `_all` data grows) |
| `hybrid` | new (this benchmark) — **hypothesis, refuted** | live band → warm band (detach-preserve, #4998 technique) → cold tail (evict nodes **and** `_all`, refetch) | bounded, but never better than `evict` where it matters (n ≥ 1000) |

Vendoring #4998's actual code (not a reimplementation) is a hard requirement: a benchmark that
reimplements a rival and makes it look bad is dismissed on sight.

### What each arm actually is — and what `evict` is *not*

**The `evict` arm is not the eviction code staged for upstream, and no number here may be attributed to
that PR.** The two are different implementations of the same idea:

- **Benchmarked (`evict`):** the fork's `MessageWindow` — a ~1090-line class in `static/js/chatHistory.js`,
  vendored here as `tests/bench/vendor/messageWindow_fork.js`.
- **Staged upstream** (`fix/chat-history-dom-eviction`): ~112 lines of functions in `static/js/sessions.js`
  (`_evictHistoryOverflow`, `_tagHistoryOffset`, `_teardownHistoryNode`) hooked into upstream's own
  `_installHistoryPager`.

What they share is the *mechanism under test* — remove off-screen nodes from the DOM, refetch them from
the server on scroll-back — and that mechanism is what these results measure. What they do not share is
source. A reviewer holding the `sessions.js` PR cannot diff it against this arm line-for-line, and should
not try. The honest reading: this benchmark establishes that **DOM removal beats detach-preserve on
renderer memory**; it does not certify any particular implementation of DOM removal.

All three non-trivial arms are vendored snapshots, so the benchmark runs deterministically from a clean
checkout of any branch — including one with no `chatHistory.js`. `tests/test_bench_vendor_snapshot_drift.py`
asserts the snapshot stays byte-identical to the live file wherever that file exists, so the published
results can never silently describe code that has since changed; the test skips where the live file is absent.

## Honest claims (corrected against the code, 2026-07-08)

- **`evict` is not "flat RSS."** `chatHistory.js` never evicts `_all` (verified: `_all` is only
  read/concatenated, never spliced). Scrolling to the top of an N-message history retains N
  already-rendered HTML **strings** in `_all`. That is far lighter than #4998's retained live DOM
  subtrees, but it is O(history-scrolled), not flat. The headline is "bounded rendered DOM + cheap
  string retention," and the scroll trajectory **must drive to the very top** so this cost is measured,
  not hidden. Fairness cuts against us too.
- **`detach`'s one genuine, unmeasured win is zero-network scroll-back** (array re-append vs our server
  round-trip). It is stated and excluded, not measured — see Known limitations. Its *layout* parity did
  not survive measurement: it loses the scroll-smoothness and scroll-back layout axes outright, for the
  `offsetHeight`-reflow reason above.
- **The hybrid's claim was refuted.** It was: match `detach` on recent scroll-back, match `evict` on
  deep memory. It matches neither advantage and costs more memory than `evict`. Kept as a recorded
  refutation.

## Instruments (empirically selected)

Two discriminator probes were run before building (see `scratchpad/probe_detached.py`; results below
are reproduced, not asserted):

```
[baseline            ] Nodes=    5  JSHeap=  556184
[2000 live attached  ] Nodes=20005  JSHeap=  723380
[2000 detach-preserve] Nodes=20005  JSHeap= 1051920   <- #4998: nodes NOT freed, heap rises
[2000 fully evicted  ] Nodes=    5  JSHeap=  692008   <- eviction: nodes + heap released
```

Conclusion: **CDP `Performance.getMetrics.Nodes` counts detached-but-referenced nodes**, so it is the
clean, legible signal that captures #4998's retention (20005 vs 5). Instruments used, in priority:

1. **`Nodes`** (CDP `Performance.getMetrics`, corroborated by `Memory.getDOMCounters.nodes`) — the
   structural retention metric. Primary.
2. **`JSHeapUsedSize`** sampled **after forced `window.gc()`** — JS-side retention. Corroborates.
3. **`LayoutDuration` + `RecalcStyleDuration`** deltas across a fixed trajectory — the lag axis
   (#4998's own metric; showing bounded strategies match it neutralizes "yours is heavier").
4. **Renderer-process USS/RSS** (via `psutil`, the *page's* renderer process) — the **ground-truth
   byte metric**: the real OS-level private memory that actually OOMs. This is the headline memory
   number; node count (1) is its structural proxy. `measureUserAgentSpecificMemory()` was intended
   here but is **unavailable in headless Chromium** — it throws `SecurityError: not available` even
   when `self.crossOriginIsolated === true` (verified 2026-07-08). Renderer USS is a stronger metric
   anyway (real process memory, not an in-page estimate). The harness reads the *max* single renderer's
   USS (one page → one content renderer holds the DOM; a spare/prewarm renderer is excluded), recording
   `renderers` so the assumption is auditable. Each cell runs in a **fresh persistent context** (clean
   renderer) located by a unique `--user-data-dir`.
5. **Real-app process RSS** — the fork's Qt-wrapper `[MEM]` telemetry on the actual QtWebEngine target,
   as ecological confirmation that the harness curves reflect real RSS. Referenced, not re-derived here;
   the harness→real-app link remains an assumption, not a measurement (a stated limitation).

Flags: `--enable-precise-memory-info`, `--js-flags=--expose-gc`. Statistics: median of ≥4 kept runs per
cell with one warm-up run discarded; dispersion (max−min) published alongside each median; environment
(Chromium build, CPU, RAM, OS) captured into the results JSON.

### Scale dependence (a load-bearing honesty point)

The memory difference is **negligible below ~1000 messages** — a few thousand DOM nodes cost a few MB,
swamped by Chromium's ~40 MB renderer baseline, so all strategies sit within noise there. The eviction
win only becomes material at large histories (measured divergence at ~2000+, large at 5000). Any claim
must be stated *with its history-length regime*; "bounds memory" is true at scale, not at n=200. The
byte metric (4) is what exposes this — a node-count-only benchmark would imply a difference that does
not exist in bytes at small n, and would *overstate* the gap by ignoring that #4998's detaching frees
real render memory even though node count is unchanged.

### Instrument caveat (decisive — read before trusting any memory number)

**JS heap does not capture #4998's cost.** DOM nodes live in the C++/Blink heap, not the JS heap.
#4998 detaches a message's *children* into a `__vChildren` JS array but the nodes themselves stay in
Blink memory — so `JSHeapUsedSize`/`performance.memory` *understates* #4998 (it only sees the small
array-of-references) while *fully* counting the fork's `_all` retained HTML strings. A benchmark that
led with `performance.memory` would wrongly conclude #4998 is the lighter option. **Retained node
count is therefore the honest structural metric** (it counts detached-but-referenced nodes — proven by
the discriminator probe), with `measureUAM` DOM-bytes / real process RSS as the byte-level confirmation.
Report JS heap too, but framed as JS-side retention only, not total memory.

### Fairness verification (guard against strawmanning #4998)

Before trusting the `detach` arm's numbers, the harness verifies #4998 is actually active: at n=500 it
collapses **458/500** messages (children detached, IntersectionObserver firing). The arm exercises
their real behaviour, so its results are theirs, not a crippled reimplementation.

## Fairness protocol (the credibility contract)

1. **One deterministic corpus generator** — realistic mix (plain, markdown+code, images, agent
   multi-round). Content richness drives detached-heap cost, so it must be representative, seeded, and
   identical across arms.
2. **Same container, viewport, and scroll trajectory** for every arm; trajectory drives to the very top.
3. **GC-settled sampling** — `window.gc()` ×2 + settle frames before every memory sample; report the
   **median of K≥5 runs** with spread, never a single number.
4. **Length curve** — {100, 250, 500, 1000, 2000} messages. The unbounded-vs-bounded *divergence* is
   the point; the slope persuades where a single point does not.
5. **Scroll-back arm against the real server** — reuse the render-paging uvicorn harness; measure
   `evict`/`hybrid` scroll-back = round-trip + re-render vs `detach` = re-append. Report the trade.

## Metrics matrix (per arm × length)

`nodes_loaded`, `nodes_peak_at_top`, `jsheap_loaded`, `jsheap_peak`, `layout_ms_traj`,
`style_ms_traj`, `append_layout_ms` (streaming proxy), `scrollback_ms` (+ network for evict/hybrid).

## Deliverables

- `tests/bench/chat_history_bench.py` — generator, arms, CDP instrument, curve runner, JSON+markdown
  emitter. Runnable: `venv/bin/python tests/bench/chat_history_bench.py`.
- `tests/bench/vendor/chatVirtualizer_4998.js` — #4998 verbatim, with a provenance header.
- Generated results (`tests/bench/results/*.json` + a rendered table) — **generated output, never
  hand-written numbers** (claims discipline: no un-reproduced number in a permanent doc).

## Interpretation → upstream strategy (rewritten against the measured result)

The hybrid does **not** Pareto-dominate; eviction dominates the hybrid. Detach-preserve retains a
superset of what eviction retains over the same window, and a live window already gives instant recent
scroll-back at zero work and zero network. So the upstream ask is *not* "land #4998, then add a cold
tail." It is:

1. **Route-shadowing fix (#125)** — makes upstream's own merged pager actually run. A pure gift.
2. **Bounded-DOM eviction**, attached to existing issue **#4644** (which asks for DOM removal).
3. **A review comment on #4998**, offered as help rather than competition: their jank has one root
   cause — `node.offsetHeight` read inside the IntersectionObserver callback forces a synchronous
   layout per collapsing node. `entry.boundingClientRect.height` is already computed and free.

## Probe failures this harness has caught (why the guards exist)

Each of these produced a *plausible, flattering* number for the arm the author favoured. They are
recorded because the guards that now prevent them are otherwise unmotivated code.

| Artifact | Symptom | Guard now in place |
|---|---|---|
| 3-viewport pixel excursion never left `evict`'s window | exact `0.00ms` "win" | excursions are driven in **messages**, not pixels |
| walk-down stalled against `chatHistory.js` scroll anchoring | ~0ms for work never done; newest message never rendered | `walkDown()` returns `complete`; cell discarded when false |
| appended stream bubbles carried no `data-i` → `topVisible()` returned `Infinity` | `evict`'s entire scroll-back row measured an excursion that **never moved** | every bubble tagged; `topVisible()` returns `NaN`, not `Infinity` |
| `upBy()` under-delivered its message target | short excursion published as a fast one | `upBy()` returns `moved`; cell discarded when `moved < k`; `moved` published |
| JS-heap table | medians in MB, spreads in bytes | spread rendered through the value's formatter |

Two rules follow, and they are load-bearing:

- **An extreme value (`0.00`, a perfect tie, a suspiciously round number) means read the underlying
  record before concluding.** Every zero above survived a plausibility check and died on inspection.
- **Never edit the harness while a measurement run is in flight.** Python has already imported the
  module; the artifact will not correspond to the source, and no one can reproduce it. One run was
  discarded for exactly this.

## Known limitations (stated, not hidden)

- **The `evict` arm is not the code staged upstream.** It is the fork's 1090-line `MessageWindow`; the
  upstream PR implements eviction as ~112 lines in `sessions.js`. They share the mechanism, not the
  source. These results support "DOM removal beats detach-preserve on renderer memory" — they do not
  validate a specific implementation. See "What each arm actually is" above.

- **`evict`'s spacer compresses unrendered history**, so a fixed message-count excursion overshoots and
  it traverses *more* messages than the other arms. This biases the deep-scroll-back table **against**
  eviction — the arm the conclusion favours, i.e. the honest direction. `deepback_moved_msgs` is
  published so the asymmetry is auditable. (That the spacer misreports also means eviction's *scrollbar
  lies to the user* in the real app — a separate, real finding.)
- **Neither bounded arm produces a deep-scroll-back number**, for two different reasons, and the table
  says so rather than showing a flattering zero. `hybrid`'s top spacer drifts (fork issue #126) so its
  excursion falls short. `evict` walks the full excursion but its scroll anchoring defeats the driver's
  `scrollTop +=` walk and it never reaches the newest message. **Consequence: this benchmark supports no
  claim about eviction's deep scroll-back cost.** The refutation of the hybrid does not rest on those
  cells (it rests on memory, which is structural).
- **That `evict` cannot be driven back to the bottom is itself a lead, not just a harness quirk** — it
  may indicate a real "scrolling down never reaches the newest message" bug under programmatic scroll.
  Unverified in the real app; do not report it as a bug until reproduced there.
- **Network is excluded.** `evict`/`hybrid` refetch cold pages from the server in the real app; the
  harness serves them from memory. Their scroll-back numbers are a **lower bound**. Again: biased
  against the conclusion.
- **Ecological validity is an assumption, not a measurement.** These are headless-Chromium renderer
  numbers; the target runtime is QtWebEngine. Nothing here demonstrates the curves transfer.
