// DOM virtualization for #chat-history.
// Phase 1: load-time windowing — renders last WINDOW_SIZE messages on session load,
//          loads older batches on demand via IntersectionObserver as user scrolls up.
// Phase 2: live pruning — caps DOM children during active sessions; replaces pruned
//          nodes with a height-matched spacer to preserve scroll position.
// Phase 3: bidirectional pruning — when the user scrolls far back through history
//          the bottom of the historical section is pruned (BIDI_CAP), closing the
//          remaining OOM vector for very long sessions scrolled top-to-bottom.
//          Pruned content is restored when the user scrolls back down to the sentinel.
//
// Usage (sessions.js):
//   window.chatHistory.reset();    // before clearing innerHTML
//   window.chatHistory.load(msgs); // instead of the addMessage for-loop
//   msgs = [{role, content, modelName, meta}, ...]  content = already-rendered HTML
//
// This script runs as a plain (non-module) script so window.chatHistory is
// available before ES modules execute.

(function () {
  'use strict';

  var WINDOW_SIZE  = 50;    // messages rendered on session load
  var BATCH_SIZE   = 25;    // messages loaded per upward/downward scroll step
  var PRUNE_AT     = 80;    // live DOM child count that triggers Phase 2 pruning
  var PRUNE_COUNT  = 20;    // nodes removed per Phase 2 prune event
  var BIDI_CAP     = 120;   // historical DOM child count that triggers bottom prune
  // Pixels ahead of the bottom sentinel at which downward scroll pre-loads the batch.
  var BIDI_MARGIN  = 200;

  function MessageWindow(container) {
    this._c          = container;  // #chat-history element
    this._all        = [];         // full history: [{role, content, modelName, meta}]
    this._startIdx   = 0;          // _all index of first message currently in DOM
    this._endIdx     = 0;          // _all index one past the last historical msg in DOM
    this._sentinel   = null;       // "↑ N earlier messages" top sentinel div
    this._sObs       = null;       // IntersectionObserver watching top sentinel
    this._bSentinel  = null;       // "↓ N more messages" bottom sentinel div
    this._histSep    = null;       // invisible div at boundary: historical | live
    this._mutObs     = null;
    this._loading    = false;      // true during load / _loadOlder (defer Phase 2)
    this._prunePending = false;    // rAF guard for Phase 2 prune (collapses burst fires)
    this._bidiPending = false;     // rAF guard for scroll-based _loadNewer
    this._initMutObs();
    this._initScrollListener();
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  MessageWindow.prototype.load = function (messages) {
    // Hold the lock through the entire load sequence. MutationObserver fires as
    // a microtask after this synchronous call returns, so setting _loading=false
    // synchronously in _renderTail would let Phase 2 prune a freshly-rendered
    // agent session (50 msgs × 5 DOM children = 250 nodes > PRUNE_AT=80).
    // rAF fires after the microtask queue drains, keeping the guard intact.
    this._loading  = true;
    this._all      = messages;
    this._startIdx = Math.max(0, messages.length - WINDOW_SIZE);
    this._endIdx   = messages.length;
    this._renderTail();
    // Scroll to bottom before attaching the sentinel so the sentinel (at the top)
    // is out of view — prevents IntersectionObserver from firing immediately.
    this._c.scrollTop = this._c.scrollHeight;
    this._attachSentinel();
    var self = this;
    requestAnimationFrame(function () { self._loading = false; });
  };

  MessageWindow.prototype.reset = function () {
    this._detachSentinel();
    this._detachBottomSentinel();
    if (this._histSep && this._histSep.parentNode) this._histSep.remove();
    this._histSep  = null;
    this._all      = [];
    this._startIdx = 0;
    this._endIdx   = 0;
  };

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  // Renders _all[_startIdx.._endIdx-1] into the container and appends the
  // invisible history/live separator. Each top-level DOM child is tagged with
  // data-ch-idx so _pruneBottom can accurately track _endIdx regardless of how
  // many children a single addMessage() call produces.
  MessageWindow.prototype._renderTail = function () {
    for (var i = this._startIdx; i < this._endIdx; i++) {
      var snap = this._c.children.length;
      var m    = this._all[i];
      window.chatModule.addMessage(m.role, m.content, m.modelName, m.meta);
      for (var k = snap; k < this._c.children.length; k++) {
        this._c.children[k].dataset.chIdx = String(i);
      }
    }
    var sep = document.createElement('div');
    sep.className  = 'chat-history-sep';
    sep.style.cssText = 'display:none;flex-shrink:0';
    this._histSep  = sep;
    this._c.appendChild(sep);
  };

  // ---------------------------------------------------------------------------
  // Top sentinel (Phase 1 — load older on scroll-up)
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._attachSentinel = function () {
    this._detachSentinel();
    if (this._startIdx === 0) return;

    var s = document.createElement('div');
    s.className   = 'chat-history-sentinel';
    s.textContent = '↑ ' + this._startIdx + ' earlier messages';
    s.style.cssText = (
      'text-align:center;padding:10px 0;color:var(--fg);opacity:0.5;' +
      'font-size:0.85rem;user-select:none;flex-shrink:0'
    );
    this._sentinel = s;
    this._c.prepend(s);

    var self = this;
    this._sObs = new IntersectionObserver(function (entries) {
      if (!entries[0].isIntersecting) return;
      self._sObs.disconnect();
      self._loadOlder();
    }, { root: this._c, rootMargin: '300px 0px 0px 0px', threshold: 0 });
    this._sObs.observe(s);
  };

  MessageWindow.prototype._detachSentinel = function () {
    if (this._sObs) { this._sObs.disconnect(); this._sObs = null; }
    if (this._sentinel && this._sentinel.parentNode) this._sentinel.remove();
    this._sentinel = null;
  };

  // ---------------------------------------------------------------------------
  // Bottom sentinel (Phase 3 — reload pruned content on scroll-down)
  //
  // NOTE: IO is NOT used here. IO fires on any visibility change including ones
  // caused by _pruneBottom() itself (content removed below makes sentinel visible
  // immediately), which defeats the pruning — restored immediately after prune.
  // Instead a scroll event listener (see _initScrollListener) watches whether the
  // sentinel is near the visible area and triggers _loadNewer() on user intent.
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._attachBottomSentinel = function () {
    this._detachBottomSentinel();
    if (this._endIdx >= this._all.length) return;

    var remaining = this._all.length - this._endIdx;
    var s = document.createElement('div');
    s.className   = 'chat-history-bottom-sentinel';
    s.textContent = '↓ ' + remaining + ' earlier messages — scroll down to load';
    s.style.cssText = (
      'text-align:center;padding:10px 0;color:var(--fg);opacity:0.5;' +
      'font-size:0.85rem;user-select:none;flex-shrink:0;cursor:pointer'
    );
    // Click also triggers load for users who prefer explicit control
    var self = this;
    s.addEventListener('click', function () { self._loadNewer(); });
    this._bSentinel = s;
    if (this._histSep && this._histSep.parentNode) {
      this._c.insertBefore(s, this._histSep);
    } else {
      this._c.appendChild(s);
    }
  };

  MessageWindow.prototype._detachBottomSentinel = function () {
    if (this._bSentinel && this._bSentinel.parentNode) this._bSentinel.remove();
    this._bSentinel = null;
  };

  // ---------------------------------------------------------------------------
  // Scroll listener — drives Phase 3 downward load
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._initScrollListener = function () {
    var self = this;
    this._c.addEventListener('scroll', function () {
      // Nothing to do if no pruned content or already loading
      if (!self._bSentinel || self._loading || self._bidiPending) return;
      if (self._endIdx >= self._all.length) return;

      // Load when the bottom sentinel is within BIDI_MARGIN px of the visible bottom
      var rect      = self._bSentinel.getBoundingClientRect();
      var container = self._c.getBoundingClientRect();
      if (rect.top <= container.bottom + BIDI_MARGIN) {
        self._bidiPending = true;
        requestAnimationFrame(function () {
          self._bidiPending = false;
          if (!self._loading && self._endIdx < self._all.length) {
            self._loadNewer();
          }
        });
      }
    }, { passive: true });
  };

  // ---------------------------------------------------------------------------
  // _loadOlder — prepend a batch of historical messages (scroll up)
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._loadOlder = function () {
    var from = Math.max(0, this._startIdx - BATCH_SIZE);
    var upTo = this._startIdx;
    if (from >= upTo) { this._attachSentinel(); return; }

    // Remove stale spacers before measuring — they should be replaced by real content
    var _spcs = this._c.querySelectorAll('.chat-history-spacer');
    for (var _si = 0; _si < _spcs.length; _si++) _spcs[_si].remove();

    var before    = this._c.scrollHeight;
    var insertRef = this._sentinel ? this._sentinel.nextSibling : this._c.firstChild;

    this._loading = true;
    var nodes = [];
    for (var i = from; i < upTo; i++) {
      var m    = this._all[i];
      var snap = this._c.children.length;
      window.chatModule.addMessage(m.role, m.content, m.modelName, m.meta);
      for (var k = snap; k < this._c.children.length; k++) {
        this._c.children[k].dataset.chIdx = String(i);
        nodes.push(this._c.children[k]);
      }
    }

    var frag = document.createDocumentFragment();
    for (var j = 0; j < nodes.length; j++) frag.appendChild(nodes[j]);
    if (insertRef) {
      this._c.insertBefore(frag, insertRef);
    } else {
      this._c.appendChild(frag);
    }

    if (window.hljs) {
      this._c.querySelectorAll('pre code:not(.hljs)').forEach(function (b) {
        window.hljs.highlightElement(b);
      });
    }

    this._startIdx = from;
    this._c.scrollTop += this._c.scrollHeight - before;

    // Phase 3: cap historical DOM size; pruned content reloads on scroll-down.
    var hist = this._histChildCount();
    if (hist > BIDI_CAP) {
      this._pruneBottom(hist - BIDI_CAP);
    }

    this._attachSentinel();
    var self = this;
    requestAnimationFrame(function () { self._loading = false; });
  };

  // ---------------------------------------------------------------------------
  // _loadNewer — append a batch of historical messages (scroll down)
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._isAtVeryBottom = function () {
    return this._c.scrollTop + this._c.clientHeight >= this._c.scrollHeight - 10;
  };

  MessageWindow.prototype._loadNewer = function () {
    if (this._endIdx >= this._all.length) return;

    // Captured before any DOM changes. When the user is at the very bottom
    // (button press or equivalent), top-prune should snap rather than shift,
    // keeping the user at the bottom so the rAF chain can continue.
    var atBottom = this._isAtVeryBottom();

    var from = this._endIdx;
    var upTo = Math.min(this._all.length, from + BATCH_SIZE);

    this._loading = true;
    var nodes = [];
    for (var i = from; i < upTo; i++) {
      var m    = this._all[i];
      var snap = this._c.children.length;
      window.chatModule.addMessage(m.role, m.content, m.modelName, m.meta);
      for (var k = snap; k < this._c.children.length; k++) {
        this._c.children[k].dataset.chIdx = String(i);
        nodes.push(this._c.children[k]);
      }
    }

    var frag = document.createDocumentFragment();
    for (var j = 0; j < nodes.length; j++) frag.appendChild(nodes[j]);
    if (this._histSep && this._histSep.parentNode) {
      this._c.insertBefore(frag, this._histSep);
    } else {
      this._c.appendChild(frag);
    }

    if (window.hljs) {
      this._c.querySelectorAll('pre code:not(.hljs)').forEach(function (b) {
        window.hljs.highlightElement(b);
      });
    }

    this._endIdx = upTo;

    // Symmetric with _loadOlder: cap historical DOM from the top when scrolling down.
    // Without this, a full up-then-down cycle loads the entire session into the DOM.
    var hist = this._histChildCount();
    if (hist > BIDI_CAP) {
      var toPrune  = hist - BIDI_CAP;
      var before   = this._c.scrollHeight;
      var removed  = 0;
      var highIdx  = this._startIdx - 1;
      var cur      = this._c.firstElementChild;
      while (cur && removed < toPrune) {
        var next = cur.nextElementSibling;
        var isCtl = (cur === this._sentinel  || cur === this._bSentinel ||
                     cur === this._histSep   ||
                     cur.classList.contains('chat-history-spacer'));
        if (!isCtl) {
          var cidx = (cur.dataset && cur.dataset.chIdx !== undefined)
            ? parseInt(cur.dataset.chIdx, 10) : null;
          cur.remove();
          removed++;
          if (cidx !== null && cidx > highIdx) highIdx = cidx;
        }
        cur = next;
      }
      // Don't leave a partial message at the boundary — remove any remaining
      // siblings that share the same _all index as the last removed node.
      if (removed > 0) {
        var peek = this._c.firstElementChild;
        while (peek) {
          var isPeekCtl = (peek === this._sentinel  || peek === this._bSentinel ||
                           peek === this._histSep   ||
                           peek.classList.contains('chat-history-spacer'));
          if (isPeekCtl) { peek = peek.nextElementSibling; continue; }
          if (peek.dataset && parseInt(peek.dataset.chIdx, 10) === highIdx) {
            var peekNext = peek.nextElementSibling;
            peek.remove();
            removed++;
            peek = peekNext;
          } else {
            break;
          }
        }
        this._startIdx = highIdx + 1;
        if (atBottom) {
          // User wants to be at the bottom (button press): snap to new bottom so
          // the rAF chain condition (_isAtBottom) stays true and continues loading.
          this._c.scrollTop = this._c.scrollHeight - this._c.clientHeight;
        } else {
          // User is scrolling slowly through history: compensate for removed height
          // above the viewport so their visual position does not jump.
          this._c.scrollTop -= (before - this._c.scrollHeight);
        }
        this._attachSentinel();
      }
    }

    this._attachBottomSentinel();
    var self = this;
    requestAnimationFrame(function () {
      self._loading = false;
      // Chain: if the user is still at the bottom after this batch (snap kept
      // them there), keep loading without waiting for another scroll event.
      // This drains all remaining batches on a single button press.
      // For slow manual scrolling atBottom is false, so this never fires —
      // the scroll listener handles that case instead.
      if (self._endIdx < self._all.length && self._isAtBottom()) {
        self._loadNewer();
      }
    });
  };

  // ---------------------------------------------------------------------------
  // Phase 2 — live pruning (MutationObserver at-bottom only)
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._initMutObs = function () {
    var self = this;
    this._mutObs = new MutationObserver(function () {
      if (self._loading || self._prunePending) return;
      // Collapse burst DOM mutations (streaming token appends) into one prune check
      // per animation frame instead of an O(n) DOM walk on every individual fire.
      self._prunePending = true;
      requestAnimationFrame(function () {
        self._prunePending = false;
        if (!self._loading) self._maybePrune();
      });
    });
    this._mutObs.observe(this._c, { childList: true });
  };

  MessageWindow.prototype._isAtBottom = function () {
    return this._c.scrollTop + this._c.clientHeight >= this._c.scrollHeight - 120;
  };

  MessageWindow.prototype._maybePrune = function () {
    if (!this._isAtBottom()) return;
    if (!this._histSep || !this._histSep.parentNode) return;
    // Threshold is based on total non-control DOM nodes (historical + live) so that
    // a long live session (many turns after the history boundary) also triggers
    // pruning — not just sessions where the user scrolled up through history.
    // Pruning itself is still limited to historical nodes (before _histSep) because
    // live nodes have no _all[] entry and cannot be reloaded once removed.
    var total = this._liveChildCount();
    if (total <= PRUNE_AT) return;
    var hist  = this._histChildCount();
    if (hist === 0) return;
    this._pruneTop(Math.min(hist, total - PRUNE_AT + PRUNE_COUNT));
  };

  // Count all non-control DOM children (excludes sentinels, spacer, sep).
  MessageWindow.prototype._liveChildCount = function () {
    var n        = 0;
    var children = this._c.children;
    for (var i = 0; i < children.length; i++) {
      var ch = children[i];
      if (ch === this._sentinel  ||
          ch === this._bSentinel ||
          ch === this._histSep   ||
          ch.classList.contains('chat-history-spacer')) continue;
      n++;
    }
    return n;
  };

  // Count historical DOM children (before _histSep), excluding control elements.
  // Used by _loadOlder to decide when to call _pruneBottom.
  MessageWindow.prototype._histChildCount = function () {
    var n        = 0;
    var children = this._c.children;
    for (var i = 0; i < children.length; i++) {
      var ch = children[i];
      if (ch === this._histSep) break;
      if (ch === this._sentinel  ||
          ch === this._bSentinel ||
          ch.classList.contains('chat-history-spacer')) continue;
      n++;
    }
    return n;
  };

  // ---------------------------------------------------------------------------
  // Prune helpers
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._pruneTop = function (count) {
    var before   = this._c.scrollHeight;
    var removed  = 0;
    var highIdx  = -1;
    var children = Array.from(this._c.children);
    for (var i = 0; i < children.length && removed < count; i++) {
      var ch = children[i];
      // Hard boundary: never cross into live messages after _histSep.
      // A single addMessage() call can produce multiple top-level DOM children,
      // so _startIdx must be derived from data-ch-idx, not the raw node count.
      if (ch === this._histSep) break;
      if (ch === this._sentinel  ||
          ch === this._bSentinel ||
          ch.classList.contains('chat-history-spacer')) continue;
      var cidx = (ch.dataset && ch.dataset.chIdx !== undefined)
        ? parseInt(ch.dataset.chIdx, 10) : -1;
      ch.remove();
      removed++;
      if (cidx > highIdx) highIdx = cidx;
    }
    if (removed === 0) return;

    // A single _all[i] entry may span multiple DOM children with the same chIdx.
    // Remove any remaining siblings at the boundary that share highIdx so the
    // first node left in DOM always begins a complete message.
    if (highIdx >= 0) {
      var peek = this._c.firstElementChild;
      while (peek && peek !== this._histSep) {
        var isPeekCtl = (peek === this._sentinel || peek === this._bSentinel ||
                         peek.classList.contains('chat-history-spacer'));
        if (isPeekCtl) { peek = peek.nextElementSibling; continue; }
        if (peek.dataset && parseInt(peek.dataset.chIdx, 10) === highIdx) {
          var peekNext = peek.nextElementSibling;
          peek.remove();
          removed++;
          peek = peekNext;
        } else {
          break;
        }
      }
      this._startIdx = highIdx + 1;
    }

    var delta = before - this._c.scrollHeight;
    this._attachSentinel();

    // Collapse any leftover spacers from previous prune events into one
    var existingSpacers = this._c.querySelectorAll('.chat-history-spacer');
    var accHeight = 0;
    for (var ei = 0; ei < existingSpacers.length; ei++) {
      accHeight += parseInt(existingSpacers[ei].style.height, 10) || 0;
      existingSpacers[ei].remove();
    }

    var totalDelta = delta + accHeight;
    if (totalDelta > 0) {
      var spacer = document.createElement('div');
      spacer.className  = 'chat-history-spacer';
      spacer.style.cssText = (
        'height:' + totalDelta + 'px;flex-shrink:0;min-height:32px;display:flex;' +
        'align-items:center;justify-content:center;' +
        'color:var(--fg);opacity:0.35;font-size:0.8rem'
      );
      spacer.textContent = 'Earlier messages pruned — scroll up to reload';
      var afterSentinel = this._sentinel ? this._sentinel.nextSibling : null;
      if (afterSentinel) {
        this._c.insertBefore(spacer, afterSentinel);
      } else {
        this._c.prepend(spacer);
      }
    }
  };

  // Remove `count` historical DOM nodes from just above _histSep.
  // Uses data-ch-idx to accurately track _endIdx even when a single _all entry
  // produces multiple top-level DOM children (e.g. agent multi-round messages).
  MessageWindow.prototype._pruneBottom = function (count) {
    var removed    = 0;
    var lowestIdx  = this._endIdx;  // track the lowest _all index removed
    var ref = this._histSep
      ? this._histSep.previousSibling
      : this._c.lastElementChild;

    while (ref && removed < count) {
      var prev = ref.previousSibling;
      var isControl = (
        ref === this._sentinel  ||
        ref === this._bSentinel ||
        ref === this._histSep   ||
        ref.classList.contains('chat-history-spacer')
      );
      if (!isControl) {
        var idx = (ref.dataset && ref.dataset.chIdx !== undefined)
          ? parseInt(ref.dataset.chIdx, 10)
          : null;
        ref.remove();
        removed++;
        if (idx !== null && idx < lowestIdx) lowestIdx = idx;
      }
      ref = prev;
    }

    if (removed > 0) {
      this._endIdx = lowestIdx;
      this._attachBottomSentinel();
    }
  };

  // ---------------------------------------------------------------------------
  // Singleton
  // ---------------------------------------------------------------------------

  var container = document.getElementById('chat-history');
  if (container) {
    window.chatHistory = new MessageWindow(container);
  }
})();
