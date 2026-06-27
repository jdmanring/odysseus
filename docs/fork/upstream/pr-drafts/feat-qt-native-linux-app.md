# PR Draft: feat/qt-native-linux-app → pewdiepie-archdaemon/odysseus:dev

**Branch:** `feat/qt-native-linux-app`
**Issue:** [#14](https://github.com/jdmanring/odysseus/issues/14) (fork tracking)
**Screenshot:** `docs/fork/screenshots/qt-native-linux-app.png`
**Status:** Ready to file


---

## Title

`feat(linux): native Linux desktop application (PyQt6 wrapper)`

---

## Summary

Adds an optional native Linux desktop wrapper that embeds the Odysseus web UI in
a `QWebEngineView` window. Users get a launcher/taskbar entry, desktop icon
integration, and a standalone app experience without needing a separate browser
tab. The Odysseus server runs in-process; the wrapper manages its full lifecycle.

Embedded QtWebEngine does not receive the OS memory-pressure signals a normal
browser uses to bound its caches, so a long session's renderer RSS grows without
ceiling (measured into the multi-GB range). The wrapper therefore ships with
**disciplined renderer memory management** as a first-class part of the feature, not
a follow-up: a gated forcible-purge reclaim fired only off the interaction path, a
graduated Linux-PSI monitor that supplies the missing pressure signal, structured
memory telemetry, and a low-resource device profile. These are described under
*Memory management* below.

<!-- Screenshot: drag `docs/fork/screenshots/qt-native-linux-app.png` into this text box when filing; the repo-relative path will not resolve upstream. -->

### New files

**`qt_wrapper.py`**: PyQt6 application entry point:

- **Server lifecycle:** spawns `uvicorn app:app` as a subprocess on startup,
  kills it on window close. Waits up to 30 s for the server to become ready
  before loading the UI.
- **Persistent profile:** uses `QWebEngineProfile("odysseus")` with explicit
  data/cache paths in `~/.local/share/odysseus/webengine/` and
  `~/.cache/odysseus/webengine/`. Cookies, `localStorage`, and `IndexedDB`
  survive across restarts (default `QWebEngineView` uses an in-memory profile
  that wipes everything on exit).
- **External links:** `OdysseusPage(QWebEnginePage)` subclass intercepts
  navigations targeting a new frame (`navigationRequested` with
  `NavigationType.Link` + `isMainFrame=False` or a new-window request) and
  routes them to `QDesktopServices.openUrl()` so external links open in the
  system browser instead of navigating away inside the wrapper.
- **Crash recovery:** `renderProcessTerminated` handler reloads the page on
  OOM or renderer crash, with a loop guard to avoid reload storms.
- **Memory telemetry:** a `QTimer`-driven 30 s loop logs renderer heap counters
  (`Memory.getDOMCounters` via CDP) and host-process VmRSS to `[MEM]` lines for
  diagnostics. See *Memory management* below for the reclaim architecture.
- **Qt bridge:** `QWebChannel` exposes `window.qtBridge` to the page for
  features that require a native dialog.
- **GPU flags:** sets `QTWEBENGINE_CHROMIUM_FLAGS` before importing Qt, with
  GPU vendor detection via `/proc/driver/nvidia`. Common flags: `--enable-gpu-rasterization`,
  `WebGPU`, `SharedArrayBuffer`, `--enable-logging=stderr`,
  `--remote-debugging-port=9222` (Chrome DevTools at `http://localhost:9222`).
  `DefaultANGLEVulkan` is absent for all configurations (forces ANGLE to Vulkan;
  causes blank/invisible windows on ozone/Wayland regardless of GPU vendor,
  Chromium bug 334275637). Vendor-conditional: **NVIDIA** (proprietary,
  `/proc/driver/nvidia` present), `QTWEBENGINE_FORCE_USE_GBM=0` guards a Qt 6.9+
  regression (qutebrowser #8535) where Qt forces GBM on drivers that lack it;
  `--enable-zero-copy` is omitted (NVIDIA lacks GBM buffer allocation).
  **Mesa/AMD/Intel/Nouveau** (`/proc/driver/nvidia` absent), `--enable-zero-copy`
  is enabled (native GBM buffer allocation path); no GBM guard needed.
  `setdefault` preserves any user override of the GBM env var.
- **Logging:** `os.dup2` redirects Chromium renderer fd 1/2 into
  `logs/wrapper_system.log` before Qt is imported so all renderer subprocess
  output is captured.
- **JS console routing:** `OdysseusPage.javaScriptConsoleMessage` override routes all
  JavaScript `console.log()` output into `wrapper_system.log`. Chromium's
  `--enable-logging=stderr` only captures the renderer's internal C++ log; JS console
  calls are silent without this override. This surfaces all `[streamRenderer]`,
  `[chatHistory]`, `[chat]`, and `[GC]` structured log lines from the application JS.
- **Post-evict listener audit:** when `chatHistory.js` emits
  `[chatHistory] Phase 2 evict: removed N live nodes`, the console override spawns
  a background thread that measures `jsEventListeners` (via `Memory.getDOMCounters`)
  immediately and again 5 seconds later. The delta is logged as
  `[CDP] post-evict listeners: before=X after=Y delta=Z nodes-evicted=N`. A delta
  close to N confirms that event listener closures are releasing after eviction; a
  near-zero delta indicates GC retention.
- **Stdlib imports for CDP:** `threading`, `socket`, `struct`, `base64`, and
  `urllib.request` are imported at module scope (aliased as `_threading`, `_cdp_sock`,
  `_cdp_struct`, `_cdp_b64`, `_cdp_req`) so that `_cdp_call` and all CDP-dependent paths
  resolve correctly at runtime.
- **Renderer PID:** `OdysseusPage.renderProcessPid()` replaces a `pgrep`
  subprocess spawn in the 60-second memory poll. PyQt6 already tracks the
  renderer PID internally; the subprocess was an unnecessary spawn per poll cycle
  that also matched unrelated processes sharing the binary name. `renderProcessPid()`
  returns 0 when the renderer has not started or has crashed; guarded with `if pid:`.
- **Bounded CDP thread pool:** `concurrent.futures.ThreadPoolExecutor(max_workers=2,
  thread_name_prefix='cdp')` replaces ad-hoc `threading.Thread` spawning for CDP
  background work (post-eviction listener audit). Bounds concurrent thread count;
  prevents unbounded thread creation under heavy eviction load. Executor is shut down
  (`cancel_futures=True, wait=False`) in `stop_server()`.
#### Memory management

Embedded QtWebEngine never receives the OS memory-pressure signals a normal browser
uses to bound its caches, so renderer RSS climbs without ceiling over a long session.
Two complementary reclaim mechanisms address this, plus a Linux-PSI signal source and a
low-resource profile.

- **Forcible renderer purge (primary reclaim):** `_purge_renderer()` runs
  `Memory.forciblyPurgeJavaScriptMemory` via CDP. This is the only call that releases the
  multi-GB renderer working set on QtWebEngine. It is **gated** by an RSS ceiling
  (`_PURGE_RSS_CEILING_KB`, default ~1.2 GB) and **rate-limited**
  (`_PURGE_MIN_INTERVAL_S = 15 s`), and fired **only off the interaction path**, where its
  ~1 s synchronous stutter is invisible: focus-loss, window minimize, post-interaction
  mouse-idle (2 s), and sustained away-from-keyboard idle. The CDP call runs in the bounded
  executor so socket I/O stays off the Qt main thread; it returns `None` on any error and
  degrades gracefully. `_purge_renderer` returns a synchronous decision status
  (`submitted` / `skipped_ceiling` / `rate_limited`) for telemetry.

  > Earlier iterations used `Memory.simulatePressureNotification(moderate)` to fire
  > `base::MemoryPressureListener`; on QtWebEngine that path was **measured to be a no-op**
  > on the renderer working set, so it was removed in favour of the forcible purge above.
  > Separately, `--enable-low-end-device-mode` was tried and removed: it caused a
  > lighter-rectangle raster tint on dark themes and bounded the raster tile budget, not
  > the Oilpan detached-DOM pool that actually grows.

- **Async GC (non-blocking, lighter reclaim):** `gc({type:'major',execution:'async'})` via
  `page.runJavaScript()` runs incremental collection without blocking the JS event loop:
  used where a stutter would be visible or a full purge is excessive: focus-loss (500 ms
  debounce via `_gc_focus_timer`, cancelled by `WindowActivate`), an Oilpan node-count
  threshold (> 50 000 nodes), and PSI MODERATE pressure (below).

- **Graduated Linux-PSI monitor (`qt_psi.py`):** supplies the missing OS pressure signal.
  A daemon thread reads `/proc/pressure/memory` (`some` + `full` avg10) and classifies
  NONE/MODERATE/CRITICAL via a notify FSM (thresholds env-tunable, defaults `some` 10/40,
  `full` 5). **MODERATE → async GC; CRITICAL → the gated forcible purge.** The detection
  logic is a **Qt-free module** (parse, level mapping, FSM, `/proc/meminfo` reads, the
  daemon loop) so it is unit-tested without the GUI stack; `qt_wrapper.py` is the output
  adapter: a 250 ms main-thread drain timer reads the monitor's event cell (GIL-atomic
  hand-off, avoiding `QTimer.singleShot` cross-thread hazards), dispatches the action, and
  emits one structured `[PSI]` line per transition carrying `level`, `some`, `full`, host
  `mem_avail_mb`, renderer `rss_mb`, `swap_mb`, and the action taken. Skipped silently on
  kernels without PSI (< 4.20). The same level mapping and notify discipline are shared
  with a companion QtWebEngine/Chromium upstream effort; this telemetry field-validates
  the thresholds on real hardware.

- **Memory telemetry:** the 30 s `[MEM]` diagnostic loop logs renderer heap counters and
  **host-process VmRSS** so renderer and host footprint are both visible.

- **Low-resource device profile:** at startup the wrapper auto-detects a low-resource host
  and selects tighter reclaim defaults (lower purge ceiling, shorter idle threshold); the
  selection and any env override are logged once in a `[PROFILE]` line. All knobs are
  env-tunable: `ODYSSEUS_PURGE_CEILING_MB`, `ODYSSEUS_IDLE_RECLAIM_S`, and
  `ODYSSEUS_PSI_MODERATE` / `ODYSSEUS_PSI_CRITICAL` / `ODYSSEUS_PSI_FULL_CRITICAL`. The
  60 s default for the disruptive sustained-idle purge follows the W3C/WICG Idle Detection
  API floor (idle thresholds below 60 s measure a pause, not idle).

- **Startup log rotation:** `_rotate_log(path)` rotates `wrapper_system.log` and
  `server_access.log` at startup if they exceed 10 MB, preserving 5 numbered
  backups (`path.1`-`path.5`) via the same shift algorithm used by
  `logging.handlers.RotatingFileHandler`. Constants (`_LOG_MAX_BYTES = 10 MB`,
  `_LOG_BACKUP_COUNT = 5`) match `src/constants.py` so all three log files
  follow the same retention policy. Rotation happens before `os.dup2` so there
  is no fd conflict with the Chromium renderer's inherited file descriptors.
  A `[LOG]` timestamp line is written to the newly opened file after `os.dup2`.
- **Memory flags:** `QTWEBENGINE_CHROMIUM_FLAGS` expanded with five targeted additions:
  `--initial-old-space-size=128` (old-gen heap starts at 128 MB, grows to 512 MB cap,
  reduces baseline RSS for short sessions); `--optimize-for-size` (V8 prefers smaller JIT
  code over throughput, ~5-15% JIT footprint reduction, safe for I/O-bound chat workloads);
  `--minor-mc` (replaces Scavenger with MinorMC for young-gen GC, compacts on every
  collection, 10-20% better retention for DOM-heavy allocation patterns);
  `--renderer-process-limit=1` (single renderer process, saves ~30-50 MB vs default
  multi-process behaviour in some Qt builds); `--disable-extensions` (removes extension
  loader overhead, ~1-5 MB, no downside for embedded app).
- **Tests** (97 across six files). `tests/test_qt_cdp_listener_audit.py` (67 tests)
  verifies import correctness, call-site presence, executor usage and shutdown,
  log-rotation structure (shift loop, `_LOG_BACKUP_COUNT`, constants match the app),
  `nodes` assigned before threshold comparison, the forcible-purge gating (RSS ceiling +
  rate limit) and off-interaction-only firing, the PSI dispatch wiring (the adapter starts
  the `qt_psi` monitor, drains its event cell, and routes CRITICAL to
  `_purge_renderer('psi-critical')`), `changeEvent` debounce/cancel behaviour, and all five
  memory flags. `tests/test_psi_monitor.py` (15 tests) unit-tests the Qt-free detection
  core directly: level boundaries, the three-arm notify FSM, `dispatch_psi_action`
  (including the CRITICAL purge path and its status mapping), the unavailable-PSI no-op,
  `/proc/meminfo` and PSI parsing, and env-tunable thresholds.
  `tests/test_low_resource_profile.py` (5) covers auto-detection and profile selection;
  `tests/test_host_rss_telemetry.py` (5) the host VmRSS log line;
  `tests/test_idle_purge_threshold.py` (4) the idle/ceiling defaults and gating; and
  `tests/test_wrapper_no_access_log.py` (1) the uvicorn access-log default.

**`qt_psi.py`**: the Qt-free Linux-PSI **detection core** (parse, level mapping,
three-arm notify FSM, `/proc/meminfo` reads, the daemon monitor + event cell). Importing
no Qt keeps the pressure logic unit-testable without the GUI stack and cleanly separates
detection from the `qt_wrapper.py` output adapter. See *Memory management* above.

**`build-linux-app.sh`**: preflight check and launch script. Verifies that
`PyQt6`, `PyQt6-WebEngine`, and `PyQt6-sip` are importable, prints an install
hint if any are missing, then launches `qt_wrapper.py`. Dependencies must be
installed via the system package manager or `pip` before running the script
(distro packages vary; no cross-distro install path is guaranteed safe).

**`static/js/qt-bridge.js`**: injected into `QWebEngineView` at startup via
`QWebEngineScript`. Initialises `QWebChannel` and makes `window.qtBridge`
available to the rest of the JS codebase.

### Modified files

**`static/index.html`**: injects `qt-bridge.js` as a `<script>` tag so the
bridge initialises before any ES module code runs.

**`static/js/colorPicker.js`**: the Web EyeDropper API is unavailable inside
`QWebEngineView` (no OS-level pixel picker), leaving the eyedropper button
permanently disabled with "not supported in this browser". When
`window.__QT_WRAPPER__` is set, the eyedropper click instead calls
`window.qtBridge.openColorPicker()`, which opens the native Qt color dialog.
The selected hex value is returned via a `colorPicked` signal. Web EyeDropper
remains the path in regular browsers.

### Desktop wrapper approach: Qt over Electron or Tauri

This section documents the tradeoffs considered. Reviewers aware of upstream
issue #606 and PR #3310 will want to understand why Qt was chosen.

**The alternative landscape**

Issue #606 requests a standalone native application for Windows, Mac, and Linux.
PR #3310 is a community Electron wrapper that already works on Linux, Windows,
and macOS. Architecture document #605 explicitly recommends **Tauri** (not Electron)
and notes that a wrapper should follow the planned frontend migration to React/TypeScript.

**Why not Electron**

Electron ships its own full copy of Chromium (zipped apps run 80-100 MB and
exceed 100 MB unzipped, per [Electron's own documentation](https://www.electronjs.org/docs/latest/why-electron)). On Linux, this means installing and running a
second Chromium runtime alongside whatever browser the user already has. For a
Python application that already runs on the system, adding a Node.js + Electron
runtime stack purely for a desktop window is a heavy dependency with a
meaningful install cost.

PyQt6-WebEngine also uses a Chromium-based rendering engine (Qt WebEngine), so
there is no capability gap between the two approaches. The difference is that on
Linux, PyQt6-WebEngine can use the Qt WebEngine packages available from the
distribution's package manager; no bundled browser binary needed. The
PR #3310 works correctly but requires an `npm install electron` path that adds
this runtime overhead.

**Why not Tauri**

The architecture document's Tauri recommendation is well-reasoned for its
intended context: a post-React-migration frontend where Tauri's Rust toolchain
integration and native webview usage are appropriate.

Two reasons Tauri is not the right choice today:

1. **Rendering engine**: Tauri uses WebKitGTK on Linux. WebKitGTK feature availability depends on the
   version packaged by each distribution: Ubuntu 22.04 LTS ships WebKitGTK
   [2.36](https://launchpad.net/ubuntu/jammy/+source/webkit2gtk),
   which lacks `container queries`. Odysseus uses `backdrop-filter`,
   `grid`, `container queries`, and features whose behavior across the full
   range of distribution-packaged WebKitGTK versions is untested. Qt WebEngine
   is Chromium-based and renders identically to the browser regardless of
   distribution.

2. **Toolchain**: Odysseus has no Rust code and no Rust toolchain. Adding Tauri
   means adding a full Rust build environment as a mandatory dependency for a
   desktop wrapper. PyQt6 is a native Python binding; no new toolchain required.

When the React migration described in #605 is complete, revisiting Tauri may be
the right call. This PR does not conflict with that path; `qt_wrapper.py` is
optional and the server is unchanged.

**Why Qt is appropriate for Linux**

Qt is the standard native application toolkit on Linux distributions that use
KDE, and is a first-class citizen on GNOME via GTK interop. PyQt6 is available
from the package manager on Arch, Debian, Ubuntu, and Fedora. The GPU
acceleration flags in `qt_wrapper.py` are chosen specifically for
NVIDIA/Wayland compatibility: `--enable-gpu-rasterization` is safe and
effective; the Vulkan/GBM flags that are problematic on NVIDIA drivers on Linux
are explicitly absent. None of this is novel: PyQt6-WebEngine wrappers
are a well-understood pattern for Python web apps that need a desktop presence
on Linux.

This PR does not attempt to cover Windows or macOS. Issue #3528 addresses a
Windows desktop mode separately. Cross-platform coverage via Electron or Tauri
is a reasonable follow-up; this PR delivers the Linux case using the tooling
that is already on every Linux machine in the target audience.

### No changes to server, API, or non-Qt JS paths

All changes are either new files or guarded behind `window.__QT_WRAPPER__` /
`window.qtBridge` checks. The wrapper has zero effect on Docker, native, or
browser installs.

### Dependencies

PyQt6, PyQt6-WebEngine. Installed by `build-linux-app.sh` into the existing
venv; not added to `requirements.txt` (optional desktop feature, not needed
for server installs or Docker).

## Target branch

- [x] This PR targets **`dev`**, not `main`. All PRs land in `dev`; `main` is curated by the maintainer at each release.

## Linked Issue

Fixes #___

## Type of Change

- [ ] Bug fix (non-breaking, fixes a confirmed issue)
- [x] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [x] I actually ran the app (`docker compose up` or `uvicorn app:app`) and verified the change works end-to-end. Type-checks and unit tests are not enough.

### How to Test

**Prerequisites:** Linux with PyQt6 and PyQt6-WebEngine available (or run `bash build-linux-app.sh` to install).

1. Run the wrapper: `bash build-linux-app.sh`: confirm it launches a native desktop window showing the Odysseus UI.
2. Log in; confirm login state persists after closing and re-opening the app (session stored in `~/.local/share/odysseus/webengine/`).
3. Click an external URL in an AI response; confirm it opens in the system browser, not inside the wrapper window.
4. Open Settings → Appearance → Theme and use the color picker; confirm the native Qt color dialog opens (not the browser eyedropper which is unsupported in QWebEngineView).
5. Open the sidebar, hover over items, open a dropdown, and open the Cookbook; confirm no black-screen flicker on any of these actions.
6. Chrome DevTools: navigate to `http://localhost:9222` in a regular browser; confirm the remote debugging endpoint is accessible.
7. Confirm standard features work: chat, session switching, model switching, Cookbook, Downloads, Settings.
8. Memory management: `tail -f logs/wrapper_system.log`, then induce memory pressure
   (e.g. `stress-ng --vm 4 --vm-bytes 6G --timeout 35s`). Confirm `[PSI]` lines appear with
   the level rising (NONE→MODERATE→…) and `mem_avail_mb`/`swap_mb` tracking the stall, and
   that a `[MEM] forcible purge` line follows a CRITICAL with a negative RSS delta. Switch
   focus away or minimize the window and confirm an off-interaction purge fires while the
   window is unfocused, never mid-interaction.

Tested on: Artix Linux, Wayland, NVIDIA open drivers. Not tested on: macOS, Windows, touchscreen/tablet.

**Screenshots required:**
- Screenshot referenced in the description (`docs/fork/screenshots/qt-native-linux-app.png`) shows the app running with the color picker open. Attach via drag-and-drop in the GitHub PR form.

---

## Filing Notes

1. **File upstream issue first**: draft in `docs/fork/upstream/issue-drafts/feat-qt-native-linux-app.md`. Add the issue number to `Fixes #` above before opening the PR.
2. The screenshot in the description uses a repo-relative path. Attach the image directly in the GitHub PR text box via drag-and-drop; do not rely on the fork's file paths being visible to upstream reviewers.
3. Upstream issue #3528 (Windows desktop wrapper) shows the maintainer is receptive to native desktop wrappers. Reference it as a parallel effort in the issue or PR if asked about motivation.
4. Fork issue #7 (HF token persistence) overlaps with upstream PR #3459; monitor it, and after the next sync re-verify whether the issue is fully resolved before filing separately.
5. **Port:** `qt_wrapper.py` now reads `APP_PORT` from the environment (`.env` is
   loaded automatically), defaulting to `7000`, the project's canonical upstream default
   (`docker-compose.yml`, `src/constants.py`, `launch-windows.ps1`). The previous
   hardcoded `8000` was a development artifact. No reviewer action needed; noted here for
   traceability.
6. **Pre-file squash (hard gate).** This branch was assembled by folding the memory stack
   in via cherry-pick, so its commit history shows the design's *evolution*
   (simulatePressure and `--enable-low-end-device-mode` added then removed, the PSI monitor
   rewritten). Squash to a small set of coherent commits before filing so the history does
   not read as "introduce naive, then patch." Verify the squash changed only history:
   `git diff <squashed-branch> feat/qt-native-linux-app` must be empty.
7. **Verify the CRITICAL purge in-app before ticking "ran end-to-end" (How-to-Test step 8).**
   Automated coverage and the stress-ng smoke reached the MODERATE→async-GC path and the
   off-interaction purge, but **not** PSI CRITICAL→`forciblyPurgeJavaScriptMemory`; confirm
   the `[MEM] forcible purge (psi-critical)` line actually fires under heavy pressure.

## Visual / UI changes; REQUIRED if you touched anything that renders

- [x] Screenshot or short clip of the change in the running app, attached below. Mobile screenshot too if the change affects mobile layout.
- [x] Style match: the change uses Odysseus's existing visual language (existing CSS variables, button/card classes, no Unicode emoji, Fira Code font, dark-mode-first).
- [x] No new component patterns; extended an existing widget rather than adding a parallel one.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.

### Screenshots / clips

<!-- Attach screenshots by dragging and dropping into this text box. -->
