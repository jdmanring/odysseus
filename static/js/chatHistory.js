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
  var SERVER_PAGE  = 100;   // messages fetched per backend history page (matches server cap)
  var PRUNE_AT     = 80;    // live DOM child count that triggers Phase 2 pruning
  var PRUNE_COUNT  = 20;    // nodes removed per Phase 2 prune event
  var BIDI_CAP     = 120;   // historical DOM child count that triggers top prune (in _loadNewer)
  // Phase 3 cap for _loadOlder is message-based, not DOM-node-based.
  // Multi-round agent messages produce many top-level DOM children each, so a
  // DOM-node cap is unreliable: the WINDOW_SIZE=50 initial load can already
  // exceed BIDI_CAP and cause a massive prune on the first _loadOlder() call.
  var BIDI_MSG_CAP = 80;    // max historical *messages* in DOM during upward scroll
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
    this._draining   = false;      // true while scrollToBottom() is draining all batches
    this._gen        = 0;          // incremented on reset(); all rAF callbacks check this
    this._evictedLiveCount = 0;   // live nodes evicted when history exhausted (for notice)
    // Server-paged history: _all holds only the pages fetched so far. When the
    // in-memory buffer is exhausted on scroll-up, older pages are pulled from
    // the backend (limit/offset) so the full history is reachable while the DOM
    // stays bounded. _serverOffset is the raw DB offset of _all[0].
    this._sessionId     = null;
    this._serverOffset  = 0;
    this._serverHasMore = false;
    this._fetching      = false;
    this._olderLoader   = null;   // async (sessionId, limit, offset) -> {msgs, offset, hasMore}
    this._initMutObs();
    this._initScrollListener();
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  MessageWindow.prototype.load = function (messages, opts) {
    // Hold the lock through the entire load sequence. MutationObserver fires as
    // a microtask after this synchronous call returns, so setting _loading=false
    // synchronously in _renderTail would let Phase 2 prune a freshly-rendered
    // agent session (50 msgs × 5 DOM children = 250 nodes > PRUNE_AT=80).
    // rAF fires after the microtask queue drains, keeping the guard intact.
    opts = opts || {};
    this._loading  = true;
    this._all      = messages;
    // Server-paging state: only enabled when the caller supplies an olderLoader
    // and the backend reports older messages exist beyond this first page.
    this._sessionId     = opts.sessionId || null;
    this._serverOffset  = (typeof opts.serverOffset === 'number' && opts.serverOffset > 0) ? opts.serverOffset : 0;
    this._olderLoader   = (typeof opts.olderLoader === 'function') ? opts.olderLoader : null;
    this._serverHasMore = !!opts.serverHasMore && this._serverOffset > 0 && this._olderLoader !== null;
    this._fetching      = false;
    this._startIdx = Math.max(0, messages.length - WINDOW_SIZE);
    this._endIdx   = messages.length;
    console.log('[chatHistory] Session load: %d msgs, rendering %d–%d', messages.length, this._startIdx, this._endIdx - 1);
    this._renderTail();
    // Attach the sentinel first so the scroll accounts for its height.
    // IO callbacks are asynchronous — they cannot fire until the current
    // JS task returns, so the sentinel is guaranteed to be out of view
    // by the time the observer first evaluates.
    this._attachSentinel();
    this._c.scrollTop = this._c.scrollHeight;
    var self = this;
    var _lgen = this._gen;
    requestAnimationFrame(function () {
      if (self._gen !== _lgen) return;
      self._c.scrollTop = self._c.scrollHeight;
      requestAnimationFrame(function () {
        if (self._gen !== _lgen) return;
        self._loading = false;
        self._c.scrollTop = self._c.scrollHeight;
        // Lazy-loaded images inflate scrollHeight after the initial snap.
        // overflow-anchor:none prevents automatic compensation, so attach one-shot
        // load listeners and re-snap. No slack threshold: a fresh session load should
        // always land at the bottom regardless of how much content loads.
        var _imgs = self._c.querySelectorAll('img');
        for (var _ii = 0; _ii < _imgs.length; _ii++) {
          if (!_imgs[_ii].complete) {
            (function (img) {
              img.addEventListener('load', function () {
                if (self._gen !== _lgen) return;
                self._c.scrollTop = self._c.scrollHeight - self._c.clientHeight;
              }, { once: true });
            })(_imgs[_ii]);
          }
        }
        // Settling loop: re-snap each frame while scrollHeight is still growing
        // (fonts, images, code blocks rendering). Runs up to 8 frames (~133ms).
        // No slack threshold: session load always wants the true bottom.
        var _slGen = self._gen;
        (function _settle(remaining, prevH) {
          requestAnimationFrame(function () {
            if (self._gen !== _slGen) return;
            var h = self._c.scrollHeight;
            if (h !== prevH) {
              self._c.scrollTop = h - self._c.clientHeight;
            }
            if (remaining > 0 && h !== prevH) {
              _settle(remaining - 1, h);
            }
          });
        })(8, self._c.scrollHeight);
      });
    });
  };

  MessageWindow.prototype.reset = function () {
    // Bump generation so all in-flight rAF callbacks from the previous session
    // detect the stale gen and bail without modifying state or calling _loadNewer.
    this._gen++;
    this._loading    = false;
    this._prunePending = false;
    this._bidiPending  = false;
    this._draining   = false;
    this._detachSentinel();
    this._detachBottomSentinel();
    if (this._histSep && this._histSep.parentNode) this._histSep.remove();
    this._histSep  = null;
    this._all      = [];
    this._startIdx = 0;
    this._endIdx   = 0;
    this._evictedLiveCount = 0;
    this._sessionId     = null;
    this._serverOffset  = 0;
    this._serverHasMore = false;
    this._fetching      = false;
    this._olderLoader   = null;
  };

  // Snap to the true bottom of history, draining all remaining _loadNewer() batches.
  // Called by the scroll-to-bottom button. Sets _draining so the rAF chain snaps to
  // the bottom before each continuity check, defeating hljs height inflation between
  // batches that would otherwise break the _isAtBottom() threshold test.
  MessageWindow.prototype.scrollToBottom = function () {
    this._draining = true;
    this._c.scrollTop = this._c.scrollHeight - this._c.clientHeight;
    if (this._endIdx < this._all.length && !this._loading) {
      this._loadNewer();
    }
    // If _loading=true, the in-progress _loadNewer() rAF chain will see _draining=true
    // and snap + continue regardless of _isAtBottom().
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
    // Keep the sentinel while there are earlier messages either buffered
    // in _all (_startIdx) or still on the server (_serverHasMore), so scrolling
    // up keeps paging the backend instead of dead-ending at the first page.
    if (this._startIdx === 0 && !this._serverHasMore) return;

    var s = document.createElement('div');
    s.className   = 'chat-history-sentinel';
    var _older = this._startIdx + (this._serverHasMore ? this._serverOffset : 0);
    s.textContent = '↑ ' + _older + ' earlier messages';
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
  // _fetchOlderFromServer — pull the next older backend page into _all
  //
  // Called by _loadOlder when the in-memory buffer is exhausted but the server
  // still has older messages. Prepends the fetched (mapped) messages to _all and
  // re-enters _loadOlder to render one batch. Returns true if a fetch started.
  // Guards: _fetching (one in flight at a time) and _gen (session switched → drop
  // the stale result). On error, paging is disabled so scroll-up stops dead-ending.
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._fetchOlderFromServer = function () {
    if (this._fetching || !this._serverHasMore || typeof this._olderLoader !== 'function') return false;
    var limit = Math.min(SERVER_PAGE, this._serverOffset);
    if (limit <= 0) { this._serverHasMore = false; return false; }
    var offset = Math.max(0, this._serverOffset - limit);
    var self = this, gen = this._gen, sid = this._sessionId;
    this._fetching = true;
    this._loading  = true;   // defer Phase 2 prune until the fetched batch renders
    Promise.resolve(this._olderLoader(sid, limit, offset)).then(function (res) {
      if (gen !== self._gen) return;          // session switched during the fetch
      var msgs = (res && res.msgs) || [];
      if (msgs.length) {
        self._all      = msgs.concat(self._all);
        self._startIdx += msgs.length;
        self._endIdx   += msgs.length;
      }
      self._serverOffset  = (res && typeof res.offset === 'number') ? res.offset : offset;
      self._serverHasMore = !!(res && res.hasMore) && self._serverOffset > 0;
      self._fetching = false;
      if (msgs.length) {
        self._loadOlder();                    // render the prepended batch from _all
      } else {
        // Page was entirely filtered out (e.g. hidden/continue messages).
        // Keep paging further back on the next scroll if more remain.
        self._loading = false;
        self._attachSentinel();
      }
    }).catch(function (e) {
      if (gen !== self._gen) return;
      console.warn('[chatHistory] server page fetch failed:', e);
      self._fetching = false;
      self._loading  = false;
      self._serverHasMore = false;            // stop retrying after an error
      self._attachSentinel();
    });
    return true;
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
    s.textContent = '↓ ' + remaining + ' newer messages, scroll down to load';
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
        var _sgen = self._gen;
        requestAnimationFrame(function () {
          if (self._gen !== _sgen) { self._bidiPending = false; return; }
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
    if (from >= upTo) {
      // In-memory buffer exhausted. Pull the next older page from the backend
      // if one exists; _fetchOlderFromServer re-enters _loadOlder once it lands.
      if (this._serverHasMore && this._fetchOlderFromServer()) return;
      this._attachSentinel();
      return;
    }

    // Measure before any DOM mutation so the spacer height is included in the
    // baseline. The scroll adjustment at the end is scrollHeight_after - before,
    // which gives the net change (content_height - spacer_height). Computing
    // before after spacer removal drops the spacer from the baseline and then
    // overcorrects scrollTop by the full content height regardless of spacer size.
    var before = this._c.scrollHeight;

    // Remove spacers before computing insertRef: after _pruneTop the sentinel is
    // immediately followed by a spacer, so insertRef = sentinel.nextSibling = spacer.
    // Removing the spacer after capturing insertRef leaves it pointing to a detached
    // node, and insertBefore(frag, detachedNode) throws NotFoundError.
    var _spcs = this._c.querySelectorAll('.chat-history-spacer');
    for (var _si = 0; _si < _spcs.length; _si++) _spcs[_si].remove();

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
    // insertRef: after the old sentinel (first real node), or _histSep as safe fallback
    if (!insertRef && this._histSep && this._histSep.parentNode) insertRef = this._histSep;
    if (insertRef) {
      this._c.insertBefore(frag, insertRef);
    } else {
      this._c.appendChild(frag);
    }

    var _deferAll = window.hljsDeferHighlightAll;
    for (var hi = 0; hi < nodes.length; hi++) {
      if (!nodes[hi].querySelectorAll) continue;
      if (_deferAll) {
        _deferAll(nodes[hi]);
      } else if (window.hljs) {
        var _bs = nodes[hi].querySelectorAll('pre code:not(.hljs)');
        for (var bi = 0; bi < _bs.length; bi++) window.hljs.highlightElement(_bs[bi]);
      }
    }

    this._startIdx = from;
    console.log('[chatHistory] Load older: msgs %d–%d, +%d DOM nodes', from, upTo - 1, nodes.length);
    // Attach sentinel before computing the scroll compensation. Sentinel height
    // changes (e.g. removing the sentinel when _startIdx reaches 0) happen above
    // the viewport and must be included in the positional correction so the user
    // does not see a visual jump when the oldest batch finishes loading.
    this._attachSentinel();
    this._c.scrollTop += this._c.scrollHeight - before;

    // Phase 3: cap historical DOM size; pruned content reloads on scroll-down.
    // Guard is message count (_endIdx - _startIdx), not DOM node count — agent
    // messages span many top-level nodes so DOM-node counting is unreliable here.
    var histMsgCount = this._endIdx - this._startIdx;
    if (histMsgCount > BIDI_MSG_CAP) {
      var _pruneTarget = this._endIdx - (histMsgCount - BIDI_MSG_CAP);
      var _beforePruneTop = this._c.scrollTop;
      var _pruneRemoved = 0;
      var _pruneLowest = this._endIdx;
      var _pRef = this._histSep
        ? this._histSep.previousSibling
        : this._c.lastElementChild;
      while (_pRef) {
        var _pPrev = _pRef.previousSibling;
        var _pIsCtl = (_pRef === this._sentinel || _pRef === this._bSentinel ||
                       _pRef === this._histSep ||
                       _pRef.classList.contains('chat-history-spacer'));
        if (!_pIsCtl) {
          var _pIdx = (_pRef.dataset && _pRef.dataset.chIdx !== undefined)
            ? parseInt(_pRef.dataset.chIdx, 10) : null;
          if (_pIdx === null || _pIdx < _pruneTarget) break;
          _pRef.remove();
          _pruneRemoved++;
          if (_pIdx < _pruneLowest) _pruneLowest = _pIdx;
        }
        _pRef = _pPrev;
      }
      if (_pruneRemoved > 0) {
        // Boundary: remove remaining siblings at the same chIdx so the first node
        // left in DOM always begins a complete message.
        var _pPeek = this._histSep
          ? this._histSep.previousElementSibling
          : this._c.lastElementChild;
        while (_pPeek && _pPeek !== this._sentinel && _pPeek !== this._bSentinel &&
               !_pPeek.classList.contains('chat-history-spacer')) {
          if (_pPeek.dataset && parseInt(_pPeek.dataset.chIdx, 10) === _pruneLowest) {
            var _pPeekNext = _pPeek.previousElementSibling;
            _pPeek.remove();
            _pPeek = _pPeekNext;
          } else { break; }
        }
        this._endIdx = _pruneLowest;
        console.log('[chatHistory] Phase 3 prune (load-older): removed %d nodes, endIdx → %d', _pruneRemoved, this._endIdx);
        this._attachBottomSentinel();
        // The prune reduced scrollHeight. Re-assert the pre-prune scrollTop so
        // the browser's implicit clamp does not silently move the user toward
        // the bottom. If the clamp is unavoidable (prune > content_below_viewport),
        // this pins to the highest achievable position.
        this._c.scrollTop = Math.min(
          _beforePruneTop,
          Math.max(0, this._c.scrollHeight - this._c.clientHeight)
        );
      }
    }
    var self = this;
    var _ogen = this._gen;
    requestAnimationFrame(function () {
      if (self._gen !== _ogen) return;
      self._loading = false;
      // If scrollToBottom() was called while _loadOlder() was running, restart drain
      if (self._draining && self._endIdx < self._all.length) {
        self._loadNewer();
      }
    });
  };

  // ---------------------------------------------------------------------------
  // _loadNewer — append a batch of historical messages (scroll down)
  // ---------------------------------------------------------------------------

  MessageWindow.prototype._isAtVeryBottom = function () {
    return this._c.scrollTop + this._c.clientHeight >= this._c.scrollHeight - 10;
  };

  MessageWindow.prototype._loadNewer = function () {
    if (this._loading) return;
    if (this._endIdx >= this._all.length) return;

    // Captured before any DOM changes. When the user is at the very bottom
    // (button press or equivalent), top-prune should snap rather than shift,
    // keeping the user at the bottom so the rAF chain can continue.
    // _draining takes precedence: in QtWebEngine with Vulkan compositing the
    // scrollTop DOM read-back after a same-frame assignment can return the
    // stale pre-assignment value, causing _isAtVeryBottom() to return false
    // even though we just snapped.  _draining is a JS-only flag that is not
    // subject to compositor lag, so trust it unconditionally.
    var atBottom = this._draining || this._isAtVeryBottom();

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

    var _deferAll2 = window.hljsDeferHighlightAll;
    for (var hi = 0; hi < nodes.length; hi++) {
      if (!nodes[hi].querySelectorAll) continue;
      if (_deferAll2) {
        _deferAll2(nodes[hi]);
      } else if (window.hljs) {
        var _bs2 = nodes[hi].querySelectorAll('pre code:not(.hljs)');
        for (var bi = 0; bi < _bs2.length; bi++) window.hljs.highlightElement(_bs2[bi]);
      }
    }

    this._endIdx = upTo;
    console.log('[chatHistory] Load newer: msgs %d–%d, +%d DOM nodes', from, upTo - 1, nodes.length);

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
        console.log('[chatHistory] Phase 3 prune (load-newer): removed %d nodes, startIdx → %d', removed, this._startIdx);
        // Attach sentinel before computing the scroll adjustment so that any
        // sentinel height change (e.g. adding a new sentinel when _startIdx
        // crosses 0) is included in the delta and the viewport does not jump.
        this._attachSentinel();
        if (atBottom) {
          // User wants to be at the bottom (button press): snap to new bottom so
          // the rAF chain condition (_isAtBottom) stays true and continues loading.
          this._c.scrollTop = this._c.scrollHeight - this._c.clientHeight;
        } else {
          // User is scrolling slowly through history: compensate for removed height
          // above the viewport so their visual position does not jump.
          this._c.scrollTop -= (before - this._c.scrollHeight);
        }
      }
    }

    this._attachBottomSentinel();
    var self = this;
    var _ngen = this._gen;
    requestAnimationFrame(function () {
      if (self._gen !== _ngen) { self._draining = false; return; }
      self._loading = false;

      // A scroll-driven load (not draining) processes exactly ONE batch and
      // stops, mirroring _loadOlder for scroll-up: the next batch loads when the
      // user scrolls the bottom sentinel back into view, with position preserved.
      // Only the scroll-to-bottom button (_draining) cascades through every
      // remaining batch and snaps to the true bottom. Without this gate, a scroll
      // that brings the sentinel within _isAtBottom()'s 120px proximity window
      // recursed to the end and behaved like the scroll-to-bottom button.
      if (!self._draining) return;

      if (self._endIdx < self._all.length) {
        // Drain mode: snap before the continuity check so hljs height inflation
        // between batches cannot break the threshold test, then load the next.
        self._c.scrollTop = self._c.scrollHeight - self._c.clientHeight;
        self._loadNewer();
        return;
      }

      // Drain reached the newest message: snap to the true bottom, then re-snap
      // as images and fonts inflate scrollHeight after the snap.
      self._draining = false;
      self._c.scrollTop = self._c.scrollHeight - self._c.clientHeight;
      var _rsGen = self._gen;
      var _drainImgs = self._c.querySelectorAll('img');
      for (var _di = 0; _di < _drainImgs.length; _di++) {
        if (!_drainImgs[_di].complete) {
          (function (img) {
            img.addEventListener('load', function () {
              if (self._gen !== _rsGen) return;
              self._c.scrollTop = self._c.scrollHeight - self._c.clientHeight;
            }, { once: true });
          })(_drainImgs[_di]);
        }
      }
      // Settling loop: re-snap each frame while scrollHeight grows (fonts, images).
      (function _settle(remaining, prevH) {
        requestAnimationFrame(function () {
          if (self._gen !== _rsGen) return;
          var h = self._c.scrollHeight;
          if (h !== prevH) {
            self._c.scrollTop = h - self._c.clientHeight;
          }
          if (remaining > 0 && h !== prevH) {
            _settle(remaining - 1, h);
          }
        });
      })(8, self._c.scrollHeight);
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
      var _mgen = self._gen;
      requestAnimationFrame(function () {
        if (self._gen !== _mgen) { self._prunePending = false; return; }
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
    var total = this._totalChildCount();
    if (total <= PRUNE_AT) return;
    var count = total - PRUNE_AT + PRUNE_COUNT;
    var hist  = this._histChildCount();
    if (hist > 0) {
      // Normal case: prune oldest historical messages (Phase 2).
      this._pruneTop(Math.min(hist, count));
    } else {
      // History exhausted — evict oldest live messages that are above the viewport.
      // They persist in DB and reload on session switch; we show a notice in-place.
      this._evictLive(count);
    }
  };

  // Evict the oldest `count` live DOM nodes (those immediately after _histSep).
  // Called when Phase 2 needs to prune but all historical nodes are gone.
  // Evicted messages are persisted in the DB and reload on session switch.
  MessageWindow.prototype._evictLive = function (count) {
    if (!this._histSep || !this._histSep.parentNode) return;

    // Collect oldest live nodes (right after _histSep), skipping control elements.
    var toRemove = [];
    var cur = this._histSep.nextElementSibling;
    while (cur && toRemove.length < count) {
      var isCtl = (cur === this._sentinel || cur === this._bSentinel ||
                   cur.classList.contains('chat-history-spacer') ||
                   cur.classList.contains('chat-live-evict-notice'));
      if (!isCtl) toRemove.push(cur);
      cur = cur.nextElementSibling;
    }
    if (!toRemove.length) return;

    var savedScrollTop = this._c.scrollTop;
    var before = this._c.scrollHeight;

    for (var i = 0; i < toRemove.length; i++) {
      var el = toRemove[i];
      // Stop any live timers/intervals before removing the node.
      if (el._waveInterval)   { clearInterval(el._waveInterval);   el._waveInterval   = null; }
      if (el._elapsedTicker)  { clearInterval(el._elapsedTicker);  el._elapsedTicker  = null; }
      if (el._streamRenderer) { el._streamRenderer = null; }
      var descendants = el.querySelectorAll('*');
      for (var j = 0; j < descendants.length; j++) {
        var d = descendants[j];
        if (d._waveInterval)   { clearInterval(d._waveInterval);   d._waveInterval   = null; }
        if (d._elapsedTicker)  { clearInterval(d._elapsedTicker);  d._elapsedTicker  = null; }
        if (d._streamRenderer) { d._streamRenderer = null; }
      }
      if (window.hljsDeferForgetNode) window.hljsDeferForgetNode(el);
      el.remove();
      this._evictedLiveCount++;
    }
    console.log('[chatHistory] Phase 2 evict: removed %d live nodes (total evicted: %d)', toRemove.length, this._evictedLiveCount);

    // Compensate for scrollHeight reduction (mirrors _pruneTop pattern).
    var delta = before - this._c.scrollHeight;
    if (delta > 0) {
      this._c.scrollTop = Math.min(
        savedScrollTop,
        Math.max(0, this._c.scrollHeight - this._c.clientHeight)
      );
    }

    this._updateEvictNotice();
    if (typeof requestIdleCallback !== 'undefined') {
      requestIdleCallback(function () {}, { timeout: 3000 });
    }
  };

  // Show or update the in-place notice above the live section after eviction.
  MessageWindow.prototype._updateEvictNotice = function () {
    if (!this._histSep || !this._histSep.parentNode || !this._evictedLiveCount) return;
    var notice = this._c.querySelector('.chat-live-evict-notice');
    if (!notice) {
      notice = document.createElement('div');
      notice.className = 'chat-live-evict-notice';
      notice.style.cssText = (
        'text-align:center;padding:6px 0;color:var(--fg);opacity:0.45;' +
        'font-size:0.8rem;user-select:none;flex-shrink:0'
      );
      this._histSep.insertAdjacentElement('afterend', notice);
    }
    notice.textContent = '↑ ' + this._evictedLiveCount +
      ' earlier message' + (this._evictedLiveCount !== 1 ? 's' : '') +
      ' not shown — reload session to see all';
  };

  // Count all non-control DOM children (excludes sentinels, spacer, sep).
  MessageWindow.prototype._totalChildCount = function () {
    var n        = 0;
    var children = this._c.children;
    for (var i = 0; i < children.length; i++) {
      var ch = children[i];
      if (ch === this._sentinel  ||
          ch === this._bSentinel ||
          ch === this._histSep   ||
          ch.classList.contains('chat-history-spacer') ||
          ch.classList.contains('chat-live-evict-notice')) continue;
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
    // Save before any DOM mutation. Node removal reduces scrollHeight and the browser
    // immediately clamps scrollTop to the new scrollHeight-clientHeight. The spacer
    // restores scrollHeight but not the clamped scrollTop, causing a visible jump.
    var savedScrollTop = this._c.scrollTop;
    var before   = this._c.scrollHeight;
    var removed  = 0;
    var highIdx  = -1;
    // Walk firstElementChild → nextElementSibling; capture next before removal
    // so we never touch the live HTMLCollection after mutating it.
    var ch = this._c.firstElementChild;
    while (ch && removed < count) {
      // Hard boundary: never cross into live messages after _histSep.
      if (ch === this._histSep) break;
      var next = ch.nextElementSibling;
      if (ch === this._sentinel  ||
          ch === this._bSentinel ||
          ch.classList.contains('chat-history-spacer')) { ch = next; continue; }
      var cidx = (ch.dataset && ch.dataset.chIdx !== undefined)
        ? parseInt(ch.dataset.chIdx, 10) : -1;
      if (ch._waveInterval)   { clearInterval(ch._waveInterval);   ch._waveInterval   = null; }
      if (ch._elapsedTicker)  { clearInterval(ch._elapsedTicker);  ch._elapsedTicker  = null; }
      if (ch._streamRenderer) { ch._streamRenderer = null; }
      var _ptDesc = ch.querySelectorAll('*');
      for (var _pi = 0; _pi < _ptDesc.length; _pi++) {
        if (_ptDesc[_pi]._waveInterval)   { clearInterval(_ptDesc[_pi]._waveInterval);   _ptDesc[_pi]._waveInterval   = null; }
        if (_ptDesc[_pi]._elapsedTicker)  { clearInterval(_ptDesc[_pi]._elapsedTicker);  _ptDesc[_pi]._elapsedTicker  = null; }
        if (_ptDesc[_pi]._streamRenderer) { _ptDesc[_pi]._streamRenderer = null; }
      }
      if (window.hljsDeferForgetNode) window.hljsDeferForgetNode(ch);
      ch.remove();
      removed++;
      if (cidx > highIdx) highIdx = cidx;
      ch = next;
    }
    if (removed === 0) return;
    console.log('[chatHistory] Phase 2 prune: removed %d nodes, startIdx → %d', removed, highIdx + 1);

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
          if (peek._waveInterval)   { clearInterval(peek._waveInterval);   peek._waveInterval   = null; }
          if (peek._elapsedTicker)  { clearInterval(peek._elapsedTicker);  peek._elapsedTicker  = null; }
          if (peek._streamRenderer) { peek._streamRenderer = null; }
          if (window.hljsDeferForgetNode) window.hljsDeferForgetNode(peek);
          peek.remove();
          removed++;
          peek = peekNext;
        } else {
          break;
        }
      }
      this._startIdx = highIdx + 1;
    }

    this._attachSentinel();

    // Collapse any leftover spacers from previous prune events into one
    var existingSpacers = this._c.querySelectorAll('.chat-history-spacer');
    for (var ei = 0; ei < existingSpacers.length; ei++) {
      existingSpacers[ei].remove();
    }

    // Compute needed spacer height AFTER all DOM changes (node removal, sentinel
    // update, spacer removal). Computing it earlier misses the sentinel's height
    // contribution when a new sentinel is added (e.g. _startIdx crossing 0→N),
    // which causes the spacer to overshoot and leaves slack equal to sentinel height.
    var totalDelta = before - this._c.scrollHeight;
    if (totalDelta > 0) {
      var spacer = document.createElement('div');
      spacer.className  = 'chat-history-spacer';
      spacer.style.cssText = (
        'height:' + totalDelta + 'px;flex-shrink:0;display:flex;' +
        'align-items:center;justify-content:center;' +
        'color:var(--fg);opacity:0.35;font-size:0.8rem'
      );
      // Only set text when the spacer is tall enough to display it legibly.
      // min-height on the spacer would add extra height beyond totalDelta,
      // creating a scroll geometry mismatch that causes visible position jumps.
      if (totalDelta >= 32) {
        spacer.textContent = 'Earlier messages pruned — scroll up to reload';
      }
      var afterSentinel = this._sentinel ? this._sentinel.nextSibling : null;
      if (afterSentinel) {
        this._c.insertBefore(spacer, afterSentinel);
      } else {
        this._c.prepend(spacer);
      }
    }
    // Spacer height ≈ removed nodes height, so scrollHeight ≈ original and
    // savedScrollTop is still a valid position. Restoring it undoes the browser
    // clamp that occurred during node removal.
    this._c.scrollTop = savedScrollTop;

    // Yield to idle after prune so V8 can run incremental GC on the detached subtrees.
    if (typeof requestIdleCallback !== 'undefined') {
      requestIdleCallback(function () {}, { timeout: 3000 });
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
        if (ref._waveInterval)   { clearInterval(ref._waveInterval);   ref._waveInterval   = null; }
        if (ref._elapsedTicker)  { clearInterval(ref._elapsedTicker);  ref._elapsedTicker  = null; }
        if (ref._streamRenderer) { ref._streamRenderer = null; }
        var _pbDesc = ref.querySelectorAll('*');
        for (var _pbi = 0; _pbi < _pbDesc.length; _pbi++) {
          if (_pbDesc[_pbi]._waveInterval)   { clearInterval(_pbDesc[_pbi]._waveInterval);   _pbDesc[_pbi]._waveInterval   = null; }
          if (_pbDesc[_pbi]._elapsedTicker)  { clearInterval(_pbDesc[_pbi]._elapsedTicker);  _pbDesc[_pbi]._elapsedTicker  = null; }
          if (_pbDesc[_pbi]._streamRenderer) { _pbDesc[_pbi]._streamRenderer = null; }
        }
        if (window.hljsDeferForgetNode) window.hljsDeferForgetNode(ref);
        ref.remove();
        removed++;
        if (idx !== null && idx < lowestIdx) lowestIdx = idx;
      }
      ref = prev;
    }

    if (removed > 0) {
      // Partial-message cleanup: if the loop stopped mid-message (a single _all entry
      // spans multiple DOM children), remove the remaining fragments at the boundary.
      // Without this, _loadNewer renders the message again over the orphaned nodes,
      // duplicating it in the DOM.
      var check = this._histSep
        ? this._histSep.previousElementSibling
        : this._c.lastElementChild;
      while (check && check !== this._sentinel && check !== this._bSentinel &&
             !check.classList.contains('chat-history-spacer')) {
        if (check.dataset && parseInt(check.dataset.chIdx, 10) === lowestIdx) {
          var prevCheck = check.previousElementSibling;
          if (check._waveInterval)   { clearInterval(check._waveInterval);   check._waveInterval   = null; }
          if (check._elapsedTicker)  { clearInterval(check._elapsedTicker);  check._elapsedTicker  = null; }
          if (check._streamRenderer) { check._streamRenderer = null; }
          if (window.hljsDeferForgetNode) window.hljsDeferForgetNode(check);
          check.remove();
          check = prevCheck;
        } else {
          break;
        }
      }
      this._endIdx = lowestIdx;
      this._attachBottomSentinel();
      if (typeof requestIdleCallback !== 'undefined') {
        requestIdleCallback(function () {}, { timeout: 3000 });
      }
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
