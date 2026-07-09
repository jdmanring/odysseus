// HYBRID ARM — proof-of-concept, benchmark-only. NOT shipping code.
//
// Purpose: show that the two published techniques COMPOSE, i.e. that bounded
// memory and cheap recent scroll-back are not a trade-off you must pick between.
// It is built from exactly two primitives, both already in the benchmark:
//
//   warm band  = upstream PR #4998's detach-preserve (children into a JS array,
//                wrapper height pinned) — restored by re-append, no re-parse.
//   cold tail  = the fork's MessageWindow eviction (remove the wrapper entirely,
//                account its height into a spacer) — restored by re-render from
//                the source, which in the real app is a server page fetch.
//
// Credibility note: naive/detach/evict are real or verbatim-vendored code. This
// arm is authored by the party with a stake in the result, which is the mirror
// image of the strawman risk the methodology guards against. Mitigations:
//   * constants are lifted unchanged from chatHistory.js (WINDOW_SIZE/BATCH_SIZE/
//     BIDI_MSG_CAP) and chatVirtualizer_4998.js (LIVE_MARGIN). Nothing is tuned
//     against this corpus.
//   * no new mechanism is invented; the only delta vs a naive stacking of the two
//     is the reflow fix documented at `collapse()` below.
//   * tests/test_chat_history_hybrid_bench_js.py asserts the three behaviours it
//     claims (warm detach, cold evict, restore from both bands) in real Chromium.
//
// The claim is "this combination is achievable and measures as follows", not
// "ship these lines".

(function () {
  'use strict';

  // --- constants, lifted (not tuned) ---------------------------------------
  var WINDOW_SIZE  = 50;        // chatHistory.js: messages rendered on load
  var BATCH_SIZE   = 25;        // chatHistory.js: messages paged per scroll step
  var MSG_CAP      = 80;        // chatHistory.js BIDI_MSG_CAP: max rendered messages
  var LIVE_MARGIN  = '2000px';  // chatVirtualizer_4998.js: fully-live band around viewport
  var PAGE_MARGIN  = 1200;      // px from an edge at which the cold tail pages in

  function spacer() {
    var s = document.createElement('div');
    s.className = 'hb-spacer';
    s.setAttribute('aria-hidden', 'true');
    s.style.flexShrink = '0';
    s.style.height = '0px';
    return s;
  }

  function sentinel(which) {
    var s = document.createElement('div');
    s.className = 'hb-sentinel hb-sentinel-' + which;
    s.setAttribute('aria-hidden', 'true');
    s.style.flexShrink = '0';
    s.style.height = '1px';
    return s;
  }

  function Hybrid(container) {
    this._c        = container;
    this._src      = [];     // the "server": message data. Cold tail holds no copy.
    this._lo       = 0;      // rendered range [lo, hi)
    this._hi       = 0;
    this._nodes    = [];     // rendered wrappers, parallel to [lo, hi)
    this._heights  = [];     // measured height per source index (Float, 8B) — the
                             // only per-message state the cold tail retains.
    this._avgH     = 0;
    this._top      = spacer();
    this._bot      = spacer();
    this._topSent  = sentinel('top');
    this._botSent  = sentinel('bottom');
    this._io       = null;   // warm band (detach/restore)
    this._ioPage   = null;   // cold tail (page in from source)
    this._queue    = [];     // batched IO entries, drained in one rAF pass
    this._draining = false;
    this._paging   = false;
  }

  // --- warm band: #4998's detach-preserve -----------------------------------
  //
  // THE ONE DELTA vs #4998: height comes from `entry.boundingClientRect.height`,
  // which the IntersectionObserver already computed, instead of `node.offsetHeight`.
  // Reading offsetHeight inside the observer callback forces a synchronous layout
  // per collapsing node; during a scroll that is a reflow storm (measured: 65ms
  // mean frame, 60 long frames at n=5000). The rect is free. Same technique, no
  // forced layout. The collapse itself is also deferred to a batched rAF pass so
  // it never runs inside the scroll's critical path.
  function collapse(node, h) {
    if (node.__vCollapsed || h < 40) return;
    var kids = [];
    while (node.firstChild) kids.push(node.removeChild(node.firstChild));
    node.__vChildren = kids;
    node.__vCollapsed = true;
    node.style.boxSizing = 'border-box';
    node.style.minHeight = h + 'px';
  }

  function restore(node) {
    if (!node.__vCollapsed) return;
    var kids = node.__vChildren || [];
    for (var i = 0; i < kids.length; i++) node.appendChild(kids[i]);
    node.__vChildren = null;
    node.__vCollapsed = false;
    node.style.minHeight = '';
    node.style.boxSizing = '';
  }

  // A node a stream may still be writing into. Never collapsed, never evicted.
  function isStreaming(node) {
    return node.classList.contains('agent-thinking-dots') ||
           node.querySelector('.stream-content') !== null;
  }

  // #4998's isLive also spares `lastElementChild`; here spacers/sentinels occupy
  // that slot, so the newest message is identified positionally. This spares it
  // from *collapse* only. Eviction from the bottom must stay allowed: scrolling up
  // prunes the bottom of the window (as MessageWindow._loadOlder does), and a rule
  // that protects the bottom-most node unconditionally deadlocks that prune — the
  // window then grows without bound all the way to the top.
  Hybrid.prototype._isCollapsible = function (node) {
    if (isStreaming(node)) return false;
    var newest = this._hi === this._src.length && node === this._nodes[this._nodes.length - 1];
    return !newest;
  };

  Hybrid.prototype._drain = function () {
    this._draining = false;
    var q = this._queue;
    this._queue = [];
    for (var i = 0; i < q.length; i++) {
      var e = q[i];
      if (!e.target.isConnected) continue;
      if (e.isIntersecting) restore(e.target);
      else if (this._isCollapsible(e.target)) collapse(e.target, e.rect);
    }
  };

  Hybrid.prototype._onIntersect = function (entries) {
    for (var i = 0; i < entries.length; i++) {
      this._queue.push({ target: entries[i].target,
                         isIntersecting: entries[i].isIntersecting,
                         rect: entries[i].boundingClientRect.height });
    }
    if (!this._draining) {
      this._draining = true;
      var self = this;
      requestAnimationFrame(function () { self._drain(); });
    }
  };

  // --- rendering ------------------------------------------------------------
  Hybrid.prototype._make = function (msg) {
    var d = document.createElement('div');
    d.className = 'msg msg-' + msg.role;
    d.innerHTML = msg.content;   // the re-parse cost the cold tail pays on restore
    d.__hbOwned = true;          // ours: the MutationObserver must not re-adopt it
    var m = /Message (\d+)\./.exec(msg.content);   // match the harness stub's tagging
    if (m) d.dataset.i = m[1];
    return d;
  };

  Hybrid.prototype._heightOf = function (node) {
    // A collapsed wrapper's height is already pinned — read it without a layout.
    if (node.__vCollapsed) return parseFloat(node.style.minHeight) || 0;
    return node.offsetHeight;
  };

  Hybrid.prototype._noteHeights = function () {
    var sum = 0, seen = 0;
    for (var i = 0; i < this._nodes.length; i++) {
      var h = this._heightOf(this._nodes[i]);
      if (h > 0) { this._heights[this._lo + i] = h; sum += h; seen++; }
    }
    if (seen) this._avgH = sum / seen;
  };

  Hybrid.prototype._spacerHeights = function () {
    var above = 0, i;
    for (i = 0; i < this._lo; i++) above += this._heights[i] || this._avgH;
    var below = 0;
    for (i = this._hi; i < this._src.length; i++) below += this._heights[i] || this._avgH;
    this._top.style.height = Math.round(above) + 'px';
    this._bot.style.height = Math.round(below) + 'px';
  };

  // --- cold tail: evict wrappers entirely -----------------------------------
  Hybrid.prototype._evictFrom = function (side, count) {
    for (var k = 0; k < count; k++) {
      var idx = side === 'top' ? 0 : this._nodes.length - 1;
      var node = this._nodes[idx];
      if (!node || isStreaming(node)) break;
      this._heights[side === 'top' ? this._lo : this._hi - 1] = this._heightOf(node);
      this._io.unobserve(node);
      node.__vChildren = null;          // drop detached children with the wrapper
      node.remove();
      this._nodes.splice(idx, 1);
      if (side === 'top') this._lo++; else this._hi--;
    }
  };

  Hybrid.prototype._pageOlder = function () {
    if (this._paging || this._lo === 0) return;
    this._paging = true;
    var box = this._c, before = box.scrollHeight;
    var count = Math.min(BATCH_SIZE, this._lo);
    var ref = this._nodes[0] || this._bot;
    for (var i = 0; i < count; i++) {
      var idx = this._lo - count + i;
      var node = this._make(this._src[idx]);
      box.insertBefore(node, ref);
      this._nodes.splice(i, 0, node);
      this._io.observe(node);
    }
    this._lo -= count;
    var over = (this._hi - this._lo) - MSG_CAP;
    if (over > 0) this._evictFrom('bottom', over);
    this._noteHeights();
    this._spacerHeights();
    box.scrollTop += box.scrollHeight - before;   // anchor: keep the viewport put
    this._paging = false;
  };

  Hybrid.prototype._pageNewer = function () {
    if (this._paging || this._hi >= this._src.length) return;
    this._paging = true;
    var box = this._c;
    var count = Math.min(BATCH_SIZE, this._src.length - this._hi);
    for (var i = 0; i < count; i++) {
      var node = this._make(this._src[this._hi + i]);
      box.insertBefore(node, this._bot);
      this._nodes.push(node);
      this._io.observe(node);
    }
    this._hi += count;
    var over = (this._hi - this._lo) - MSG_CAP;
    if (over > 0) this._evictFrom('top', over);
    this._noteHeights();
    this._spacerHeights();
    this._paging = false;
  };

  // Paging is sentinel-driven, not scroll-event-driven — the same primitive
  // chatHistory.js uses, and for the same reason: once scrollTop pins at 0 the
  // element stops emitting scroll events, so a scroll handler deadlocks at the
  // top with history still unpaged. An IntersectionObserver keeps firing.
  // After each page we re-observe the sentinel: it may remain intersecting after
  // the DOM changes, and IO only notifies on a *change* of intersection state.
  Hybrid.prototype._onPageSentinel = function (entries) {
    var self = this, hitTop = false, hitBottom = false;
    for (var i = 0; i < entries.length; i++) {
      if (!entries[i].isIntersecting) continue;
      if (entries[i].target === this._topSent) hitTop = true;
      else hitBottom = true;
    }
    if (!hitTop && !hitBottom) return;
    requestAnimationFrame(function () {
      if (hitTop) self._pageOlder();
      if (hitBottom) self._pageNewer();
      if (hitTop && self._lo > 0) { self._ioPage.unobserve(self._topSent); self._ioPage.observe(self._topSent); }
      if (hitBottom && self._hi < self._src.length) {
        self._ioPage.unobserve(self._botSent); self._ioPage.observe(self._botSent);
      }
    });
  };

  // --- public ---------------------------------------------------------------
  Hybrid.prototype.load = function (messages) {
    var box = this._c, self = this;
    box.innerHTML = '';
    this._src = messages.slice();
    this._heights = new Array(this._src.length);
    this._lo = Math.max(0, this._src.length - WINDOW_SIZE);
    this._hi = this._src.length;
    this._nodes = [];

    this._io = new IntersectionObserver(function (e) { self._onIntersect(e); },
                                        { root: box, rootMargin: LIVE_MARGIN + ' 0px' });

    // Order matters: the sentinel sits ABOVE the spacer (as in chatHistory.js), so
    // scrolling to the top reaches the sentinel. With the spacer first, scrollTop=0
    // lands you on 30000px of spacer and the sentinel is never near the viewport.
    box.appendChild(this._topSent);
    box.appendChild(this._top);
    for (var i = this._lo; i < this._hi; i++) {
      var node = this._make(this._src[i]);
      box.appendChild(node);
      this._nodes.push(node);
    }
    box.appendChild(this._bot);
    box.appendChild(this._botSent);

    this._noteHeights();
    this._spacerHeights();
    for (var j = 0; j < this._nodes.length; j++) this._io.observe(this._nodes[j]);

    this._ioPage = new IntersectionObserver(function (e) { self._onPageSentinel(e); },
                                            { root: box, rootMargin: PAGE_MARGIN + 'px 0px' });
    this._ioPage.observe(this._topSent);
    this._ioPage.observe(this._botSent);

    // Appends from chatModule.addMessage land after _bot; adopt them so the
    // rendered range and the source stay consistent with what is on screen.
    new MutationObserver(function (muts) {
      for (var m = 0; m < muts.length; m++) {
        muts[m].addedNodes.forEach(function (n) {
          if (n.nodeType !== 1 || !n.classList.contains('msg') || n.__hbOwned) return;
          n.__hbOwned = true;
          self._src.push({ role: 'assistant', content: n.innerHTML });
          self._heights.push(0);
          self._hi = self._src.length;
          self._nodes.push(n);
          self._io.observe(n);
          var over = (self._hi - self._lo) - MSG_CAP;
          if (over > 0) self._evictFrom('top', over);
        });
      }
    }).observe(box, { childList: true });

    box.scrollTop = box.scrollHeight;
  };

  Hybrid.prototype.stats = function () {
    var collapsed = 0;
    for (var i = 0; i < this._nodes.length; i++) if (this._nodes[i].__vCollapsed) collapsed++;
    return { lo: this._lo, hi: this._hi, rendered: this._nodes.length,
             collapsed: collapsed, total: this._src.length };
  };

  var box = document.getElementById('chat-history');
  var h = new Hybrid(box);
  window.hybridBench = { load: function (m) { h.load(m); }, stats: function () { return h.stats(); } };
})();
