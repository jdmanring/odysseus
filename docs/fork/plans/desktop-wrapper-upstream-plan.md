# Desktop Wrapper → Upstream Contribution Plan

**Goal:** Stage the fork's unified QtWebEngine desktop wrapper (Linux, macOS, Windows,
FreeBSD, OpenBSD) as upstream PR(s), retire the inherited browser/pystray launcher, and
win on technical merit — pre-empting every concern upstream's #976 reviewers raised so a
maintainer cannot reasonably reject it.

**Why we can win:** upstream ships only `launcher.py` (Windows-only: pystray tray +
`webbrowser.open()`, PR #976) and thin `.app`/shell launchers. It has **no native window,
no single-instance, no dock/tray lifecycle, no crash recovery, and nothing for
Linux/BSD/macOS-native**. Our system is a different, strictly superior architecture.

---

## Sequencing decision (senior call)

Do **not** open one giant 5-OS PR, and do **not** lead with Windows. Lead where upstream
has **nothing** and there is no competing code to bikeshed:

1. **PR 1 — Linux/BSD core (`qt_wrapper.py` + `qt_psi.py` + `qt_watchdog.py` + `build-linux-app.sh`).**
   The reference implementation. Establishes the architecture (native window spawns
   `uvicorn app:app` child, single-instance `QLocalServer`, close-to-tray, memory reclaim,
   software-render fallback) where upstream offers zero alternative. Smallest blast radius,
   least contention.
2. **PR 2 — FreeBSD + OpenBSD (`build-freebsd-app.sh`, `build-openbsd-app.sh`).** Extends the
   Linux core; upstream has nothing here either. Proves the "runs across the fleet" claim.
3. **PR 3 — macOS (`mac_wrapper.py`, `build-mac-app.sh`).** Supersedes upstream's thin `.app`
   shell with a native window + dock lifecycle.
4. **PR 4 — Windows (`windows_wrapper.py`, `build-windows-app.ps1`) + retire `launcher.py`.**
   The contentious one: directly supersedes #976. File it **last**, after PRs 1–3 have
   established the architecture's credibility, with the comparison matrix front-and-center.

Each PR is its own branch off `upstream-mirror`, cherry-picked to develop.

**Deletion is a second track, filed only after acceptance.** The PRs above are
strictly *additive* — they add our Qt wrapper *alongside* upstream's launcher,
never delete it. Deleting a maintainer's merged feature (#976) in the same PR
reads as hostile and auto-rejects. So: force acceptance of ours through the
comparison matrix first; *then*, once ours is merged and proven, file a
*separate* PR proposing removal of the browser launcher, argued on its own
merits. On our own fork the fallbacks are already retired (2026-07-23); this
two-track split is purely for how the change reaches upstream.

## Phases

- **Phase 0 — cleanup (DONE):** aria2c staged-branch convergence + stale-test corrections;
  full suite green except pre-existing non-wrapper items.
- **Phase 1 — retire the inherited launcher:** delete `launcher.py`, `Odysseus.spec`,
  `build-windows-portable.ps1`; make `windows_wrapper.py`/`build-windows-app.ps1` the sole
  Windows path; scrub references (`build-windows-portable.ps1` callers, docs, tests).
- **Phase 2 — completeness audit:** build the capability matrix (per-OS × per-capability:
  native window, single-instance, tray, close-to-tray, dock/taskbar identity, crash/hang
  recovery, memory reclaim, software-render fallback, provisioning). Identify and fill gaps
  so every target is genuinely complete, not just present.
- **Phase 3 — cross-platform verification (VMs, ONE AT A TIME; shut each down after):**
  | Target | Bench | How |
  |--------|-------|-----|
  | Linux | host + a virsh distro | build + launch, verify all capabilities |
  | FreeBSD | `virsh freebsd15` / `ssh freebsd` | build-freebsd-app.sh, launch, verify |
  | OpenBSD | `ssh openbsd` | build-openbsd-app.sh, launch, verify |
  | Windows | `virsh win11` / `ssh win11` | build-windows-app.ps1, launch, verify tray/single-instance |
  | macOS | `ssh macos` bench | build-mac-app.sh, launch, verify dock/close-to-tray |
  Record **machine-verified vs code-reviewed** per capability. Never claim a platform tested
  that wasn't booted.
- **Phase 4 — PR staging:** per the sequencing above; each branch off `upstream-mirror`,
  PR draft with the comparison matrix + explicit pre-emption of #976 concerns
  (no ASGI import side-effects, no GUI deps in base requirements, windowed-mode console
  suppression) plus the net-new wins (single-instance, dock/tray lifecycle, 5 OSes).
- **Phase 5 — verify (senior):** hostile audit of each PR draft (every claim traced to a
  recorded VM run), full suite, sign-off before the human files.

## #976 review concerns to pre-empt (must appear addressed in the PR)

1. Launcher logic inside `app.py` / import-time side effects → we spawn `uvicorn` as a child; `app.py` stays a pure server.
2. GUI lib (`pystray`/PyQt) in base `requirements.txt` → ours has none; GUI deps build-time only.
3. Windowed-mode console/stdout crashes → `pythonw` + `CREATE_NO_WINDOW` on every console child.
4. No tests for the frozen path → wrapper test suites (`qt_psi` behavioral, wrapper lifecycle static guards).
5. Frozen-path prerequisites → documented in `docs/dev/desktop-wrappers.md`.

## Risks / honesty gates

- macOS/Windows/BSD verification depends on bench availability; label each capability
  machine-verified vs code-reviewed and never overclaim.
- The wrapper's richer architecture carries self-inflicted risks (QtWebEngine renderer
  segfault on CDP purge; `/proc`,`/sys`,`QtDBus` non-portability) — already guarded
  (`_PROC_RSS_OK`, `_HAS_QTDBUS`, `_linux_software_render()`); the audit must confirm each
  guard fires on the non-Linux targets.
