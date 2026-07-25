# Download-stack test hardening: mandated 2026-07-20

Four gaps identified in the post-D16 test review; all four commissioned.

1. **Status state-machine harness** (highest value): simulate the poll loop:
   feed transcript windows in order (real fixtures: tiny-success, midrun,
   dspark multi-file, FreakStorm failure) through the composed status pipeline
   and assert the invariant that broke all week: status never regresses
   done->running->done; "done" appears ONLY after DOWNLOAD_OK is in the window.
   Extract the poll's decision core into a pure function (same pattern as
   _shouldStopBackgroundMonitor) so node can drive it without DOM.
2. **Upgrade static guards to behavioral where the guard can be wrong**, not
   just absent: probe semantics (done, test_hf_cache_probes.py is the model),
   retry backend pinning, delete exit_code handling.
3. **Deliberate live E2E tier**: pytest -m live suite that STARTS its own app
   instance (bare uvicorn, temp DB/cache) instead of hijacking the user's
   session (ODYSSEUS_LIVE_UI_TESTS lesson); drives download+Launch through the
   real endpoints with a tiny model (tiny-random/gpt2).
4. **Adjacent-path coverage**: Pause/Resume during each phase, retry backend
   pinning (P2-2 fix ships with its test), remote-host probe variants,
   multi-file + resume combinations.

Staging: these ride with feat/aria2c-downloader (tests are PR-strengthening).
The hwfit staging branch (#149/#150/#151) is a separate pending item.

## Status: all four tiers landed on develop 2026-07-20

1. **DONE** (`e78bdb79`): `_nextDownloadStatus` pure reducer wired at all three
   decision sites; rolling-window harness over three NEW real fixtures
   (multi-file success, gated failure, exit-2 failure) captured from live panes.
   Sticky-done closed the done->crashed regression in the blind background poll.
2. **DONE** (`2538f11c`): P2-2 retry backend pinning (client `pin_backend` +
   server `resolve_download_backend`, fails loudly); delete exit_code check
   extracted to `_shellExecFailure` and pinned behaviorally.
3. **DONE** (`f28b4328`): `tests/test_live_download_e2e.py`, opt-in via
   `RUN_LIVE_E2E=1 pytest -m live`. Boots a private uvicorn (temp data dir,
   internal-token auth), real aria2c download of tiny-random-gpt2 confined to
   the test dir, full lifecycle asserted. ~5s wall warm. Documented contract:
   the launch route does NOT self-register tasks; the client does, via
   `POST /api/cookbook/state`.
4. **DONE** (this commit): paused-is-sticky reducer rule (C-c pause artifact
   `DOWNLOAD_FAILED` can no longer flip a paused task); full
   `_buildDownloadCardHtml` build exercised in node (paused override,
   multi-file rows, initializing on marker-less floods).

**Deliberately not covered** (recorded, not silently dropped):
- Real *resume* transcript fixture (`--continue` over `.aria2` sidecars): needs
  a mid-flight interrupt of a real large download; synthesizing one would
  violate the real-fixtures rule. Capture next time a real pause/resume happens.
- Remote-host probe plumbing (`ssh -p` variants around the cache probes): needs
  a reachable remote host; the probe *payloads* themselves are covered locally
  in test_hf_cache_probes.py.
