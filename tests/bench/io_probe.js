/* Reusable IntersectionObserver delivery probe for tests and diagnostics.
 *
 * Wraps window.IntersectionObserver so every observer created AFTER install()
 * logs its lifecycle to window.__ioLog:
 *   {t, id, ev: 'observe',    cls}    -- observe(el) called (cls = el.className)
 *   {t, id, ev: 'cb',         inter}  -- delivery; inter = entries.map(isIntersecting)
 *   {t, id, ev: 'disconnect'}         -- disconnect() called
 *
 * Why it exists: IO queues one entry per transition between deliveries, so a
 * busy main thread can hand a callback SEVERAL entries at once (a batched
 * leave+enter pair logs as inter: [false, true]). A callback that reads only
 * entries[0] acts on stale state -- this probe is what caught exactly that
 * dead-end in chatHistory.js's top sentinel (a single delivery with
 * [false, true], read as "left", discarding the enter forever). When paging or
 * lazy-loading stalls with an armed observer, install this before the driver
 * runs and read the tail of window.__ioLog at the stall.
 *
 * Usage (Playwright): page.evaluate(IO_PROBE_JS) BEFORE the code under test
 * creates its observers; then page.evaluate("window.ioProbe.log()") to read.
 * install() is idempotent; uninstall() restores the native constructor for
 * observers created afterwards (already-wrapped instances keep logging).
 */
(function () {
  'use strict';
  if (window.ioProbe) return;

  var Native = window.IntersectionObserver;
  var seq = 0, installed = false;

  function install() {
    if (installed) return;
    installed = true;
    window.__ioLog = window.__ioLog || [];
    window.IntersectionObserver = function (cb, opts) {
      var id = ++seq;
      var log = window.__ioLog;
      var o = new Native(function (entries, obs) {
        log.push({ t: performance.now() | 0, id: id, ev: 'cb',
                   inter: entries.map(function (e) { return e.isIntersecting; }) });
        return cb(entries, obs);
      }, opts);
      var obsFn = o.observe.bind(o), disFn = o.disconnect.bind(o);
      o.observe = function (el) {
        log.push({ t: performance.now() | 0, id: id, ev: 'observe',
                   cls: el && el.className });
        return obsFn(el);
      };
      o.disconnect = function () {
        log.push({ t: performance.now() | 0, id: id, ev: 'disconnect' });
        return disFn();
      };
      o.__ioProbeId = id;
      return o;
    };
    window.IntersectionObserver.prototype = Native.prototype;
  }

  function uninstall() {
    if (!installed) return;
    installed = false;
    window.IntersectionObserver = Native;
  }

  window.ioProbe = {
    install: install,
    uninstall: uninstall,
    log: function () { return window.__ioLog || []; },
    clear: function () { window.__ioLog = []; }
  };
  install();
})();
