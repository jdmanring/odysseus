# Downloader System Audit — Known-Good Baseline and Defect Record

**Status:** living document. Started 2026-07-20 after a night of cascading failures.
**Purpose:** rebuild trust in the download stack from verified facts. Every claim here is
traceable to a commit, a log line, or a live probe — nothing is asserted from memory.
Update this document whenever a downloader defect is found, fixed, or verified.

---

## 1. The known-good baseline

The aria2c download system was **finished, verified, and working perfectly** as of mid-June 2026.
The finished state comprised:

- `tooling/aria2c_download.py` — aria2c launcher (URL resolution via `tooling/hf_url_resolver.py`,
  binary via `tooling/bin_manager.py`), `.aria2` sidecar resume, PID lock, `DOWNLOAD_OK` /
  `DOWNLOAD_FAILED` exit sentinels.
- The download card UI — per-file progress rows, auth pill, phase-gated banners
  (`data-dl-phase` CSS state machine), pause/resume/stop actions.
- Built across `bc5e46fe` (2026-06-08, per-file progress rows), `41a468c4` (2026-06-12,
  compact parser + auth pill), `b488f4a7` (2026-06-12, auth badge to header, per-file rows
  for parallel). Ancestry order: `bc5e46fe` → `41a468c4` → `b488f4a7` → `4f962b55`, so
  `4f962b55^` contains the complete finished stylesheet — this is the restoration source.

Provenance is settled: the card and stack are entirely this fork's work. Upstream `dev` has
zero occurrences of `data-dl-card`, `dl-done-banner`, `aria2c`, or `use_aria2c`.

**Everything that broke after this point was broken by later maintenance work in this repo,
not by the original design and not by upstream.**

## 2. How it broke — regression timeline

| When | Commit | What it did |
|------|--------|-------------|
| 2026-06-11 | `4f962b55` "css render performance pass" | Deleted 438 lines from `static/style.css`, including the **entire** `.dl-*` download-card stylesheet (~350 lines): phase-visibility rules, auth pill, banners. Both banners are always in the DOM; CSS shows exactly one per phase — without it the card showed "complete" + "failed" + progress simultaneously. |
| 2026-06-13 | `88e1e123` | Orphaned `_dl_base` → NameError on every aria2c run. |
| 2026-06-15 | `247a2a35` (labeled a basicsr fix) | Amputated the whole aria2c launch block. |
| 2026-06-22 | `b6f0f941` | Restored only the pre-flight, leaving a `use_aria2c` flag nothing read. |
| Jun 15 → Jul 19 | — | **Launcher silently dead (issue #146).** Every "aria2c" download actually ran the hf fallback. Because nothing rendered the card in anger, the CSS deletion also went unnoticed. This dormancy is why the damage wasn't caught for a month: the system wasn't failing loudly, it was disconnected. |
| 2026-07-19 | `a7e870f5` | Launcher restored. This put live traffic back onto code paths nothing had exercised in a month — the latent defects below then surfaced one by one, in production, in front of the person who built the system. |

## 3. Defect catalog

Each entry: symptom → root cause → evidence → fix → verification state.
All fix commits are on `develop` and cherry-picked to `feat/aria2c-downloader`
(wrapper fixes to `feat/qt-native-linux-app` / `feat/qt-native-windows-app`).

### D1. Launcher dead (issue #146)
- **Symptom:** downloads "worked" but never used aria2c; no card behavior matched the finished design.
- **Cause:** regression chain above (`88e1e123` → `247a2a35` → `b6f0f941`).
- **Fix:** `a7e870f5`. Wiring pinned by `tests/test_aria2c_launcher_wiring.py`.
- **Verified:** live E2E both platforms (Linux: two full downloads with `DOWNLOAD_OK`; Windows: 9.6 GiB GGUF complete).

### D2. Download-card stylesheet deleted
- **Symptom:** "Download Failed", "Download Complete", and live progress all shown at once; card unstyled; no auth pill.
- **Cause:** `4f962b55` deleted the `.dl-*` block. CSS is the card's phase state machine.
- **Fix:** `0f051fda` — restored byte-exact from `4f962b55^` (minus the dead `.managed-download-ui` block). Guard test asserts every class the JS template emits exists in the stylesheet.
- **Verified:** live, after D3 was also fixed (see below — the first verification attempt was defeated by D3).

### D3. Hard-coded stylesheet cache-buster
- **Symptom:** the (correct) CSS restoration appeared broken; card still unstyled after fix.
- **Cause:** `static/index.html` pins `style.css?v=...` with a hard-coded value. Any style.css change is **invisible to every client until the v-param is bumped.** Cost an hour of misdiagnosis and produced a false "fixed" claim.
- **Fix:** `bef1e1ca` bumped to `?v=20260719dlcard`.
- **Rule:** bump the v-param in the same commit as any style.css change.

### D4. Empty token became a literal `Bearer ` header
- **Symptom:** URL resolution silently degraded to the unauthenticated raw-API fallback ("Illegal header value").
- **Cause:** `--token ''` reached `HfApi(token='')`.
- **Fix:** `9004401d` — coerce `'' → None` in both launcher and `HfUrlResolver`. Guard test added.
- **Verified:** live (auth pill + sized file list on subsequent runs).

### D5. "Finished before finished" — loose success markers
- **Symptom:** card said done mid-download; state scrambled after renderer crash-reloads.
- **Cause:** success judged from `/snapshots/` and per-file `Download complete` markers — aria2c prints **both from its first progress tick** (`[*] Saving to: .../snapshots/...`). Three sites trusted them: the dead-session reconnect heuristic, the `_strongDone` finalizer, and the `_selfHealStaleTasks` skip-guard (which also permanently blocked recovery of a wrongly-done task). Tasks adopted from server state carry no `use_aria2c` flag, so payload-only gating was insufficient.
- **Fix:** `bef1ecfa`/`bef1e1ca` (reconnect path), then `7bfe963e` (all sites, via `_isAria2cRun()` = payload flag OR output fingerprint `[*] Using aria2c:`). aria2c success now requires the `DOWNLOAD_OK` exit sentinel everywhere; loose markers remain only for hf-CLI output, which has no sentinel.
- **Verified:** code-audited (subagent adversarial audit, P1-1/P1-2) + guard test. Not yet exercised by a live crash-reload cycle.

### D6. Renderer SIGSEGV: idle purge during active download
- **Symptom:** app crashed and reloaded mid-download (3× on 2026-07-19: exit=11 at 22:23:44, 22:37:08, 22:48:05 — `logs/wrapper_system.log`), each crash rescrambling card state.
- **Cause:** input-idle ≠ page-idle. During a download the user touches nothing, so idle timers fire `Memory.forciblyPurgeJavaScriptMemory` — but the renderer is repainting the card constantly; purging a busy renderer segfaults it. Each of the three crashes immediately followed a forcible purge.
- **Fix:** `a9a299b0` — busy-page gate in `qt_wrapper.py` + `windows_wrapper.py`: before idle-path purges, a CDP probe checks localStorage `cookbook-tasks` for a running/queued download or running serve. Genuine-pressure reasons (`psi-critical`, `low-memory`, `node-threshold`) are exempt. Fails open. Guard test parametrized over wrappers.
- **Verified:** deployed and running; no purge-adjacent crash since. Needs a long-download soak to call closed.

### D7. aria2c bash args escaped but not quoted
- **Symptom (latent):** any download dir containing a space → instant argparse failure; `--include *.gguf` bash-expanded in the tmux cwd.
- **Cause:** `_bash_squote` escapes embedded quotes but does **not** wrap the value; call sites used it bare. (The Windows PowerShell builder was already correct.)
- **Fix:** `7bfe963e` — all values wrapped in real single quotes at the call site. Guard test added.
- **Verified:** live download (Qwen3-8B-FP8) launched and completed through the quoted command path.

### D8. Background monitor killed itself at download launch
- **Symptom:** fresh download stuck at "Initializing" forever, log view empty, while the transfer ran perfectly in tmux.
- **Cause:** `_pollBackgroundStatus`'s first tick fires in the same instant as the download POST; the server's task list is still empty; the empty response hit the idle branch and ran `_stopBackgroundMonitor()` — permanently. Nothing restarts the monitor until the Cookbook tab is reopened.
- **Evidence:** access log shows exactly **one** `/api/cookbook/tasks/status` call after launch (06:11:32 UTC), then silence; live CDP probe showed leader heartbeat 250 s stale against a 15 s TTL.
- **Fix:** `50c5950c` — stop requires the **local** task list to be idle too.
- **Verified:** live — monitor restarted via CDP in the running page, polling resumed on the 10 s cadence, card healed to the true state.

### D9. Delete trusted HTTP 200
- **Symptom:** press delete → row animates away → model reappears on next visit.
- **Cause:** `/api/shell/exec` always returns HTTP 200; the real outcome is `exit_code` in the body. The client checked only `res.ok`, so a failed `rm` looked successful.
- **Fix:** `50c5950c` — client checks `exit_code` and surfaces stderr on failure.
- **Verified:** code-level; needs one live failed-delete to confirm the error surfaces.

### D10. Launch list served from a 6-hour client cache with no invalidation
- **Symptom:** Launch showed a deleted model as the only entry and neither of the two models actually on disk. (The visible, enraging one.)
- **Cause:** `_fetchCachedModels` renders from a localStorage scan snapshot (`cookbook_cached_models_scan_v1`, TTL 6 h). **Nothing invalidated it on mutation** — delete even re-rendered from the same stale cache. The server scanner was always correct; the UI never asked it.
- **Evidence:** live CDP dump of the running page's snapshot: 49 minutes old, containing exactly `cyankiwi/Llama-3.1-8B-Instruct-AWQ-INT4` (deleted) — precisely what the screen showed, while disk held `Qwen/Qwen3-8B-FP8` + `nvidia/Qwen3-30B-A3B-NVFP4` (both complete per direct scanner run).
- **Fix:** `ba54c281` — `_invalidateCachedModelScan()` dropped on delete success and at all three download-completion sites; delete refetches fresh.
- **Verified:** stale snapshot purged live; fix deployed both machines. Needs one full download→Launch and delete→Launch cycle to confirm end-to-end.

## 4. The staleness map — read this before touching the UI

The night's central lesson: **there are multiple caches between the disk and the pixels, and
every one of them lied at least once.** Any future "the UI shows the wrong thing" report
must be checked against ALL layers, in order:

| Layer | Location | Invalidation | Bit us as |
|-------|----------|--------------|-----------|
| Stylesheet | `index.html` hard-coded `?v=` pin | manual bump only | D3 |
| Module JS | served `no-cache` (`_RevalidatingStatic` in `app.py`) | revalidates per load; **running page keeps old code until reload** | crash-reload ran stale heuristics |
| Task state | localStorage `cookbook-tasks` | reconcilers (poll, self-heal) — which had their own bugs | D5, D8 |
| Poll loops | in-page intervals + leader election (`odysseus-cookbook-bg-leader`, TTL 15 s) | self-managed | D8 |
| Launch scan snapshot | localStorage `cookbook_cached_models_scan_v1`, TTL 6 h | **none before `ba54c281`** | D10 |
| Downloaded-dot set | `_cachedModelIds` in `cookbook-hwfit.js`, refreshed per server-switch | `refreshCachedModelIds` on download done | (adjacent; refreshed at done sites) |
| Server | `/api/model/cached` scanner, `/api/cookbook/tasks/status` | scans fresh per request (status endpoint short-circuits terminal-status tasks — relevant to D5 healing) | — |

**Rule:** when the UI contradicts the disk, dump the actual layer contents (CDP probe of the
live page beats reasoning about the code) before claiming anything is "fine."

## 5. Verified solid (adversarial audit, 2026-07-20)

A read-only audit tried to break the stack and could not, at: progress-parser vs real aria2c
output (including transient xet-CDN 403 lines, which are NORMAL — signed byte-range URLs
reject extra split connections, aria2c drops to CN:2 and completes); sentinel exclusivity
(exactly one of `DOWNLOAD_OK`/`DOWNLOAD_FAILED` per run); paused-state protection; sidecar
resume integrity (`--continue=true`, deterministic paths, no auto-renaming); PID lock;
input-validation/injection surface; the restored CSS phase machine.

## 6. Open items (known, accepted, not yet fixed)

From the audit, real but lower-stakes — fix from this list, not from fresh symptoms:

1. **Retry backend switch** (audit P2-2): if the aria2c pre-flight fails on a retry, the server silently reruns via hf into a different disk layout, orphaning partials. Should stay on aria2c or fail loudly.
2. **Pause during resolve is a lie** (P2-3): `C-c` during the resolving phase kills the resolver (exit 130 → `DOWNLOAD_FAILED`); the card claims "Paused". Gate Pause to the `downloading` phase.
3. **Auto-retry destroys the card** (P2-4): the `DOWNLOAD_FAILED` auto-retry path removes the task and creates a new card instead of updating in place (`replaceSessionId` not passed).
4. `_dlFileTracker` leaks entries for failed/stopped sessions; its loss on reload downgrades the reconnect-affordance check for aria2c tasks.
5. Stale `errorMsg`: banner text only refreshes on phase *change*; a second, different error in the same phase never displays.
6. Inline `style.display` set by the Pause handler briefly fights the phase CSS after Resume.
7. Accessibility: progress bars lack `role="progressbar"`/`aria-valuenow`; error banner lacks `role="alert"`; spinner lacks a label.
8. Sequential-mode parser regex in `cookbookRunning.js` is dead code.
9. `--minor-mc` V8 flag in wrapper `--js-flags` is unrecognized by current V8 (137 logged errors; harmless noise) — remove.
10. Bash `''`-sentinel args work only by truthiness; the PowerShell builder's omit-when-empty style is the robust pattern to converge on.

## 7. Required before this system is called "working" again

- [x] **Tooling-layer E2E cycle (Linux, 2026-07-20):** fresh download of a real repo through `aria2c_download.py` (exit 0, complete transcript captured as a test fixture) → scanner lists it → delete → scanner clears it. Exercises the quoted command path, tokenless resolution, and disk truth.
- [x] **Behavioral test harness:** `tests/js/downloader_behavior.test.mjs` runs the extracted parser/state functions against REAL captured aria2c transcripts (`tests/fixtures/`) — sentinel-only done, mid-run phases, xet-403-is-not-failure, aria2c-run detection incl. adopted tasks, and the monitor stop decision (D8's race, now a pure exported function `_shouldStopBackgroundMonitor`). Bridged into pytest via `test_js_behavioral_suite_passes`.
- [x] **Cache-buster made structural (D3 class closed):** `serve_html_with_nonce` rewrites every `/static/*?v=` pin to a content hash at serve time (`rewrite_asset_versions` in `src/app_helpers.py`; `tests/test_asset_version_rewrite.py`). A CSS/JS change now changes the URL automatically. Takes effect on next app restart.
- [ ] **UI-layer hostile sweep, both machines (needs restarted app):** download → watch card through every phase → reload mid-download → complete → appears in Launch → serve → delete → gone from Launch → re-download resumes. Each step checked against disk + logs, not belief.
- [ ] Soak one long download against the purge gate (D6) with idle timers firing.
- [ ] One deliberate failed delete to confirm D9's error surfaces.
- [ ] Close issue #146 only after the sweep passes (per fork rules: verified, not believed).

### D11. `/api/cookbook/resolve-gguf` endpoint amputated from develop (found 2026-07-20)
- **Symptom:** "No GGUF source is configured" for models that should auto-discover GGUF quantizations.
- **Cause:** the route (24 lines of `d3eeee9c`) was lost in the June restorations while the resolver library and the JS caller both survived — a partial amputation; every discovery call 404'd (server log confirms). Same failure family as D1.
- **Fix:** route restored verbatim from `fix/gguf-quality-scored`; guard test pins client caller + route + resolver method **together**. Takes effect on next app restart.
- **Verified:** guard suite green; live verification pending restart. A systematic sweep of all staged branches for further lost content is running; results will be appended here.

## 8. Process failures that made this worse (bind these)

1. **"Proof" claimed from the wrong vantage point, twice** (D3: verified CSS content but not delivery; D10: verified the scanner but not the UI's data source). Verify the path the user's eyes are on, end to end.
2. **Symptoms fixed serially when the class was visible.** After the first stale-data bug, the whole staleness map (§4) should have been swept at once.
3. **The original regressions were preventable at commit time.** A "perf pass" deleting 438 lines of live selectors and a "basicsr fix" amputating a launch block both needed a selector-liveness/caller check. The guard tests now exist; they were written after user-facing breakage, which is the most expensive ordering.
4. **A dormant subsystem is not a working subsystem.** The launcher was dead for a month and nothing noticed. The wiring tests now pin it; prefer a cheap always-on liveness assertion over discovering disconnection in production.
