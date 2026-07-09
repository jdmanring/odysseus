# Chat-History Virtualization Benchmark — Methodology

**Purpose.** Produce a reproducible, apples-to-apples comparison of chat-history rendering strategies
on the two axes that matter — **renderer memory** and **layout/paint cost (lag)** — plus the axis the
memory-bound strategies trade away — **scroll-back latency**. The output is an artifact a skeptic
(upstream maintainer) can re-run and get the same *shape*, so the conclusion is not deniable.

**Non-goal.** A chart that only flatters one strategy. Every strategy's genuine win is reported. The
persuasive result is not "ours beats theirs" (a trade-off, waved off in one comment) but a **hybrid
that Pareto-dominates** — bounded memory *and* low layout cost *and* instant recent scroll-back.

---

## Strategies compared (real code, no strawmen)

| Arm | Source | Mechanism | Bounds |
|-----|--------|-----------|--------|
| `naive` | upstream merged pager (`45ee5a71`) shape | render page, prepend older on scroll-up, never remove | nothing (baseline) |
| `detach` | **vendored** upstream PR **#4998** `chatVirtualizer.js` (verbatim, with provenance) | off-screen: detach children into a JS array, pin wrapper height; restore on scroll-back | layout/paint only |
| `evict` | the fork's `static/js/chatHistory.js` (`MessageWindow`) | remove off-screen nodes; refetch from server on scroll-back | rendered DOM nodes (but `_all` data grows) |
| `hybrid` | new (this benchmark) | live band → warm band (detach-preserve, #4998 technique) → cold tail (evict nodes **and** `_all`, refetch) | rendered DOM nodes **and** retained data |

Vendoring #4998's actual code (not a reimplementation) is a hard requirement: a benchmark that
reimplements a rival and makes it look bad is dismissed on sight.

## Honest claims (corrected against the code, 2026-07-08)

- **`evict` is not "flat RSS."** `chatHistory.js` never evicts `_all` (verified: `_all` is only
  read/concatenated, never spliced). Scrolling to the top of an N-message history retains N
  already-rendered HTML **strings** in `_all`. That is far lighter than #4998's retained live DOM
  subtrees, but it is O(history-scrolled), not flat. The headline is "bounded rendered DOM + cheap
  string retention," and the scroll trajectory **must drive to the very top** so this cost is measured,
  not hidden. Fairness cuts against us too.
- **`detach` genuinely wins two things:** layout/paint parity with the bounded strategies, and
  **instant, zero-network scroll-back** (array re-append vs our server round-trip). Both are reported.
- **The hybrid's claim:** matches `detach` on layout and on recent scroll-back (warm band is detach),
  and matches `evict` on memory for deep history (cold tail frees both nodes and `_all`).

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
4. **`performance.measureUserAgentSpecificMemory()` DOM-bytes** — authoritative DOM byte breakdown.
   Optional corroboration; requires a COOP/COEP cross-origin-isolated server. Not a dependency (1–3
   work today and are decisive).
5. **Real-app process RSS** — the fork's Qt-wrapper `[MEM]` telemetry on the actual target, as
   ground-truth confirmation that the harness curves reflect real RSS. Referenced, not re-derived here.

Flags: `--enable-precise-memory-info`, `--js-flags=--expose-gc`.

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

## Interpretation → upstream strategy

If the hybrid Pareto-dominates (expected from the probe: `detach` node-count stays at history size,
`evict`/`hybrid` sawtooth low; layout parity across bounded arms; hybrid keeps `detach`'s instant
recent scroll-back), the upstream ask is not "replace #4998." It is: **land #4998 for lag, then add the
cold-tail eviction increment** (this benchmark's hybrid delta) tied to issue #4644 (which asks for DOM
removal). Small, single-purpose, complementary — and backed by numbers the maintainer re-runs.
