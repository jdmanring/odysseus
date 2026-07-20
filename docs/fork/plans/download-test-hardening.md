# Download-stack test hardening — mandated 2026-07-20

Four gaps identified in the post-D16 test review; all four commissioned.

1. **Status state-machine harness** (highest value): simulate the poll loop —
   feed transcript windows in order (real fixtures: tiny-success, midrun,
   dspark multi-file, FreakStorm failure) through the composed status pipeline
   and assert the invariant that broke all week: status never regresses
   done→running→done; "done" appears ONLY after DOWNLOAD_OK is in the window.
   Extract the poll's decision core into a pure function (same pattern as
   _shouldStopBackgroundMonitor) so node can drive it without DOM.
2. **Upgrade static guards to behavioral where the guard can be wrong**, not
   just absent: probe semantics (done — test_hf_cache_probes.py is the model),
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
