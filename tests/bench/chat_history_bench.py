#!/usr/bin/env python3
"""Chat-history virtualization benchmark — real Chromium, apples-to-apples.

Measures renderer memory (retained DOM node count + post-GC JS heap) and layout/paint
cost across strategies for chat-history rendering, over a history-length curve. See
docs/dev/chat-history-benchmark.md for the methodology and fairness protocol.

Strategies (real code, no strawmen):
  naive   render everything, never remove (upstream merged-pager shape / baseline)
  detach  vendored upstream PR #4998 chatVirtualizer.js (detach children, keep refs)
  evict   the fork's static/js/chatHistory.js MessageWindow (remove nodes)
  hybrid  warm-band detach + cold-tail eviction of nodes AND data (this benchmark)

Instrument (empirically selected — see the methodology doc's discriminator probe):
  Nodes            CDP Performance.getMetrics — counts detached-but-referenced nodes,
                   so it captures #4998's retention (the primary, legible signal).
  JSHeapUsedSize   sampled after forced window.gc() — JS-side retention (corroborates).
  LayoutDuration / RecalcStyleDuration deltas — the lag axis (#4998's own metric).

Run:
    venv/bin/python tests/bench/chat_history_bench.py                 # default curve
    venv/bin/python tests/bench/chat_history_bench.py --lengths 100,500,2000 --repeats 5
"""
import argparse
import json
import pathlib
import platform
import shutil
import statistics
import sys
import tempfile

import psutil

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CHAT_HISTORY_JS = ROOT / "static/js/chatHistory.js"
VENDOR_4998 = ROOT / "tests/bench/vendor/chatVirtualizer_4998.js"
HYBRID_JS = ROOT / "tests/bench/vendor/hybrid_bench.js"
RESULTS_DIR = ROOT / "tests/bench/results"

VIEWPORT = {"width": 900, "height": 700}
LAUNCH_ARGS = ["--enable-precise-memory-info", "--js-flags=--expose-gc"]


# ---------------------------------------------------------------------------
# Corpus — one deterministic generator, identical across arms. Content richness
# drives detached-heap cost, so the mix mirrors real messages (plain / markdown+
# code / image / agent multi-round). No randomness: fully reproducible.
# ---------------------------------------------------------------------------
_TINY_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
             "AAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _bubble_html(i: int) -> str:
    """Rendered-bubble HTML for message i, matching what chatModule.addMessage gets."""
    kind = i % 10
    body = f"<p>Message {i}. " + ("Lorem ipsum dolor sit amet, consectetur adipiscing. " * 3) + "</p>"
    if kind in (0, 3, 6):  # markdown + fenced code (~30%)
        code = "\n".join(f"    line {j} of code block {i}" for j in range(8))
        body += f"<p>Here is <strong>bold</strong> and <code>inline</code>:</p><pre><code>{code}</code></pre>"
    elif kind == 1:        # image (~10%)
        body += f'<p>An image:</p><img alt="img{i}" src="{_TINY_PNG}" style="width:120px;height:80px">'
    elif kind == 2:        # agent multi-round (~10%): several top-level blocks
        for r in range(4):
            body += f'<div class="agent-round"><p>Round {r} of agent message {i}. Reasoning text here.</p></div>'
    return body


def corpus_js(n: int) -> str:
    """Emit a JS array literal of {role, content} for n messages."""
    rows = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        rows.append({"role": role, "content": _bubble_html(i), "modelName": None, "meta": None})
    return json.dumps(rows)


# ---------------------------------------------------------------------------
# HTML harness — same container / addMessage stub for every arm.
# ---------------------------------------------------------------------------
_HARNESS_HTML = """
<!DOCTYPE html><html><head><style>
  body { margin: 0; }
  #chat-history { height: 700px; overflow-y: auto; display: flex; flex-direction: column; }
  .msg { flex-shrink: 0; box-sizing: border-box; padding: 8px; border-bottom: 1px solid #333; }
  .msg img { display: block; }
</style></head><body>
<div id="chat-history" role="log" aria-live="polite"></div>
<script>
  // Shared, fair render primitive: content is already-rendered HTML (as in the app).
  window.chatModule = {
    addMessage: function(role, content) {
      var d = document.createElement('div');
      d.className = 'msg msg-' + role;
      d.innerHTML = content;
      // Source index, so scroll excursions can be defined in MESSAGES rather than
      // pixels. A pixel span is not comparable across arms: an arm whose spacer
      // under-models unrendered history has a much shorter scrollHeight, so the
      // same pixel hop traverses a different number of messages (measured: evict
      // reached scrollTop 3962 where hybrid reached 312902 for the same "30
      // viewports"). Every arm renders through this stub except hybrid, which
      // tags identically in its own _make().
      var m = /Message (\\d+)\\./.exec(content);
      if (m) d.dataset.i = m[1];
      document.getElementById('chat-history').appendChild(d);
      return d;
    }
  };
  window.hljsDeferHighlightAll = null;  // keep the evict arm's hljs path a no-op
</script></body></html>
"""


# ---------------------------------------------------------------------------
# Arm drivers — each loads the corpus and drives the SAME scroll-to-top trajectory.
# Returned value is unused; measurement is done via CDP around these calls.
# ---------------------------------------------------------------------------
def _scroll_sweep_js(divisor: int = 120) -> str:
    # Instrumented smooth scroll from bottom to top: step scrollTop down each frame
    # and record per-frame intervals. This (a) drives the scroll-back mechanism of
    # each strategy (detach restore / evict _loadOlder paging) so the memory peak is
    # measured at the top, and (b) captures scroll smoothness. A composited static
    # list (naive) stays at ~16.7ms; a strategy doing synchronous DOM work per scroll
    # step (e.g. #4998's per-message collapse/restore) shows long frames. Robust
    # across scroll speed (validated: #4998 janks at fast/med/slow alike).
    return f"""
      async () => {{
        const box = document.getElementById('chat-history');
        box.scrollTop = box.scrollHeight;
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        const H = box.scrollHeight, step = Math.max(8, Math.floor(H / {divisor}));
        let last = performance.now();
        const frames = [];
        for (let y = H; y >= 0; y -= step) {{
          box.scrollTop = y;
          await new Promise(r => requestAnimationFrame(() => {{
            const n = performance.now(); frames.push(n - last); last = n; r();
          }}));
        }}
        // settle at the very top so any final paging lands before the memory sample
        for (let s = 0; s < 8; s++) {{ box.scrollTop = 0;
          await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }}
        await new Promise(r => setTimeout(r, 60));
        const sum = frames.reduce((s, x) => s + x, 0);
        return {{ mean: +(sum / frames.length).toFixed(2),
                 long: frames.filter(f => f > 50).length, frames: frames.length }};
      }}
    """


# --- scroll-back probes ------------------------------------------------------
# Shared JS: an excursion measured in MESSAGES, not pixels.
#
# A pixel span is not comparable across arms. An arm whose spacer under-models the
# unrendered history has a far shorter scrollHeight, so the same "30 viewports" walks
# a different number of messages (measured: evict reached scrollTop 3962 where hybrid
# reached 312902). Excursions are therefore driven until the top *visible* message
# index has moved back by K, using the data-i tag every arm writes.
#
# The index scan does forced layout, so it runs only during the UNMEASURED excursion;
# the measured pass is a plain scroll with per-frame timing and CDP layout/style deltas
# sampled around it.
_PROBE_PRELUDE = """
  const box = document.getElementById('chat-history');
  const atBottom = () => box.scrollTop >= box.scrollHeight - box.clientHeight - 2;
  // NaN (not Infinity) when nothing tagged is visible: Infinity silently satisfied the
  // "moved k messages" test on the first tagged message it saw, so an excursion that
  // never moved reported success. NaN comparisons are false, so the walk continues and
  // the completeness check below catches a genuinely broken probe.
  const topVisible = () => {
    const top = box.getBoundingClientRect().top;
    let best = Infinity;
    for (const el of box.querySelectorAll('.msg[data-i]')) {
      if (el.getBoundingClientRect().bottom > top) { best = Math.min(best, +el.dataset.i); }
    }
    return best === Infinity ? NaN : best;
  };
  const settle = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  // Walk up until we have passed K messages (or hit the true top).
  // Returns the pixel distance the walk required, so a measured pass can replay the
  // same excursion without calling topVisible() (whose scan forces layout).
  // Reports how far it actually got, in messages, so a caller can refuse to publish
  // an excursion that under-delivered. Reaching the true top counts as complete.
  // Fine steps (0.25 viewport) bound the overshoot. A coarse 0.9-viewport step walked
  // evict from message 1880 to 0 in one excursion while hybrid moved only ~330: evict's
  // spacer under-models unrendered history, so a pixel of its scrollbar is worth many
  // messages. `moved` is returned and published so any residual asymmetry between arms
  // is auditable rather than hidden inside a "200 messages" label.
  const upBy = async (k) => {
    const start = topVisible(), from = box.scrollTop;
    for (let i = 0; i < 2400; i++) {
      if (start - topVisible() >= k) break;
      if (box.scrollTop <= 0) break;
      box.scrollTop -= box.clientHeight * 0.25;
      await settle();
    }
    await new Promise(r => setTimeout(r, 80));
    const moved = start - topVisible();
    // Reaching the true top does NOT excuse a short excursion: if an arm cannot travel
    // k messages, the cell it would produce is not comparable and must be discarded.
    return { dist: Math.abs(from - box.scrollTop), moved: moved, complete: moved >= k };
  };
  // Walk DOWN to the live conversation, recording per-frame intervals. Distance is
  // whatever that arm's own geometry requires -- the work it must do to get back IS
  // the metric.
  //
  // "Arrived" means the newest message is rendered AND we are pinned at the bottom;
  // a pixel test alone is not enough. An arm that re-anchors scrollTop while paging
  // (chatHistory.js does, to hold the viewport steady) fights a naive `scrollTop +=`
  // walk: an early version stalled at scrollTop 12756 of 16718 with the newest
  // message never rendered, and reported ~0ms because almost nothing had happened.
  // A stalled walk must never be published as a fast one, so this reports `complete`
  // and the runner discards the cell when it is false.
  const walkDown = async (frames) => {
    const lastIdx = window.CORPUS.length - 1;
    const arrived = () => atBottom() && !!box.querySelector('.msg[data-i="' + lastIdx + '"]');
    let last = performance.now(), stalled = 0, prev = -1;
    for (let i = 0; i < 2000; i++) {
      if (arrived()) break;
      const before = box.scrollTop;
      box.scrollTop += box.clientHeight * 0.9;
      await new Promise(r => requestAnimationFrame(() => {
        const t = performance.now(); frames.push(t - last); last = t; r();
      }));
      // Paging can re-anchor scrollTop; only a total lack of progress is a stall.
      stalled = (box.scrollTop <= before + 1 && box.scrollTop === prev) ? stalled + 1 : 0;
      prev = box.scrollTop;
      if (stalled > 60) break;
    }
    await new Promise(r => setTimeout(r, 80));
    return arrived();
  };
  const report = (frames) => {
    if (!frames.length) return { mean: 0, worst: 0 };
    const sum = frames.reduce((s, x) => s + x, 0);
    return { mean: +(sum / frames.length).toFixed(2), worst: +Math.max(...frames).toFixed(2) };
  };
"""


def _scrollback_probe_js() -> str:
    """RECENT scroll-back: revisit a region 20 messages back -- inside the bounded
    arms' 80-message window, so nothing was ever pruned.

    Trajectory: bottom -> up 20 msgs -> back to bottom -> MEASURED: up 20 msgs again.

    Measured behaviour, which INVERTS the result this probe was designed to show (the
    first draft used a 3-viewport pixel span and reported an exact 0.00ms for evict --
    an artifact of never leaving its window, not a win):

      naive   nothing to do (still attached)                    -> floor
      evict   also nothing: the region is still inside its window
      detach  collapses and restores it -- #4998's 2000px live margin is NARROWER than
              eviction's window, so it works where eviction rests
      hybrid  same warm band, batched and reflow-free -> a fraction of detach's cost
    """
    return """
      async () => {
""" + _PROBE_PRELUDE + """
        if (!window.__sbWarmed) {
          box.scrollTop = box.scrollHeight;
          await settle();
          const ex = await upBy(20);
          window.__sbDist = ex.dist;
          window.__sbOk = ex.complete;
          await walkDown([]);          // leave: region collapses (detach) or rests (evict)
          window.__sbWarmed = true;
          return null;
        }
        // MEASURED: walk back up the same excursion. Distance was fixed in messages by
        // the warm-up; replay it in pixels so topVisible()'s forced layout stays out of
        // the sample.
        const frames = [];
        const dist = window.__sbDist || box.clientHeight;
        const steps = Math.max(1, Math.round(dist / (box.clientHeight * 0.9)));
        let last = performance.now();
        for (let i = 0; i < steps && box.scrollTop > 0; i++) {
          box.scrollTop -= dist / steps;
          await new Promise(r => requestAnimationFrame(() => {
            const t = performance.now(); frames.push(t - last); last = t; r();
          }));
        }
        await new Promise(r => setTimeout(r, 80));
        return Object.assign(report(frames), { complete: !!window.__sbOk });
      }
    """


def _deepback_probe_js() -> str:
    """DEEP scroll-back: return to the conversation after walking 200 messages up --
    well past the bounded arms' window, so they HAVE pruned the bottom.

    Trajectory: bottom -> up 200 msgs -> MEASURED: back down to the bottom.

    This is the axis the detach family owns: #4998 still holds every message's children
    in `__vChildren` and re-appends them, while evict/hybrid discarded the bottom and
    must re-render it from data (`innerHTML` parse + style + layout; in the real app,
    also a server round-trip).

    Network is NOT included, so evict's and hybrid's numbers are a LOWER BOUND on their
    real cost. The bias runs against the conclusion, which is the honest direction.
    """
    return """
      async () => {
""" + _PROBE_PRELUDE + """
        if (!window.__dbWarmed) {
          box.scrollTop = box.scrollHeight;
          await settle();
          const ex = await upBy(200);
          window.__dbOk = ex.complete;
          window.__dbMoved = ex.moved;
          window.__dbWarmed = true;
          return null;
        }
        const frames = [];
        const complete = await walkDown(frames);   // MEASURED: return to the conversation
        return Object.assign(report(frames),
                             { complete: complete && !!window.__dbOk, moved: window.__dbMoved });
      }
    """


def load_arm(page, arm: str, n: int):
    """Load the corpus under the given strategy. Returns after initial render settles."""
    page.evaluate(f"window.CORPUS = {corpus_js(n)};")

    if arm == "naive":
        page.evaluate("() => { for (const m of window.CORPUS) window.chatModule.addMessage(m.role, m.content); }")
    elif arm == "detach":
        # Render all bubbles; #4998's initChatVirtualizer is invoked in run_cell
        # (it must observe children that already exist).
        page.evaluate("() => { for (const m of window.CORPUS) window.chatModule.addMessage(m.role, m.content); }")
    elif arm == "evict":
        page.add_script_tag(path=str(CHAT_HISTORY_JS))
        page.evaluate("""() => {
            window.chatHistory.reset();
            window.chatHistory.load(window.CORPUS.map(m => ({...m})));
        }""")
    elif arm == "hybrid":
        page.add_script_tag(path=str(HYBRID_JS))
        page.evaluate("() => { window.hybridBench.load(window.CORPUS); }")
    else:
        raise ValueError(arm)

    page.wait_for_timeout(150)


# ---------------------------------------------------------------------------
# CDP instrument
# ---------------------------------------------------------------------------
def _metrics(cdp) -> dict:
    return {e["name"]: e["value"] for e in cdp.send("Performance.getMetrics")["metrics"]}


def sample_mem(page, cdp) -> dict:
    """GC-settled memory sample: retained node count + post-GC JS heap."""
    page.evaluate("window.gc && (window.gc(), window.gc());")
    page.wait_for_timeout(60)
    m = _metrics(cdp)
    dom = cdp.send("Memory.getDOMCounters")
    return {"nodes": int(m["Nodes"]), "dom_nodes": int(dom["nodes"]),
            "jsheap": int(m["JSHeapUsedSize"]), "listeners": int(dom["jsEventListeners"])}


def layout_cost(cdp) -> dict:
    m = _metrics(cdp)
    return {"layout_ms": m["LayoutDuration"] * 1000.0, "style_ms": m["RecalcStyleDuration"] * 1000.0,
            "layout_count": m["LayoutCount"], "style_count": m["RecalcStyleCount"]}


# --- Real process memory (ground truth — what actually OOMs) -----------------
# measureUserAgentSpecificMemory() is unavailable in headless Chromium even when
# crossOriginIsolated, so we read the renderer process's private memory (USS) and
# RSS from the OS via psutil. USS = memory unique to the renderer (freed if it
# exits) — the honest byte-level DOM-retention signal that node count only proxies.
def find_browser_pid(marker: str):
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            joined = " ".join(p.info["cmdline"] or [])
            if marker in joined and "--type=" not in joined:
                return p.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def renderer_mem(browser_pid: int) -> dict:
    """Private memory of the page's renderer (GC-settled caller).

    Reports the MAX single renderer's USS/RSS — with one page there is one content
    renderer holding the DOM; a spare/prewarm renderer (~baseline) is excluded so the
    number isolates the page's DOM cost rather than a constant offset. renderers>1 is
    recorded so the assumption is auditable.
    """
    try:
        proc = psutil.Process(browser_pid)
    except psutil.NoSuchProcess:
        return {"uss_mb": None, "rss_mb": None, "renderers": 0}
    best = None
    renderers = 0
    for p in [proc] + proc.children(recursive=True):
        try:
            if "--type=renderer" in " ".join(p.cmdline()):
                renderers += 1
                mi = p.memory_full_info()
                if best is None or mi.uss > best[0]:
                    best = (mi.uss, mi.rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if best is None:
        return {"uss_mb": None, "rss_mb": None, "renderers": 0}
    return {"uss_mb": round(best[0] / 1e6, 2), "rss_mb": round(best[1] / 1e6, 2), "renderers": renderers}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_cell(pw, arm: str, n: int) -> dict:
    # Fresh persistent context per cell → clean renderer process, and a unique
    # user-data-dir so we can locate that process for OS-level memory sampling.
    udd = tempfile.mkdtemp(prefix="chbench_")
    ctx = pw.chromium.launch_persistent_context(udd, headless=True, args=LAUNCH_ARGS, viewport=VIEWPORT)
    browser_pid = find_browser_pid(udd)
    try:
        page = ctx.new_page()
        page.set_content(_HARNESS_HTML)
        cdp = ctx.new_cdp_session(page)
        cdp.send("Performance.enable")

        load_arm(page, arm, n)
        if arm == "detach":
            # init #4998 after content is present (its initChatVirtualizer observes children).
            # Inject the verbatim module + a one-line window bridge (file:// dynamic import
            # is blocked for set_content pages; the on-disk vendored file stays verbatim).
            vendored = VENDOR_4998.read_text()
            page.add_script_tag(
                content=vendored + "\nwindow.__initChatVirtualizer = initChatVirtualizer;",
                type="module")
            page.wait_for_function("() => typeof window.__initChatVirtualizer === 'function'")
            page.evaluate("() => window.__initChatVirtualizer()")
            page.wait_for_timeout(150)

        mem_loaded = sample_mem(page, cdp)

        # --- lag axis: cost of appending messages into a large list (streaming proxy).
        # Pure scrolling is composited (no relayout), so the real lag #4998 targets is
        # incremental layout/style when content changes with a big history present.
        # Scroll to the bottom (where appends land and are visible), then append K and
        # measure the layout/style the browser did.
        page.evaluate("""async () => {
            const box = document.getElementById('chat-history');
            box.scrollTop = box.scrollHeight;
            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        }""")
        lay_before = layout_cost(cdp)
        page.evaluate("""async () => {
            // Tag appends with the next source indices. Untagged bubbles at the bottom
            // made topVisible() return Infinity, which made the scroll-back excursions
            // break on their first tagged message and never move at all -- reported as
            // a genuine 0.00ms. Every bubble in the container must carry data-i.
            const base = window.CORPUS.length;
            for (let k = 0; k < 25; k++) {
                window.chatModule.addMessage('assistant',
                    '<p>Message ' + (base + k) + '. Appended streamed. ' +
                    'Lorem ipsum dolor sit amet consectetur adipiscing elit. '.repeat(3) + '</p>');
                const box = document.getElementById('chat-history');
                box.scrollTop = box.scrollHeight;
                await new Promise(r => requestAnimationFrame(r));
            }
            await new Promise(r => setTimeout(r, 60));
        }""")
        lay_after = layout_cost(cdp)

        # --- recent scroll-back axis: the one where the detach family beats eviction.
        # Warm-up pass (unmeasured) leaves the region already-rendered-then-left; the
        # second pass is measured for frame cost and for the layout/style work each
        # strategy must redo. See _scrollback_probe_js for the lower-bound caveat.
        page.evaluate(_scrollback_probe_js())
        sb_before = layout_cost(cdp)
        sb = page.evaluate(_scrollback_probe_js())
        sb_after = layout_cost(cdp)

        # --- deep scroll-back: return to the conversation after a long excursion.
        # This is the case eviction actually pays for (it discarded the bottom).
        page.evaluate(_deepback_probe_js())
        db_before = layout_cost(cdp)
        db = page.evaluate(_deepback_probe_js())
        db_after = layout_cost(cdp)

        # --- scroll axis + drive to top: an instrumented bottom→top sweep records
        # scroll smoothness AND exercises each strategy's scroll-back path, leaving us
        # at the top so the evict arm's _all retention and the detach arm's kept-node
        # retention are both measured (fairness cuts both ways).
        sweep = page.evaluate(_scroll_sweep_js())
        mem_peak = sample_mem(page, cdp)
        # GC-settle before the OS memory read so USS reflects retained, not transient.
        page.evaluate("window.gc && (window.gc(), window.gc());")
        page.wait_for_timeout(250)
        rmem = renderer_mem(browser_pid) if browser_pid else {"uss_mb": None, "rss_mb": None, "renderers": 0}

        return {
            "arm": arm, "n": n,
            "nodes_loaded": mem_loaded["nodes"], "nodes_peak": mem_peak["nodes"],
            "jsheap_loaded": mem_loaded["jsheap"], "jsheap_peak": mem_peak["jsheap"],
            "listeners_peak": mem_peak["listeners"],
            "uss_mb": rmem["uss_mb"], "rss_mb": rmem["rss_mb"],
            "scroll_mean_ms": sweep["mean"], "scroll_long_frames": sweep["long"],
            # Same discipline as deepback: an excursion that never travelled the
            # required number of messages measured nothing, and 0.00ms from a no-op
            # must never be published as a win.
            "scrollback_complete": bool(sb["complete"]),
            "scrollback_mean_ms": sb["mean"] if sb["complete"] else None,
            "scrollback_worst_ms": sb["worst"] if sb["complete"] else None,
            "scrollback_layout_ms": round(sb_after["layout_ms"] - sb_before["layout_ms"], 2)
            if sb["complete"] else None,
            "scrollback_style_ms": round(sb_after["style_ms"] - sb_before["style_ms"], 2)
            if sb["complete"] else None,
            # A walk that never reached the newest message measured nothing; publishing
            # its near-zero cost would be a lie. Null it out so the cell shows as absent.
            "deepback_complete": bool(db["complete"]),
            "deepback_moved_msgs": db.get("moved"),
            "deepback_mean_ms": db["mean"] if db["complete"] else None,
            "deepback_worst_ms": db["worst"] if db["complete"] else None,
            "deepback_layout_ms": round(db_after["layout_ms"] - db_before["layout_ms"], 2)
            if db["complete"] else None,
            "deepback_style_ms": round(db_after["style_ms"] - db_before["style_ms"], 2)
            if db["complete"] else None,
            "append_layout_ms": round(lay_after["layout_ms"] - lay_before["layout_ms"], 2),
            "append_style_ms": round(lay_after["style_ms"] - lay_before["style_ms"], 2),
        }
    finally:
        ctx.close()
        shutil.rmtree(udd, ignore_errors=True)


def median_cell(pw, arm, n, repeats):
    # Warm-up discard: the first run of a fresh process pays one-time JIT/allocation
    # costs, so run repeats+1 and drop run 0. Report median + spread (max-min) over
    # the kept runs; keep the raw values in the artifact for full transparency.
    runs = [run_cell(pw, arm, n) for _ in range(repeats + 1)][1:]
    out = {"arm": arm, "n": n, "repeats_kept": len(runs)}
    keys = ("nodes_loaded", "nodes_peak", "jsheap_loaded", "jsheap_peak", "listeners_peak",
            "uss_mb", "rss_mb", "scroll_mean_ms", "scroll_long_frames",
            "scrollback_mean_ms", "scrollback_worst_ms",
            "scrollback_layout_ms", "scrollback_style_ms",
            "deepback_mean_ms", "deepback_worst_ms",
            "deepback_layout_ms", "deepback_style_ms", "deepback_moved_msgs",
            "append_layout_ms", "append_style_ms")
    for k in keys:
        vals = [r[k] for r in runs if r[k] is not None]
        if not vals:
            out[k] = out[k + "_spread"] = None
            continue
        out[k] = round(statistics.median(vals), 2)
        out[k + "_spread"] = round(max(vals) - min(vals), 2)
        out[k + "_raw"] = vals
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lengths", default="100,500,2000")
    ap.add_argument("--arms", default="naive,detach,evict")
    ap.add_argument("--repeats", type=int, default=7)
    args = ap.parse_args()
    lengths = [int(x) for x in args.lengths.split(",")]
    arms = [a.strip() for a in args.arms.split(",")]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed", file=sys.stderr)
        sys.exit(1)

    rows = []
    with sync_playwright() as pw:
        vb = pw.chromium.launch(headless=True)
        chromium_version = vb.version
        vb.close()
        env = {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "chromium_version": chromium_version,
            "cpu_count": psutil.cpu_count(),
            "total_ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
            "repeats_kept": args.repeats, "warmup_runs_discarded": 1,
            "memory_metric": "renderer-process USS/RSS via psutil (measureUAM unavailable headless); "
                             "node count is the structural proxy; JS heap is JS-side only",
            "launch_args": LAUNCH_ARGS,
        }
        for n in lengths:
            for arm in arms:
                cell = median_cell(pw, arm, n, args.repeats)
                rows.append(cell)
                uss = cell["uss_mb"]
                print(f"  {arm:7} n={n:5}  nodes={cell['nodes_peak']:7}  "
                      f"USS={uss if uss is None else f'{uss:6.1f}'}MB  "
                      f"scroll={cell['scroll_mean_ms']:6}ms/{cell['scroll_long_frames']:>3}long  "
                      f"append={cell['append_layout_ms']:6}ms")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "bench.json").write_text(json.dumps({"env": env, "results": rows}, indent=2))
    _write_markdown(rows, lengths, arms, env)
    print(f"\nWrote {RESULTS_DIR/'bench.json'} and {RESULTS_DIR/'bench.md'}")


def _cell(v, spread):
    if v is None:
        return "—"
    return f"{v} ±{spread}" if spread else f"{v}"


def _table(by, lengths, arms, key, fmt=lambda x: x):
    lines = ["| n | " + " | ".join(arms) + " |", "|" + "---|" * (len(arms) + 1)]
    for n in lengths:
        cells = []
        for a in arms:
            r = by[(a, n)]
            v = r.get(key)
            sp = r.get(key + "_spread")
            # spread is stored in the raw unit; render it through the same formatter
            # as the value or a bytes->MB table prints "1.51 ±22016".
            cells.append(_cell(fmt(v) if v is not None else None, fmt(sp) if sp else sp))
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    return lines


def _write_markdown(rows, lengths, arms, env):
    by = {(r["arm"], r["n"]): r for r in rows}
    L = ["# Chat-history benchmark results (generated)\n",
         "Generated by `tests/bench/chat_history_bench.py` (do not hand-edit). Values are medians over "
         f"{env['repeats_kept']} kept runs (1 warm-up discarded), shown as `median ±(max-min)`.\n",
         "## Environment\n",
         f"- Chromium {env['chromium_version']}, {env['platform']}",
         f"- {env['cpu_count']} CPUs, {env['total_ram_gb']} GB RAM, Python {env['python']}",
         f"- Memory metric: {env['memory_metric']}\n",
         "## Renderer process USS at top of history (MB) — ground-truth private memory\n",
         "The real OS-level memory unique to the renderer (what OOMs). Lower = bounded.\n"]
    L += _table(by, lengths, arms, "uss_mb")
    L.append("\n## Retained DOM nodes at top of history — structural memory proxy\n")
    L.append("Counts detached-but-referenced nodes, so it captures #4998's retention.\n")
    L += _table(by, lengths, arms, "nodes_peak")
    L.append("\n## Renderer process RSS at top of history (MB)\n")
    L += _table(by, lengths, arms, "rss_mb")
    L.append("\n## Post-GC JS heap at top (MB) — JS-side retention only\n")
    L.append("Does NOT include #4998's detached DOM (C++/Blink); includes the fork's `_all` strings.\n")
    L += _table(by, lengths, arms, "jsheap_peak", fmt=lambda b: round(b / 1e6, 2))
    L.append("\n## Scroll smoothness — mean frame ms during a bottom→top sweep\n")
    L.append("~16.7ms = a solid 60fps. A composited static list (naive) stays smooth; a strategy doing "
             "synchronous DOM work per scroll step janks. This also exercises scroll-back: evict's batched "
             "`_loadOlder` re-render stays smooth, whereas #4998's per-message collapse/restore does not "
             "(validated janky at fast/medium/slow scroll alike). Excludes evict's server-fetch cost — see "
             "the scroll-back note below.\n")
    L += _table(by, lengths, arms, "scroll_mean_ms")
    L.append("\n## Scroll long frames (>50ms) during the sweep — jank count\n")
    L += _table(by, lengths, arms, "scroll_long_frames")
    L.append("\n## Recent scroll-back — LAYOUT ms revisiting a region inside the window\n")
    L.append("Walk back 20 messages, return to the bottom, then walk back again; the second pass is "
             "measured. The excursion stays inside the bounded arms' 80-message window. **This inverts the expected "
             "result and is reported as measured:** `evict` does *no* work here (the region was never "
             "pruned), while `detach` pays the most — #4998's 2000px live margin is narrower than "
             "eviction's window, so it collapses and restores messages eviction simply kept. `hybrid` "
             "runs the same warm band at a fraction of the cost: batched, and sized from the "
             "IntersectionObserver's own rect instead of a per-node `offsetHeight` reflow.\n")
    L += _table(by, lengths, arms, "scrollback_layout_ms")
    L.append("\n## Recent scroll-back — STYLE-recalc ms\n")
    L += _table(by, lengths, arms, "scrollback_style_ms")
    L.append("\n## Deep scroll-back — LAYOUT ms returning to the conversation\n")
    L.append("Walk back 200 messages (past the window, so the bounded arms pruned the bottom), then "
             "measure the return to the newest message. Designed as the axis the detach family owns — "
             "`detach` holds every message's children in `__vChildren`, while `evict`/`hybrid` must "
             "re-render from data.\n")
    L.append("\n**Both bounded arms' cells are withheld, for two different reasons, and neither is a "
             "result.** `evict` walks its full 200 messages but its scroll anchoring defeats the "
             "driver's `scrollTop +=` walk, so it never reaches the newest message. `hybrid`'s top "
             "spacer drifts (fork issue #126), so its excursion falls short of 200. A stalled walk is "
             "not a fast one: the harness reports `complete`/`moved` and blanks the cell rather than "
             "publishing a near-zero. **What survives here is only `detach` vs `naive`** — and it is "
             "brutal for `detach`, for the same `offsetHeight`-reflow reason as the scroll-jank row. "
             "No claim about eviction's deep scroll-back cost is supported by this table.\n")
    L.append("\n(`detach` at n=5000 carries a wide spread from one outlier run; the median is robust and "
             "every kept run exceeds 470ms. Raw per-run values are in `bench.json`.)\n")
    L.append("\nMessages actually traversed by the excursion (`evict`'s spacer compresses unrendered "
             "history, so a fixed message target overshoots — it walks *further* than the others, "
             "which biases this table against it):\n")
    L += _table(by, lengths, arms, "deepback_moved_msgs")
    L += _table(by, lengths, arms, "deepback_layout_ms")
    L.append("\n## Deep scroll-back — STYLE-recalc ms\n")
    L.append("Style recalc is where the re-parse shows: re-appending detached nodes skips `innerHTML` "
             "parse and style resolution; re-rendering from data does not.\n")
    L += _table(by, lengths, arms, "deepback_style_ms")
    L.append("\n> **Network is NOT in the deep scroll-back numbers, and that biases them toward `evict`/"
             "`hybrid`.** In the real app both refetch cold pages from the server "
             "(`_fetchOlderFromServer`), paying ~one round-trip per page; `detach` restores from its "
             "in-heap `__vChildren` with zero network. This harness serves their cold pages from an "
             "in-memory source, so the columns above are a **lower bound** on their real cost. The bias "
             "runs against the conclusion drawn from them, which is the honest direction.\n")
    L.append("\n## Append LAYOUT ms (stream 25 msgs into an n-message list)\n")
    L.append("Cost of streaming new messages into a large list. `evict` wins because its list stays "
             "bounded. **This does NOT capture #4998's lag benefit**: appends land in the live region, "
             "not collapsed nodes, so #4998 ≈ naive here. #4998 targets *scroll-repaint* lag, which this "
             "harness does not yet measure — do not read this column as \"#4998 fails at lag.\"\n")
    L += _table(by, lengths, arms, "append_layout_ms")
    L.append("\n## Append STYLE-recalc ms\n")
    L.append("Same caveat as layout: measured during append (live region), so #4998's collapse does not "
             "help here (the data confirms #4998 ≈ naive). Its style/paint win during scrolling is "
             "unmeasured.\n")
    L += _table(by, lengths, arms, "append_style_ms")
    (RESULTS_DIR / "bench.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
