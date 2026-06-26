import json
import os
import re as _re
import sys
import time as _time

# ==============================================================================
# CRITICAL: Logging setup must happen BEFORE any PyQt6/QtWebEngine imports.
#
# sys.stdout/stderr alone is not enough — Chromium renderer subprocesses inherit
# OS-level file descriptors (fd 1, fd 2), not Python's sys.stdout/stderr.
# os.dup2 replaces the OS fds so all child process output lands in our log.
# ==============================================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Rotate logs at startup rather than mid-run: once os.dup2 binds the Chromium
# renderer's inherited fds to the log inode, the file cannot be swapped while
# the process lives. Renaming before the open+dup2 avoids that constraint.
# Constants match src/constants.py (LOG_MAX_BYTES, LOG_BACKUP_COUNT) so all
# three log files follow the same retention policy.
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB — matches app RotatingFileHandler
_LOG_BACKUP_COUNT = 5               # matches app LOG_BACKUP_COUNT


def _rotate_log(path: str) -> None:
    """Shift existing backups and rename path → path.1 if over _LOG_MAX_BYTES.

    Mirrors the behaviour of logging.handlers.RotatingFileHandler with
    backupCount=_LOG_BACKUP_COUNT. Silent on any error.
    """
    try:
        if os.path.getsize(path) <= _LOG_MAX_BYTES:
            return
        # Shift: path.4 → path.5, path.3 → path.4, ..., path.1 → path.2
        for n in range(_LOG_BACKUP_COUNT, 1, -1):
            src = f'{path}.{n - 1}'
            dst = f'{path}.{n}'
            if os.path.exists(src):
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(src, dst)
        # Move current log to path.1
        backup = path + '.1'
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(path, backup)
    except OSError:
        pass


_rotate_log(os.path.join(LOG_DIR, "wrapper_system.log"))
_log_file = open(os.path.join(LOG_DIR, "wrapper_system.log"), "a", buffering=1)
sys.stdout.flush()
sys.stderr.flush()
os.dup2(_log_file.fileno(), 1)   # redirect fd 1: Chromium renderer stdout → our log
os.dup2(_log_file.fileno(), 2)   # redirect fd 2: Chromium renderer stderr → our log
sys.stdout = _log_file
sys.stderr = _log_file
print(f'[LOG] wrapper_system.log opened at {_time.strftime("%Y-%m-%dT%H:%M:%S")}',
      flush=True)

# GPU vendor detection. /proc/driver/nvidia is created by the NVIDIA proprietary
# kernel module (including nvidia-open); absent for Mesa drivers (AMD, Intel, Nouveau).
_is_nvidia = os.path.exists("/proc/driver/nvidia")

if _is_nvidia:
    # Qt 6.9+ regression: forces GBM even on drivers without GBM support.
    # NVIDIA proprietary does not implement GBM buffer allocation; the forced
    # path causes black windows (qutebrowser #8535). setdefault preserves any
    # user environment override.
    os.environ.setdefault("QTWEBENGINE_FORCE_USE_GBM", "0")

# DefaultANGLEVulkan omitted for all GPU types: forces ANGLE to a Vulkan
# backend, which conflicts with Qt WebEngine 6.6+'s own Vulkan path on
# ozone/Wayland and causes blank windows (Chromium bug 334275637).
_gpu_flags = []
if not _is_nvidia:
    # Mesa (AMD, Intel, Nouveau): GBM buffer allocation is the native rendering
    # path. Zero-copy avoids a CPU→GPU texture upload per rendered frame.
    # Omitted on NVIDIA proprietary: no GBM support in that driver.
    _gpu_flags.append("--enable-zero-copy")

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join([
    "--no-sandbox",
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
    "--enable-features=WebGPU,SharedArrayBuffer,PartitionAllocMemoryReclaimer,BlinkHeapCompaction",
    "--enable-logging=stderr --log-level=1",  # captured via os.dup2 into wrapper_system.log
    "--remote-debugging-port=9222",            # Chrome DevTools at http://localhost:9222
    "--js-flags=--expose-gc,--initial-old-space-size=128,--max-old-space-size=512,--optimize-for-size,--minor-mc",
    "--renderer-process-limit=1",
    "--disable-extensions",
    # NB: --enable-low-end-device-mode is deliberately NOT set. It caused a
    # lighter-rectangle raster tint on dark themes (its low-fidelity raster path,
    # tile-aligned, ~+4/+4/+5 lighter than --bg), and did not bound the actual
    # OOM — which is Oilpan detached-DOM growth (e.g. transient CSS :hover
    # pseudo-element churn), a separate pool from the raster tile budget.
    *_gpu_flags,
])

import concurrent.futures as _futures
import signal
import socket as _cdp_sock
import struct as _cdp_struct
import base64 as _cdp_b64
import urllib.request as _cdp_req
import subprocess
import threading as _threading
import time
from PyQt6.QtWidgets import QApplication, QMainWindow, QColorDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PyQt6.QtCore import QUrl, QObject, QFile, QIODevice, QTimer, QSettings, QEvent, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QDesktopServices

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(INSTALL_DIR, "venv", "bin", "python")
PORT = os.environ.get("APP_PORT", "7000")
WINDOW_TITLE = "Odysseus"
PROFILE_NAME = "odysseus"
DATA_DIR = os.path.expanduser("~/.local/share/odysseus/webengine")
CACHE_DIR = os.path.expanduser("~/.cache/odysseus/webengine")

_UVICORN_PATTERN = "uvicorn app:app"
_server_proc = None


def kill_zombies():
    result = subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)
    if result.returncode == 0:
        print("Killed stale uvicorn process(es), waiting for port to release...")
        time.sleep(1)


def start_server():
    global _server_proc
    print(f"Starting Odysseus server on port {PORT}...")
    cmd = [VENV_PYTHON, "-m", "uvicorn", "app:app",
           "--host", "127.0.0.1", "--port", PORT, "--access-log"]
    env = os.environ.copy()
    env["ODYSSEUS_LOG_FILE"] = os.path.join(LOG_DIR, "server.log")
    _rotate_log(os.path.join(LOG_DIR, "server_access.log"))
    _access_log = open(os.path.join(LOG_DIR, "server_access.log"), "a", buffering=1)
    _server_proc = subprocess.Popen(
        cmd,
        cwd=INSTALL_DIR,
        env=env,
        stdout=_access_log,
        stderr=_access_log,
        start_new_session=True,
    )
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{PORT}", timeout=1)
            print("Server ready.")
            return True
        except Exception:
            time.sleep(0.5)
    print("Server slow to start, proceeding anyway.")
    return False


def stop_server():
    global _server_proc
    print("Stopping server...")
    if _server_proc is not None:
        try:
            _server_proc.terminate()
            _server_proc.wait(timeout=5)
        except Exception:
            try:
                _server_proc.kill()
            except Exception:
                pass
        _server_proc = None
    _cdp_executor.shutdown(wait=False, cancel_futures=True)
    subprocess.run(["pkill", "-f", _UVICORN_PATTERN], check=False)
    print("Server stopped.")


def _signal_handler(sig, frame):
    stop_server()
    sys.exit(0)


def _cdp_ws_call(ws_url, method, params=None):
    """Send one CDP command to an already-resolved ws:// URL and return the result.

    Shared by _cdp_call (page target) and _cdp_browser_call (browser target).
    Returns the CDP result dict or None on any error.
    """
    try:
        hostpath = ws_url[len('ws://'):]
        host_port, path = hostpath.split('/', 1)
        host_name, port_s = host_port.split(':')
        s = _cdp_sock.create_connection((host_name, int(port_s)), timeout=2)
        try:
            key = _cdp_b64.b64encode(os.urandom(16)).decode()
            s.sendall((
                f'GET /{path} HTTP/1.1\r\nHost: {host_port}\r\n'
                'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'
            ).encode())
            buf = b''
            while b'\r\n\r\n' not in buf:
                buf += s.recv(4096)
            if b' 101 ' not in buf.split(b'\r\n')[0]:
                return None
            payload_obj = {'id': 1, 'method': method}
            if params:
                payload_obj['params'] = params
            msg = json.dumps(payload_obj).encode()
            mask = os.urandom(4)
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(msg))
            frame_len = len(msg)
            length_byte = 0x7E if frame_len > 125 else frame_len
            header = bytes([0x81, 0x80 | length_byte])
            if frame_len > 125:
                header += _cdp_struct.pack('!H', frame_len)
            s.sendall(header + mask + masked)
            hdr = b''
            while len(hdr) < 2:
                hdr += s.recv(2 - len(hdr))
            dlen = hdr[1] & 0x7F
            if dlen == 126:
                lb = b''
                while len(lb) < 2:
                    lb += s.recv(2 - len(lb))
                dlen = _cdp_struct.unpack('!H', lb)[0]
            data = b''
            while len(data) < dlen:
                data += s.recv(dlen - len(data))
            return json.loads(data.decode()).get('result')
        finally:
            s.close()
    except Exception:
        return None


def _cdp_call(method, params=None):
    """One-shot CDP call on the page target via stdlib WebSocket.

    Embedded Chromium builds (PyQt, Electron, native wrappers) do not receive OS
    memory-pressure signals that would trigger Oilpan's automatic GC, so Python-side
    CDP calls are the reliable way to invoke collection without --expose-gc.
    Returns the CDP result dict or None on any error.
    """
    try:
        raw = _cdp_req.urlopen('http://localhost:9222/json', timeout=1).read()
        pages = json.loads(raw)
        ws_url = next(
            (p['webSocketDebuggerUrl'] for p in pages if p.get('type') == 'page'),
            None,
        )
        if not ws_url:
            return None
        return _cdp_ws_call(ws_url, method, params)
    except Exception:
        return None


def _cdp_browser_call(method, params=None):
    """One-shot CDP call on the browser target via stdlib WebSocket.

    Browser-level commands (e.g. Memory.simulatePressureNotification) must be sent
    to the browser target — they are not dispatched to renderer processes when called
    from a page target. The browser target URL is at /json/version rather than /json.
    Returns the CDP result dict or None on any error.
    """
    try:
        raw = _cdp_req.urlopen('http://localhost:9222/json/version', timeout=1).read()
        info = json.loads(raw)
        ws_url = info.get('webSocketDebuggerUrl')
        if not ws_url:
            return None
        return _cdp_ws_call(ws_url, method, params)
    except Exception:
        return None


# Pattern that chatHistory.js emits at the end of each Phase 2 eviction batch.
_RE_EVICT = _re.compile(r'\[chatHistory\] Phase 2 evict: removed (\d+) live nodes')

# Bounds CDP background work to eviction audit threads (5 s sleep each).
_cdp_executor = _futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='cdp')

# Renderer reclaim policy (issue #106). simulatePressureNotification is a no-op on
# QtWebEngine; Memory.forciblyPurgeJavaScriptMemory actually reclaims the renderer
# cache (measured 5.2 GB and 3.7 GB freed in single calls). The purge causes a ~1s
# stutter, so it is only ever fired off the interaction path (mouse-idle,
# focus-loss), gated by an RSS ceiling so light use never stutters, and rate-limited
# so it cannot repeat back to back.
_PURGE_RSS_CEILING_KB = 1_800_000   # ~1.8 GB; baseline after a purge is ~1.1 GB
_PURGE_MIN_INTERVAL_S = 15
# Seconds of no user input (mouse OR keyboard) before the renderer counts as idle
# and the periodic reclaim is allowed to fire. Short enough to catch a walk-away,
# long enough that a brief reading pause does not trigger a purge mid-glance.
_IDLE_RECLAIM_AFTER_S = 3.0

# GC request cell — written by background threads (PSI monitor), read and drained
# by a 250 ms QTimer on the Qt main thread.  CPython's GIL makes single-element
# list assignment atomic so no explicit lock is needed.
_gc_request_pending: list[bool] = [False]


def _request_async_gc() -> None:
    """Signal the main-thread drain timer to schedule an async JS GC cycle.

    Thread-safe: sets a module-level flag that the Qt main thread polls every
    250 ms.  Using a flag + poll avoids QTimer.singleShot from a non-Qt daemon
    thread (which has no event loop and would silently drop the call).
    """
    _gc_request_pending[0] = True


def _cdp_audit_listeners(n_evicted: int) -> None:
    """Measure jsEventListeners delta 5 s after a Phase 2 eviction batch.

    Runs in a background thread. Captures the listener count immediately before
    sleeping (pre-GC baseline) then again after GC has had time to collect the
    evicted nodes. A delta close to zero after evicting N nodes with continue
    buttons indicates listener retention; a delta ≈ N confirms clean release.
    """
    pre = _cdp_call('Memory.getDOMCounters')
    pre_listeners = pre.get('jsEventListeners', 0) if pre else None
    _time.sleep(5)
    post = _cdp_call('Memory.getDOMCounters')
    if post and pre_listeners is not None:
        post_listeners = post.get('jsEventListeners', 0)
        delta = pre_listeners - post_listeners
        print(
            f'[CDP] post-evict listeners:'
            f' before={pre_listeners} after={post_listeners}'
            f' delta={delta} nodes-evicted={n_evicted}',
            flush=True,
        )


def _start_psi_monitor():
    """Background thread monitoring Linux /proc/pressure/memory (PSI).

    PSI avg10 measures the fraction of time tasks are stalled waiting for memory
    over the last 10 seconds. When it exceeds 5% the system is under genuine memory
    pressure. This mirrors the OS memory-pressure signal path that is absent in
    embedded QtWebEngine builds — the signal that would normally trigger Oilpan's
    automatic collection in a regular browser.

    Skipped silently on kernels < 4.20 and non-Linux platforms.
    """
    _PSI_PATH = '/proc/pressure/memory'
    _POLL_INTERVAL = 5    # seconds
    _THRESHOLD_PCT = 5.0  # avg10 % that triggers a GC request
    _COOLDOWN = 30        # minimum seconds between GC requests under sustained pressure

    if not os.path.exists(_PSI_PATH):
        return

    def _loop():
        last_gc = 0.0
        while True:
            try:
                with open(_PSI_PATH) as f:
                    for line in f:
                        if line.startswith('some'):
                            avg10 = float(line.split()[1].split('=')[1])
                            if avg10 > _THRESHOLD_PCT:
                                now = _time.monotonic()
                                if now - last_gc >= _COOLDOWN:
                                    last_gc = now
                                    print(
                                        f'[MEM] PSI avg10={avg10:.2f}% > {_THRESHOLD_PCT}%'
                                        f' — queuing async JS GC',
                                        flush=True,
                                    )
                                    _request_async_gc()
                            break
            except Exception:
                pass
            _time.sleep(_POLL_INTERVAL)

    _threading.Thread(target=_loop, daemon=True, name='psi-monitor').start()
    print('[MEM] PSI memory pressure monitor started', flush=True)


class NativeBridge(QObject):
    colorPicked = pyqtSignal(str)

    @pyqtSlot()
    def openColorPicker(self):
        bus = QDBusConnection.sessionBus()
        portal = QDBusInterface(
            'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop',
            'org.freedesktop.portal.Screenshot',
            bus,
        )
        if not portal.isValid():
            self._fallback()
            return

        reply = portal.call('PickColor', '', {})
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            self._fallback()
            return

        request_path = str(reply.arguments()[0])
        bus.connect(
            'org.freedesktop.portal.Desktop',
            request_path,
            'org.freedesktop.portal.Request',
            'Response',
            self._on_response,
        )

    @pyqtSlot('uint', 'QVariantMap')
    def _on_response(self, response, results):
        QDBusConnection.sessionBus().disconnect(
            'org.freedesktop.portal.Desktop', '',
            'org.freedesktop.portal.Request', 'Response',
            self._on_response,
        )
        if response == 0 and 'color' in results:
            try:
                color = results['color']
                try:
                    r, g, b = color
                except TypeError:
                    color.beginStructure()
                    r, g, b = color.asVariant(), color.asVariant(), color.asVariant()
                    color.endStructure()
                self.colorPicked.emit('#{:02x}{:02x}{:02x}'.format(
                    round(r * 255), round(g * 255), round(b * 255)
                ))
                return
            except Exception as e:
                print(f'[BRIDGE] color portal error: {e}', flush=True)
        self.colorPicked.emit('')

    def _fallback(self):
        color = QColorDialog.getColor()
        self.colorPicked.emit(color.name() if color.isValid() else '')


class OdysseusPage(QWebEnginePage):
    """QWebEnginePage subclass that routes external links to the system browser."""

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Chromium's --enable-logging=stderr captures the renderer's internal log but
        # NOT JavaScript console.log() — those only reach Python via this override.
        # Print without a prefix so structured [tag] messages sort cleanly in the log.
        label = level.name if hasattr(level, 'name') else str(level)
        if label in ('WARNING', 'ERROR', 'CRITICAL'):
            print(f'[JS:{label}] {message}', flush=True)
        else:
            print(message, flush=True)
        # When chatHistory.js evicts a Phase 2 batch, audit whether jsEventListeners
        # drops proportionally — confirms that WeakRef fixes released the closures.
        m = _RE_EVICT.match(message)
        if m:
            _cdp_executor.submit(_cdp_audit_listeners, int(m.group(1)))

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if is_main_frame and url.host() not in ('localhost', '127.0.0.1'):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, win_type):
        page = QWebEnginePage(self.profile(), self)
        page.urlChanged.connect(lambda url: (QDesktopServices.openUrl(url), page.deleteLater()))
        return page


class _InputIdleFilter(QObject):
    """App-level event filter that records the last user-input time and restarts the
    post-interaction idle timer.

    Qt WebEngine handles input internally, but Qt delivers these events at the
    QApplication level before Chromium consumes them, so installing this filter on
    QApplication.instance() catches all interaction over any widget or the web
    content area. It tracks keyboard as well as mouse so that typing defers the
    reclaim purge: a forcible purge causes a ~1s stutter, so it must never fire
    mid-typing.
    """
    _INPUT_EVENTS = frozenset((
        QEvent.Type.MouseMove,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.KeyPress,
        QEvent.Type.Wheel,
    ))

    def __init__(self, on_input, timer: QTimer, parent=None):
        super().__init__(parent)
        self._on_input = on_input
        self._timer = timer

    def eventFilter(self, obj, event):
        if event.type() in self._INPUT_EVENTS:
            self._on_input()
            self._timer.start()
        return False


class OdysseusWindow(QMainWindow):
    def __init__(self, profile: QWebEngineProfile):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.browser = QWebEngineView()
        page = OdysseusPage(profile, self.browser)
        self._page = page  # held for lifecycle management in changeEvent
        self._last_purge = 0.0  # monotonic ts of last forcible renderer purge
        self._last_input = time.monotonic()  # ts of last mouse/keyboard activity

        # Inject synchronous flag so JS knows it's running inside the Qt wrapper
        flag_script = QWebEngineScript()
        flag_script.setSourceCode("window.__QT_WRAPPER__ = true;")
        flag_script.setName("qt-wrapper-flag")
        flag_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        flag_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        page.scripts().insert(flag_script)

        # Inject Qt's qwebchannel.js from Qt's internal resources
        _f = QFile(":/qtwebchannel/qwebchannel.js")
        _f.open(QIODevice.OpenModeFlag.ReadOnly)
        _qwc_js = bytes(_f.readAll()).decode()
        _f.close()
        qwc_script = QWebEngineScript()
        qwc_script.setSourceCode(_qwc_js)
        qwc_script.setName("qwebchannel.js")
        qwc_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        qwc_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        page.scripts().insert(qwc_script)

        # Native bridge — held as instance attrs to prevent GC
        self._bridge = NativeBridge()
        self._channel = QWebChannel(page)
        self._channel.registerObject("bridge", self._bridge)
        page.setWebChannel(self._channel)

        # Renderer crash recovery — auto-reload on OOM or hard crash
        self._crash_times = []
        def _on_renderer_crash(status, exit_code):
            label = {0: 'Normal', 1: 'Abnormal', 2: 'Crashed', 3: 'Killed(OOM)'}.get(
                status.value, f'Unknown({status.value})')
            print(f'[RENDERER] {label} exit={exit_code} at {_time.strftime("%H:%M:%S")}',
                  flush=True)
            if status.value == 0:
                return
            now = _time.monotonic()
            self._crash_times = [t for t in self._crash_times if now - t < 10]
            if self._crash_times:
                print('[RENDERER] Crash loop — not reloading', flush=True)
                return
            self._crash_times.append(now)
            print('[RENDERER] Scheduling reload in 1s', flush=True)
            QTimer.singleShot(1000, lambda: self.browser.setUrl(
                QUrl(f"http://localhost:{PORT}")))
        page.renderProcessTerminated.connect(_on_renderer_crash)

        # Periodic renderer memory snapshot (every 60s).
        # Polls /proc/<pid>/status for RSS and CDP Memory.getDOMCounters for live
        # Oilpan node counts. When node accumulation is high, triggers a CDP purge
        # so collection doesn't wait for the next focus-loss event.
        _last_vmpeak: list[int] = [0]  # mutable cell for closure capture

        def _log_renderer_memory():
            rss_before = 0
            pid = page.renderProcessPid()
            if pid:
                try:
                    with open(f'/proc/{pid}/status') as f:
                        for line in f:
                            if line.startswith('VmRSS'):
                                rss_before = int(line.split()[1])
                                print(f'[MEM] pid={pid} {line.rstrip()}', flush=True)
                            elif line.startswith('VmPeak'):
                                kb = int(line.split()[1])
                                if kb > _last_vmpeak[0]:
                                    _last_vmpeak[0] = kb
                                    print(f'[MEM] pid={pid} {line.rstrip()} (new peak)',
                                          flush=True)
                except OSError as e:
                    print(f'[MEM] error: {e}', flush=True)
            counts = _cdp_call('Memory.getDOMCounters')
            if counts:
                nodes = counts.get('nodes', 0)
                listeners = counts.get('jsEventListeners', 0)
                # listeners/node ratio should be roughly constant (~3–5× for a
                # typical chat session). A rising ratio indicates a listener leak
                # — either removeEventListener is being skipped or setInterval
                # closures are preventing GC of elements that still hold listeners.
                ratio = f'{listeners / nodes:.1f}' if nodes else 'n/a'
                print(
                    f'[CDP] nodes={nodes} '
                    f'documents={counts.get("documents")} '
                    f'listeners={listeners} (listeners/node={ratio})',
                    flush=True,
                )
                # Detached node accumulation above this threshold means Oilpan is not
                # keeping up.  Direct runJavaScript call is safe here because
                # _log_renderer_memory runs on the Qt main thread via QTimer.
                if nodes > 50_000:
                    print(
                        f'[GC] node-count threshold ({nodes} > 50000)'
                        f' — async JS GC',
                        flush=True,
                    )
                    page.runJavaScript(
                        "if(typeof gc==='function')"
                        "gc({type:'major',execution:'async'});"
                    )
            # This periodic timer is telemetry only. The renderer purge is NOT
            # fired here: the timer runs regardless of interaction and a forcible
            # purge causes a ~1s stutter. Reclaim happens strictly off the
            # interaction path (mouse-idle and focus-loss) via _purge_renderer.
            # The previous call here, simulatePressureNotification('critical'), was
            # a no-op on QtWebEngine (measured: no RSS change) — issue #106.
            del rss_before  # was only used by the removed eviction telemetry

        self._mem_timer = QTimer()
        self._mem_timer.timeout.connect(_log_renderer_memory)
        self._mem_timer.start(30_000)
        _start_psi_monitor()

        # Focus-loss GC timer: 500 ms single-shot debounce started on WindowDeactivate,
        # cancelled on WindowActivate.  Skips transient focus shifts (notifications,
        # dropdowns) that would otherwise trigger unnecessary GC mid-typing.
        def _on_focus_loss_gc():
            print('[GC] focus-loss — async JS GC', flush=True)
            page.runJavaScript(
                "if(typeof gc==='function')"
                "gc({type:'major',execution:'async'});"
            )
            # Window is not focused: a reclaim stutter is invisible. Gated and
            # rate-limited inside _purge_renderer.
            self._purge_renderer('focus-loss')
        self._gc_focus_timer = QTimer()
        self._gc_focus_timer.setSingleShot(True)
        self._gc_focus_timer.timeout.connect(_on_focus_loss_gc)

        # PSI drain timer: polls _gc_request_pending every 250 ms on the main thread.
        # QTimer.singleShot from a daemon Python thread (PSI monitor) has no event
        # loop to fire on; this polling pattern is the correct cross-thread dispatch.
        def _drain_gc_requests():
            if not _gc_request_pending[0]:
                return
            _gc_request_pending[0] = False
            print('[GC] async JS GC — PSI', flush=True)
            page.runJavaScript(
                "if(typeof gc==='function')"
                "gc({type:'major',execution:'async'});"
            )
        self._gc_drain_timer = QTimer()
        self._gc_drain_timer.timeout.connect(_drain_gc_requests)
        self._gc_drain_timer.start(250)

        # Post-interaction reclaim: when input has been still for 2 seconds the user
        # has paused, so a reclaim stutter is invisible. This gives a fast reclaim
        # right after the user stops, for the focused-but-idle case (reading a long
        # response) that focus-loss does not cover. Gated and rate-limited inside
        # _purge_renderer, so it only fires when memory is actually over budget.
        self._idle_evict_timer = QTimer(self)
        self._idle_evict_timer.setSingleShot(True)
        self._idle_evict_timer.setInterval(2000)

        def _evict_on_idle():
            self._purge_renderer('post-interaction-idle')

        self._idle_evict_timer.timeout.connect(_evict_on_idle)
        self._idle_filter = _InputIdleFilter(
            self._mark_input, self._idle_evict_timer, self)
        QApplication.instance().installEventFilter(self._idle_filter)

        # Sustained-idle reclaim: the post-interaction timer is single-shot and only
        # re-arms on input, so a user who walks away gets exactly one purge and then
        # the renderer climbs unbounded (it filled all RAM in testing). This repeating
        # timer fixes that: every few seconds, if there has been no input for
        # _IDLE_RECLAIM_AFTER_S, attempt a purge. _purge_renderer is gated by the RSS
        # ceiling and rate-limited, so an idle-but-present user sees a reclaim only
        # every few minutes (when RSS climbs back over the ceiling), never mid-input.
        self._idle_reclaim_timer = QTimer(self)
        self._idle_reclaim_timer.setInterval(4000)
        self._idle_reclaim_timer.timeout.connect(self._maybe_idle_purge)
        self._idle_reclaim_timer.start()

        self.browser.setPage(page)
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)
        self.resize(1280, 800)

    def _renderer_rss_kb(self) -> int:
        page = getattr(self, '_page', None)
        pid = page.renderProcessPid() if page else None
        if not pid:
            return 0
        try:
            with open(f'/proc/{pid}/status') as f:
                for line in f:
                    if line.startswith('VmRSS'):
                        return int(line.split()[1])
        except OSError:
            return 0
        return 0

    def _purge_renderer(self, reason: str) -> None:
        """Forcibly purge renderer caches: the multi-GB pool that
        simulatePressureNotification does not touch on QtWebEngine (issue #106).

        Called only where a ~1s stutter is invisible: post-interaction mouse-idle,
        sustained idle (no input for a few seconds), focus-loss, and minimize.
        Gated by an RSS ceiling so light use never pays the stutter, and
        rate-limited so it cannot repeat back to back. The purge runs in the CDP
        executor so the socket I/O is off the Qt main thread. Logs the reason and
        the RSS delta on each purge; gated skips are intentionally silent (the
        idle timer would otherwise spam the log every few seconds).
        """
        import time
        rss = self._renderer_rss_kb()
        if rss and rss < _PURGE_RSS_CEILING_KB:
            return  # below ceiling — not worth the stutter
        now = time.monotonic()
        if now - self._last_purge < _PURGE_MIN_INTERVAL_S:
            return  # rate limit
        self._last_purge = now

        def _do():
            res = _cdp_call('Memory.forciblyPurgeJavaScriptMemory')
            after = self._renderer_rss_kb()
            print(
                f'[MEM] forcible purge ({reason}): '
                f'{"ok" if res is not None else "FAILED"} '
                f'RSS {rss} -> {after} kB (delta={rss - after:+d} kB)',
                flush=True,
            )
        _cdp_executor.submit(_do)

    def _mark_input(self) -> None:
        """Record the time of the latest user input (mouse or keyboard)."""
        self._last_input = time.monotonic()

    def _maybe_idle_purge(self) -> None:
        """Repeating sustained-idle reclaim. Purges only after the user has been
        idle for _IDLE_RECLAIM_AFTER_S; _purge_renderer adds the RSS-ceiling gate
        and rate limit, so this bounds memory on walk-away without stuttering an
        active user."""
        if time.monotonic() - self._last_input >= _IDLE_RECLAIM_AFTER_S:
            self._purge_renderer('sustained-idle')

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                # Reclaim renderer memory while minimized WITHOUT freezing the page.
                # The lifecycle freeze released compositor memory but left the web
                # content unresponsive to input after the Frozen->Active thaw — Qt
                # documents that a non-Active page can lose HTML input, says
                # "a visible page must remain in the Active state", and PyQt's
                # lifecycle transitions are unreliable (issue #109). The gated purge
                # frees memory without touching the lifecycle state; its ~1s stutter
                # is invisible while minimized.
                print('[LIFECYCLE] minimized — page kept Active, reclaim requested',
                      flush=True)
                self._purge_renderer('minimized')
        elif event.type() == QEvent.Type.WindowDeactivate:
            # Minimize fires both WindowStateChange and WindowDeactivate; only run
            # the focus-loss GC when actually losing focus (not minimizing).
            if not self.isMinimized():
                self._gc_focus_timer.start(500)
        elif event.type() == QEvent.Type.WindowActivate:
            self._gc_focus_timer.stop()
        super().changeEvent(event)

    def closeEvent(self, event):
        s = QSettings("odysseus", "odysseus")
        s.setValue("windowMaximized", self.isMaximized())
        # Only write geometry when windowed. On Wayland, saveGeometry() while
        # maximized records the maximized dimensions as the "normal" size, which
        # destroys the restore target on next open. Skipping the write when
        # maximized leaves the last good windowed geometry intact in QSettings.
        if not self.isMaximized():
            s.setValue("windowGeometry", self.saveGeometry())
        s.sync()
        self.browser.setPage(QWebEnginePage(QWebEngineProfile.defaultProfile(), self.browser))
        stop_server()
        event.accept()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    kill_zombies()
    start_server()

    app = QApplication(sys.argv)
    # Tell KDE which .desktop file owns this window so it groups with the
    # pinned taskbar entry and shows the correct icon instead of the X logo.
    app.setDesktopFileName("odysseus")

    # Named persistent profile — cookies, localStorage, and session data
    # survive between restarts. Without this the login is lost on every close.
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    profile = QWebEngineProfile(PROFILE_NAME, None)
    profile.setPersistentStoragePath(DATA_DIR)
    profile.setCachePath(CACHE_DIR)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    # App serves from localhost — HTTP cache is almost entirely idle but grows
    # without bound by default. Cap at 50 MB.
    profile.setHttpCacheMaximumSize(50_000_000)

    win = OdysseusWindow(profile)
    win.show()

    # Restore window state from previous session. show() must precede any
    # geometry calls so the window handle exists (required on Wayland).
    # When opening maximized we skip restoreGeometry() entirely: the stored
    # geometry blob was saved while windowed and is correct, but calling
    # restoreGeometry() before showMaximized() would make Qt treat the blob's
    # size as the maximized size rather than the restore target, repeating the
    # Wayland normal-geometry bug. We just maximize; Qt uses resize(1280,800)
    # from __init__ as the un-maximize restore target.
    _s = QSettings("odysseus", "odysseus")
    if _s.value("windowMaximized", False, type=bool):
        win.showMaximized()
    else:
        _geom = _s.value("windowGeometry")
        if _geom:
            win.restoreGeometry(_geom)

    sys.exit(app.exec())
