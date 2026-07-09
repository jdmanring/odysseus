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
import statistics
import sys

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


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_cell(pw, arm: str, n: int) -> dict:
    browser = pw.chromium.launch(headless=True, args=LAUNCH_ARGS)
    try:
        page = browser.new_context(viewport=VIEWPORT).new_page()
        page.set_content(_HARNESS_HTML)
        cdp = page.context.new_cdp_session(page)
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

        return {
            "arm": arm, "n": n,
            "nodes_loaded": mem_loaded["nodes"], "nodes_peak": mem_peak["nodes"],
            "jsheap_loaded": mem_loaded["jsheap"], "jsheap_peak": mem_peak["jsheap"],
            "listeners_peak": mem_peak["listeners"],
            "append_layout_ms": round(lay_after["layout_ms"] - lay_before["layout_ms"], 2),
            "append_style_ms": round(lay_after["style_ms"] - lay_before["style_ms"], 2),
        }
    finally:
        browser.close()


def median_cell(pw, arm, n, repeats):
    runs = [run_cell(pw, arm, n) for _ in range(repeats)]
    out = {"arm": arm, "n": n, "repeats": repeats}
    for k in ("nodes_loaded", "nodes_peak", "jsheap_loaded", "jsheap_peak",
              "listeners_peak", "append_layout_ms", "append_style_ms"):
        vals = [r[k] for r in runs]
        out[k] = round(statistics.median(vals), 2)
        out[k + "_spread"] = round(max(vals) - min(vals), 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lengths", default="100,500,2000")
    ap.add_argument("--arms", default="naive,detach,evict")
    ap.add_argument("--repeats", type=int, default=3)
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
        for n in lengths:
            for arm in arms:
                cell = median_cell(pw, arm, n, args.repeats)
                rows.append(cell)
                print(f"  {arm:7} n={n:5}  nodes={cell['nodes_peak']:7}  "
                      f"jsheap={cell['jsheap_peak']/1e6:6.2f}MB  "
                      f"append_layout={cell['append_layout_ms']:7}ms")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "bench.json").write_text(json.dumps(rows, indent=2))
    _write_markdown(rows, lengths, arms)
    print(f"\nWrote {RESULTS_DIR/'bench.json'} and {RESULTS_DIR/'bench.md'}")


def _write_markdown(rows, lengths, arms):
    by = {(r["arm"], r["n"]): r for r in rows}
    lines = ["# Chat-history benchmark results (generated)\n",
             "Retained DOM nodes at the top of history (lower = memory bounded), post-GC JS heap "
             "(JS-side retention only — does NOT include #4998's detached DOM, which lives in C++/Blink "
             "memory; see the methodology doc's instrument caveat), and append layout cost (streaming "
             "into a large list). Generated by `tests/bench/chat_history_bench.py`; do not hand-edit.\n",
             "## Retained DOM nodes at top of history\n",
             "| n | " + " | ".join(arms) + " |", "|" + "---|" * (len(arms) + 1)]
    for n in lengths:
        lines.append(f"| {n} | " + " | ".join(str(by[(a, n)]["nodes_peak"]) for a in arms) + " |")
    lines.append("\n## Post-GC JS heap at top (MB)\n")
    lines.append("| n | " + " | ".join(arms) + " |")
    lines.append("|" + "---|" * (len(arms) + 1))
    for n in lengths:
        lines.append(f"| {n} | " + " | ".join(f"{by[(a,n)]['jsheap_peak']/1e6:.2f}" for a in arms) + " |")
    lines.append("\n## Append layout ms (streaming 25 msgs into an n-message list)\n")
    lines.append("| n | " + " | ".join(arms) + " |")
    lines.append("|" + "---|" * (len(arms) + 1))
    for n in lengths:
        lines.append(f"| {n} | " + " | ".join(str(by[(a,n)]["append_layout_ms"]) for a in arms) + " |")
    (RESULTS_DIR / "bench.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
