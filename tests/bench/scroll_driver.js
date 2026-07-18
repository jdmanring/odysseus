/* Shared scroll drivers for benches and regression tests that walk chat history.
 *
 * These encode three measured failure modes of driving MessageWindow's scroll-up
 * paging (all diagnosed while building the network arm — do not re-derive them):
 *
 *  1. `_loadOlder` is NOT scroll-event-driven. It fires from a one-shot
 *     IntersectionObserver on a top sentinel (chatHistory.js, rootMargin 300px);
 *     dispatching 'scroll' events does nothing on its own (measured: 2 pages
 *     fetched in 6000 hammer iterations).
 *  2. Pinning scrollTop at 0 deadlocked (FIXED): the sentinel
 *     callback read entries[0] — the OLDEST queued entry — so a leave+enter
 *     pair delivered in one batch (busy main thread) was read as "left" and
 *     the enter discarded; no transition ever followed and paging dead-ended
 *     with buffered messages unrendered. pinnedTopWalk reproduced it and is
 *     the regression driver for that bug (fast cadence provokes the batched delivery).
 *  3. A down-up jiggle inside one frame is invisible. IO evaluates intersections
 *     once per frame after layout; a transition that never survives to a frame
 *     boundary never happened. Each phase must HOLD for a settled frame.
 *
 * Messages are identified by a marker regex over textContent (default
 * /SEQMSG (\d+)/, the seed convention in tests/bench/live_app.py), because
 * excursions must be defined in MESSAGES, not pixels — see the main bench's
 * probe-failure discipline in docs/dev/chat-history-benchmark.md.
 */
(function () {
  'use strict';

  var raf = function () { return new Promise(function (r) { requestAnimationFrame(r); }); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  function makeMinIdx(box, markerRe) {
    return function () {
      var best = Infinity;
      var els = box.querySelectorAll('.msg,.agent-thread');
      for (var i = 0; i < els.length; i++) {
        var m = markerRe.exec(els[i].textContent || '');
        if (m) best = Math.min(best, +m[1]);
      }
      return best;
    };
  }

  /* Walk to the oldest message the way a real user does: leave the top, return,
   * hold each phase across a frame boundary, and wait for progress before the
   * next round. Returns {ms, complete, iters}. */
  async function walkToOldest(box, opts) {
    opts = opts || {};
    var markerRe = opts.markerRe || /SEQMSG (\d+)/;
    var holdDownMs = opts.holdDownMs != null ? opts.holdDownMs : 120;
    var progressPolls = opts.progressPolls != null ? opts.progressPolls : 20; // x50ms
    var maxStalls = opts.maxStalls != null ? opts.maxStalls : 8;
    var maxRounds = opts.maxRounds != null ? opts.maxRounds : 2000;
    var minIdx = makeMinIdx(box, markerRe);

    box.scrollTop = box.scrollHeight;
    await raf(); await raf();
    var t0 = performance.now();
    var prev = minIdx(), stalls = 0, rounds = 0;
    while (prev > 0 && stalls < maxStalls && rounds++ < maxRounds) {
      box.scrollTop = box.clientHeight * 2;   // sentinel leaves the rootMargin...
      await raf();
      await sleep(holdDownMs);                // ...and the leave survives a frame
      box.scrollTop = 0;                      // sentinel re-enters: a transition
      await raf();
      box.dispatchEvent(new Event('scroll'));
      var cur = prev;
      for (var w = 0; w < progressPolls; w++) {
        await sleep(50);
        cur = minIdx();
        if (cur < prev) break;
      }
      stalls = cur < prev ? 0 : stalls + 1;
      prev = cur;
    }
    return { ms: +(performance.now() - t0).toFixed(0), complete: prev === 0, iters: rounds };
  }

  /* The deadlock shape: pin scrollTop at 0 (scrollbar dragged to the top) and
   * never leave. A fixed MessageWindow must still reach the oldest message;
   * pre-fix code dead-ended here (stale entries[0] read).
   * Regression tests assert complete === true with THIS driver at a
   * fast cadence (~30ms), which provokes the batched leave+enter delivery. */
  async function pinnedTopWalk(box, opts) {
    opts = opts || {};
    var markerRe = opts.markerRe || /SEQMSG (\d+)/;
    var cadenceMs = opts.cadenceMs != null ? opts.cadenceMs : 100;
    var maxStalls = opts.maxStalls != null ? opts.maxStalls : 50;
    var minIdx = makeMinIdx(box, markerRe);

    box.scrollTop = box.scrollHeight;
    await raf(); await raf();
    var t0 = performance.now();
    var prev = minIdx(), stalls = 0, rounds = 0;
    while (prev > 0 && stalls < maxStalls && rounds++ < 5000) {
      box.scrollTop = 0;
      box.dispatchEvent(new Event('scroll'));
      await sleep(cadenceMs);
      var cur = minIdx();
      stalls = cur < prev ? 0 : stalls + 1;
      prev = cur;
    }
    return { ms: +(performance.now() - t0).toFixed(0), complete: prev === 0, iters: rounds };
  }

  window.scrollDriver = { walkToOldest: walkToOldest, pinnedTopWalk: pinnedTopWalk };
})();
