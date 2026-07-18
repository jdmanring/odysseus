// trimChatHistory_4661.js -- VENDORED SNAPSHOT. Not shipping code; benchmark input only.
//
// Source: upstream PR #4661 ("fix(ui): prevent browser OOM during long agent
// interactions", holden093), commit 27f35e1c1303ec9732bae68e8c32c14ebd3e82a6,
// static/js/chat.js hunk: _trimChatHistoryDOM + _loadOlderMessages, extracted
// verbatim except the marked HARNESS ADAPTERS (renderer + fetch + session id),
// which replace app modules unavailable in the bench page. Every constant and
// every teardown/removal line is the PR's own.
//
// What this measures: #4661's actual DOM-bounding behavior -- a 150-child cap
// (MAX_CHAT_DOM_NODES) enforced by removing oldest children with per-node
// interval teardown and data-URI image blanking, older messages recoverable
// through a click-driven "Show N older messages" bar backed by server paging.
// The bench's scroll-driven excursions do NOT apply to this arm (its reload is
// click-driven, not scroll-driven); those cells are withheld by the harness's
// completeness guard, and loadOlderAll() exists for click-path measurements.
(function () {
  'use strict';

  var MAX_CHAT_DOM_NODES = 150;
  var _unloadedMsgCount = 0;

  // HARNESS ADAPTER: chatRenderer.addMessage -> capture the element the mock
  // chatModule appends (the mock returns it, matching chatRenderer's contract).
  function _renderMessage(role, content) {
    return window.chatModule.addMessage(role, content);
  }

  function _trimChatHistoryDOM() {
    var box = document.getElementById('chat-history');
    if (!box) return;
    var children = box.children;
    if (children.length <= MAX_CHAT_DOM_NODES) return;
    var keepFloor = Math.min(20, Math.floor(MAX_CHAT_DOM_NODES / 4));

    var existingBar = box.querySelector('.load-older-bar');
    if (existingBar) {
      existingBar.remove();
    }

    var offloaded = 0;
    var maxIdx = Math.max(0, children.length - keepFloor);
    for (var i = 0; i < maxIdx && children.length > MAX_CHAT_DOM_NODES; i++) {
      var el = children[i];
      if (!el) break;

      if (el._waveInterval) { clearInterval(el._waveInterval); el._waveInterval = null; }
      if (el._elapsedTicker) { clearInterval(el._elapsedTicker); el._elapsedTicker = null; }
      if (el._spinner) { try { el._spinner.destroy(); } catch (_) {} }
      el.querySelectorAll('.agent-thread-node').forEach(function (n) {
        if (n._waveInterval) { clearInterval(n._waveInterval); n._waveInterval = null; }
        if (n._elapsedTicker) { clearInterval(n._elapsedTicker); n._elapsedTicker = null; }
      });
      el.querySelectorAll('img[src^="data:"]').forEach(function (img) {
        img.src = '';
      });

      if (el.classList.contains('msg') || el.classList.contains('agent-thread')) {
        offloaded++;
      }
      el.remove();
      i--;
    }

    if (offloaded > 0) {
      _unloadedMsgCount += offloaded;
      var bar = document.createElement('div');
      bar.className = 'load-older-bar';
      bar.textContent = 'Show ' + _unloadedMsgCount + ' older messages';
      bar.addEventListener('click', function () {
        _loadOlderMessages(box, bar);
      });
      box.insertBefore(bar, box.firstChild);
    }
  }

  // HARNESS ADAPTER: the fetch of /api/history?limit=50&offset=... becomes a
  // corpus slice with the PR's exact offset arithmetic; page size unchanged.
  function _fetchOlderPage() {
    var offset = Math.max(0, _unloadedMsgCount - 50);
    return Promise.resolve(window.__trimCorpus.slice(offset, offset + 50));
  }

  function _loadOlderMessages(box, bar) {
    if (bar._loading) return;
    bar._loading = true;
    bar.textContent = 'Loading…';
    bar.style.pointerEvents = 'none';
    return _fetchOlderPage().then(function (msgs) {
      if (msgs.length === 0) {
        bar.textContent = 'No older messages';
        return;
      }
      for (var i = 0; i < msgs.length; i++) {
        var el = _renderMessage(msgs[i].role, msgs[i].content);
        if (el) box.insertBefore(el, bar);
      }
      _unloadedMsgCount = Math.max(0, _unloadedMsgCount - msgs.length);
      if (_unloadedMsgCount <= 0) {
        bar.remove();
      } else {
        bar.textContent = 'Show ' + _unloadedMsgCount + ' older messages';
        bar._loading = false;
        bar.style.pointerEvents = '';
      }
    });
  }

  window.trim4661 = {
    // Steady-state session shape: messages append over time with the PR's trim
    // running after each append (its call sites run it on message-add paths).
    load: function (corpus) {
      window.__trimCorpus = corpus;
      for (var i = 0; i < corpus.length; i++) {
        var el = window.chatModule.addMessage(corpus[i].role, corpus[i].content);
        if (el && el.dataset) el.dataset.i = String(i);   // bench message markers
        _trimChatHistoryDOM();
      }
    },
    trim: _trimChatHistoryDOM,
    // Click the bar until every offloaded message is back (the arm's reload
    // path -- click-driven, the analogue of the others' scroll-back).
    loadOlderAll: async function () {
      var box = document.getElementById('chat-history');
      var t0 = performance.now();
      var clicks = 0;
      for (;;) {
        var bar = box.querySelector('.load-older-bar');
        if (!bar || _unloadedMsgCount <= 0) break;
        await _loadOlderMessages(box, bar);
        clicks++;
        if (clicks > 10000) break;
      }
      return { ms: +(performance.now() - t0).toFixed(1), clicks: clicks,
               remaining: _unloadedMsgCount };
    },
    stats: function () {
      return { unloaded: _unloadedMsgCount,
               children: document.getElementById('chat-history').children.length };
    }
  };
})();
