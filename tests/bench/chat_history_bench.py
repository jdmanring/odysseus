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
def _scroll_to_top_js(steps: int = 60) -> str:
    # Step the container to the top, yielding frames so IntersectionObserver /
    # scroll-driven paging/eviction actually fire. Drives all the way up so the
    # evict arm's _all retention and the detach arm's kept nodes are both measured.
    return f"""
      async () => {{
        const box = document.getElementById('chat-history');
        for (let s = 0; s < {steps}; s++) {{
          box.scrollTop = 0;
          await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
          if (box.scrollTop === 0 && s > 4) {{
            // give paging a couple extra frames to settle at the very top
            await new Promise(r => setTimeout(r, 30));
            if (box.scrollTop === 0) break;
          }}
        }}
        await new Promise(r => setTimeout(r, 60));
      }}
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
            for (let k = 0; k < 25; k++) {
                window.chatModule.addMessage('assistant',
                    '<p>Appended streamed message ' + k + '. ' +
                    'Lorem ipsum dolor sit amet consectetur adipiscing elit. '.repeat(3) + '</p>');
                const box = document.getElementById('chat-history');
                box.scrollTop = box.scrollHeight;
                await new Promise(r => requestAnimationFrame(r));
            }
            await new Promise(r => setTimeout(r, 60));
        }""")
        lay_after = layout_cost(cdp)

        # --- memory axis: drive to the very top so both the evict arm's _all retention
        # and the detach arm's kept-node retention are measured (fairness cuts both ways).
        page.evaluate(_scroll_to_top_js())
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
            "uss_mb", "rss_mb", "append_layout_ms", "append_style_ms")
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
                      f"jsheap={cell['jsheap_peak']/1e6:5.2f}MB  "
                      f"append_layout={cell['append_layout_ms']:6}ms  style={cell['append_style_ms']:6}ms")

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
            cells.append(_cell(fmt(v) if v is not None else None, r.get(key + "_spread")))
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
