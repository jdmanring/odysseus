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
11. **Auth pill is a capture race** (found 2026-07-20): the `[*] HF auth:` lines print once at the head of the launcher output, but the status poll keeps only the last 500 pane lines — a fast single-file GGUF download scrolls the header out before the first capture and the pill never renders. Robust fix: render from the task payload (the client knows whether it sent a token) as fallback when the lines are gone. The pill code itself is identical to the staged branch — not a regression.
12. **Transient "stopped" badge at download launch** (2026-07-20): a download card can briefly show "stopped" (status `error`) in the poll/adoption race before output flows, then self-corrects. Cosmetic but alarming; root-cause the exact error-status site (candidates: `_taskBadge` on adopted status, poll error paths at cookbookRunning.js ~3888/~4326) and suppress the flash.

### Design decisions (2026-07-20, settled — do not relitigate without new evidence)
- **No hub blob/symlink layout for aria2c.** Considered and rejected: blobs buy revision dedup (worthless for the download-one-snapshot-and-serve use case) and cross-tool resume interop (moot once retries pin the backend). Against them: symlink degradation to copies on Windows (double disk on the most disk-constrained bench), more moving parts, and losing the current identical-on-every-OS layout. Direct-to-snapshots stays. The real fix for the layout-mismatch class is pinning the backend across retries (P2-2).
- **Gated repos are routed around, not fought** (2026-07-20, user-mandated). Pre-flight 1-byte range probe detects the gated signature (public file list, 401 content) before aria2c runs; the launcher reroutes to the best scored GGUF source at the Q6 reliability floor (UD-Q6_K_XL > Q6_K_L > Q6_K > Q8_0). This does NOT reopen D13/#148: every candidate is provenance-verified as a quantization of the SAME model by the relatedness filter, and the reroute is printed loudly (`REROUTED: orig -> new`) with files landing under the real repo's identity — the banned thing was *unrelated* substitution *silently*. Network errors never reroute. No GGUF source → fail with ungated non-GGUF suggestions (`find_community_quants`, provenance-filtered).
- **hf_transfer is removed, permanently** (issue #36; develop `6803ded1`). It crashes near the end of large files at high throughput. aria2c is the fast path; the hf fallback always runs the plain Python downloader. `test_hf_transfer_is_structurally_dead` makes reintroduction a test failure, not a review judgment call. Upstream: folded into `feat/aria2c-downloader` — the PR's story IS "replace hf_transfer with aria2c" (issue #36's own title), and the removal is what makes the replacement complete. The fallback the PR leaves upstream is their own plain Python downloader, which their comments already concede is the reliable path.

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

### D12. `qt-bridge.js` script tag amputated from `index.html` (found 2026-07-20, branch sweep)
- **Symptom:** `window.qtBridge` undefined on the page; native color-picker support in `colorPicker.js` silently degraded to the HTML fallback.
- **Cause:** the tag was lost in `9b469344` (June 20) — a *third* index.html restoration commit beyond the two previously known (`247a2a35`, `b6f0f941`), so the silent-loss window is wider than first mapped. Same partial-amputation family as D1/D11: the library file and its consumer both survived; only the wiring line died.
- **Fix:** tag restored (`80d9a09b`) plus `tests/test_index_script_wiring.py`, which asserts the qt-bridge tag is present **and** that every local `<script src>` on the page resolves to a real file — closing the whole script-tag-amputation class, not just this instance. Takes effect on next app restart / page reload.

### D13. GGUF resolver substituted a completely unrelated model ([#148](https://github.com/jdmanring/odysseus/issues/148), found 2026-07-20)
- **Symptom:** a download of `tiny-random/qwen3-next-moe` fetched 7.9 GB of `mradermacher/Qwen3-MOE-2x6B-ST-The-Next-Generation-II-FreakStorm-12B-i1-GGUF` — a different model entirely, not a quant of the requested one. The card was titled with the *requested* model, so the swap was invisible until the weights were on disk.
- **Cause:** `find_gguf_sources()` validated only that candidates contain GGUF files, never that they derive from the requested model. `_probe_gguf_repo()` fetched the `base_models` metadata — the exact field for this — and used it only as a cosmetic console flag. Auto-selection was console-log-only.
- **Fix:** relatedness filter (`_is_quant_of`: base_models metadata match, or full normalized base-name containment in the candidate repo name); no qualifying candidate → empty → the honest "No GGUF source" path. Auto-select now surfaced in a visible toast. `bf51d93e` on `fix/gguf-quality-scored`, cherry-picked to develop (`e5b41dcc`).
- **Verified:** live both directions — incident model now returns 0 sources; Llama-3.1-8B still resolves 14 genuine quants, bartowski top. 9 new tests with the incident as recorded fixture (`tests/test_gguf_relatedness.py`). Takes effect on next app restart (server caches the imported module).

### D14. HW-Fit fabricated a Q4_K_M/llama.cpp identity for GGUF-less safetensors models ([#149](https://github.com/jdmanring/odysseus/issues/149), found 2026-07-20)
- **Symptom** (screenshot `screenshots/dspark.png`): a BF16 safetensors research repo rendered as QUANT Q4_K_M / MODE llama.cpp; Run used the wrong engine, Download took the GGUF gate and errored "No GGUF source" for a directly downloadable repo.
- **Cause:** `services/hwfit/fit.py` single-GPU default rated every non-prequantized model at a hypothetical Q4_K_M and emitted it as the row's `quant`; client `_detectBackend` treated any Q-tier label as GGUF proof. Upstream code, upstream design flaw.
- **Fix:** `1aa7a4fe` — server defaults to the GGUF ladder only with real GGUF evidence, otherwise native precision (BF16 → vLLM); rows expose `format`/`is_gguf`; client llamacpp branch requires evidence when format is safetensors. 4 server tests (incident as fixture) + node behavioral test.

### D15. Scan rated an unservable research checkpoint PERFECT ([#150](https://github.com/jdmanring/odysseus/issues/150), found 2026-07-20)
- **Symptom:** `Qwen3DSparkModel` (no inference code exists in any engine) listed as PERFECT; user downloaded 2.6 GB and got vLLM's architecture rejection at launch.
- **Cause:** "fit" was purely a VRAM calculation; the collection ingester never recorded architectures (`architecture: ""`).
- **Fix:** servability gate — ingest hydrates each repo's architecture from the HF models API (cached); `arch_looks_servable()` gates on the standard task-class suffixes; unservable rows pin to no_fit and render a "research" label with the architecture in the tooltip; unrecorded architectures are never judged. Local catalog cache backfilled for both dspark entries. 3 tests.
- **Open residue:** serve diagnosis could recognize vLLM's "architectures not supported" wall and say "unsupported architecture" plainly (offered, not yet requested).

### Branch-sweep outcome (2026-07-20)
The sweep's question was develop-side only: did every staged fix actually land on develop? Two live losses were found (D11, D12), both now restored. Two branches needed nothing cherry-picked because develop already carries their content in evolved form — that says NOTHING about the branches themselves, which are staged upstream PRs and stay:
- `fix/dom-oom-streaming-throttle` (#64) — develop has the equivalent fixes (`_throttledRenderStream()`, thinking textContent, `StreamRenderer` teardown). Upstream still has the O(n²) thinking `innerHTML` render and no throttle (verified against upstream-mirror 2026-07-20); the staged PR stands unchanged.
- `fix/css-contain-paint-transparent-rendering` (#93) — its chat-history hunk is on develop; its sidebar hunk was deliberately reverted the same day (`03517911`: containment creates a stacking context that breaks the sidebar box-shadow in the Qt compositor), so develop's `test_sidebar_no_contain` is the current truth and the sidebar hunk must NOT be re-cherry-picked. The branch needs **rework before filing** (chat-history-only + tests adjusted; the sidebar finding becomes PR-narrative evidence), not deletion.

## 8. Process failures that made this worse (bind these)

1. **"Proof" claimed from the wrong vantage point, twice** (D3: verified CSS content but not delivery; D10: verified the scanner but not the UI's data source). Verify the path the user's eyes are on, end to end.
2. **Symptoms fixed serially when the class was visible.** After the first stale-data bug, the whole staleness map (§4) should have been swept at once.
3. **The original regressions were preventable at commit time.** A "perf pass" deleting 438 lines of live selectors and a "basicsr fix" amputating a launch block both needed a selector-liveness/caller check. The guard tests now exist; they were written after user-facing breakage, which is the most expensive ordering.
4. **A dormant subsystem is not a working subsystem.** The launcher was dead for a month and nothing noticed. The wiring tests now pin it; prefer a cheap always-on liveness assertion over discovering disconnection in production.
5. **"Fixed" claimed before the fix was proven, repeatedly (2026-07-21).** The stale-cache symptom was hand-patched three times before the service-worker update mechanism was diagnosed; a partial spot-check of one JS file was reported as "deployment current" while the file that renders the card was stale; the Windows app was asserted "stopped" without checking (it was running, in fact duplicated). Each was the same failure as D3/D10 — a claim ahead of end-to-end verification from the user's vantage. The token fix (D19) was only trustworthy once `resolve_snapshot_urls` returned a real file list on the actual bench.

### D16. The premature-"finished" family, finally closed (2026-07-20, three layers)
- **Server cache probe** (`routes/cookbook_output.py`): judged completion by populated `snapshots/` + no `blobs/*.incomplete` — the hf convention only. aria2c grows the REAL filename under `snapshots/` with a `<file>.aria2` control file, so mid-download read as complete ("finished at 23%", oscillating with live capture). Both probes now treat `*.aria2` as in-progress. Tests run the actual probe strings against synthetic cache trees (`tests/test_hf_cache_probes.py`).
- **Server output tail**: running tasks got a 12-line tail — smaller than one multi-file summary block; downloads now get 60 lines, URL walls stripped at source.
- **Client output window**: stored tail capped at 5000 chars; aria2c's 2–3 KB signed-URL NOTICEs evicted the summary block → parser starved → "Initializing…", per-file bars vanished. Now compacted (URL lines dropped) with a 20000-char window. Behavioral test proves the old window loses the summary and the new pipeline yields one row per file.
- All three converged onto `feat/aria2c-downloader`. This closes the D5 family: every completion signal is now either the DOWNLOAD_OK sentinel or a cache shape that both downloaders' conventions agree is final.

### D17. tmux line-wrapping defeated D16's URL filter; benign aria2c errors read as a crash (2026-07-20, live-verified)
Found minutes after D16 shipped, on a live Janus-Pro-7B + deepseek-math parallel download: card stuck on "Initializing", then "crashed" — while both tmux panes streamed healthy multi-file progress.
- **Wrapped URL walls** — `tmux capture-pane` without `-J` breaks the 2–3 KB signed-URL NOTICE lines into ~80-char fragments at pane width. No fragment matches the `\S{200,}` long-URL filter, so the 60-line tail was pure URL wall and the summary/`FILE:`/auth lines never reached the client. Fix: `-J` (rejoin wrapped logical lines) on every status-route and crash-watchdog capture. Verified against the live pane: 60-line tail = 2 full summary blocks + complete `FILE:` paths + compact lines, 0 URL fragments.
- **Benign aria2c `[ERROR]` lines** — xet-bridge redirects reject some range requests; aria2c logs `[ERROR] CUID#N … errorCode=22`, retries, and completes. The status route's generic `has_error` text sniff ran before the download-specific branches → healthy live download classified "error". Fix: download marker branches (`DOWNLOAD_OK`/`DOWNLOAD_FAILED`/incomplete evidence) now precede the sniff, and the sniff skips live downloads entirely — only the runner's `DOWNLOAD_FAILED` sentinel fails a download.
- **Auth pill loss** — the `[*] HF auth:` banner scrolls out before the first poll and both scrubbers (client `_redactTaskForStorage`, server `_strip_task_secrets`) deleted `hf_token` outright, so the payload fallback found nothing. Both now persist a non-secret `hf_token_used` boolean the pill falls back to.
- Guards: `tests/test_download_status_route_guards.py` (source-level; superseded by the tier-1 behavioral harness when it lands).
- **Follow-up (same night):** the `-J` join exposed a fourth face — `_pick_download_progress`'s `lines[-1]` fallback put a now-single-line 2-3 KB redirect NOTICE straight into the card header. Picker now skips URL/NOTICE/overlong lines, prefers aria2c's compact progress line, returns '' over noise (behavioral tests exec the real function). The screenshot's missing auth pill / stuck "Initializing" were the pre-fix page: the client JS was loaded before the D17 fixes landed on disk; `/static` serves `no-cache` + ETag, so any reload after them is current.
- **Follow-up (2026-07-20, fifth face):** the client reconnect loop runs its OWN `capture-pane -p -S -500` for the download card's phase parser — and it lacked `-J`. During the early NOTICE flood the wrapped-URL wall evicted the phase markers from the 500-physical-line window, so the card spun "Initializing…" while the header badge (server's fixed capture) tracked normally; it self-healed once compact aria2c lines dominated the pane. Fixed (`04fd36de`) + wiring guard. That was the last unjoined capture — server route, watchdog, and client now all pass `-J`.

### D18. A rate-limited (429) resolve reported DOWNLOAD_OK on zero files (2026-07-21, `3a0b8abb`)
A download of `bartowski/Qwen2.5-3B-GGUF` with no HF token said "complete" immediately while fetching nothing. Two layers:
- **Resolver swallowed the failure** (`tooling/hf_url_resolver.py`): `resolve_snapshot_urls` caught the 429 at every listing fallback (`list_repo_tree`, `list_repo_files`, raw API tree) and returned an **empty list** — indistinguishable from a repo that genuinely has no matching files. It now tracks whether any method returned an authoritative answer and **raises** when all failed, so the caller reports a real error instead of "nothing to download".
- **Downloader exited 0 on empty** (`tooling/aria2c_download.py`): `[!] No files matched — nothing to download.` was followed by `sys.exit(0)`, which the runner turned into `DOWNLOAD_OK`. Zero files is a failed download → now `sys.exit(1)` → `DOWNLOAD_FAILED`.
- **Defense in depth** (`routes/cookbook_output.py`): `classify_dead_download`'s zero-file guard (previously "Fetching 0 files" only) now also matches "No files matched"/"nothing to download", so a stray `DOWNLOAD_OK` over a zero-file snapshot is still classified error.
- Tests: `tests/test_hf_resolver_listing_failure.py` (raises on total failure, returns empty on genuine empty match), `tests/test_download_status_classification.py::test_no_files_matched_is_error_even_with_ok`. Extends the D5/D16 premature-"finished" family: the underlying 429 was caused by D19.

### D19. Stored HF token lost its `enc:` prefix → auth silently sent ciphertext (2026-07-21, `f257a9e8`)
The token in `data/cookbook_state.json` (`env.hfToken`) was a raw Fernet ciphertext with **no `enc:` prefix**. `secret_storage.decrypt` read the missing prefix as "legacy plaintext" and returned the **140-char ciphertext unchanged**, so `load_stored_hf_token()` handed the app a blob instead of the real `hf_` token. Every authenticated HuggingFace call then failed (the source of D18's 429s), while the UI "auth achieved" pill — driven by `bool(token)` — showed green the whole time. Broken on the host and on both benches.
- Fix: `decrypt()` now attempts a Fernet decrypt on an unprefixed value; a real ciphertext round-trips to plaintext, a genuine legacy-plaintext secret fails the HMAC/format check and falls through unchanged. Re-saving settings re-encrypts with the prefix, migrating the on-disk format.
- Bench remediation: the real token was decrypted on the host and re-encrypted with **each bench's own `data/.app_key`** (host key can't decrypt on a bench), written to the bench `cookbook_state.json`. Verified end-to-end: `resolve_snapshot_urls("bartowski/Qwen2.5-3B-GGUF")` returns **21 files** on macOS and Windows (was 429/empty).
- Test: `tests/test_secret_storage_legacy.py` (prefixed round-trip, unprefixed self-repair, genuine-plaintext passthrough).
