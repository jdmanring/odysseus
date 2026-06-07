# [UPSTREAM] HF Token Not Saved When Set Outside Cookbook Tab

## Status
- Issue filed: Not yet filed
- PR opened: Not yet opened
- Fix in fork: Not yet implemented (fork uses `set-hf-token.py` workaround)

## Notes
Small, self-contained backend + JS fix. No visual changes — no screenshot required.
The dedicated endpoint approach is cleaner than patching the hydration guard.

---

## Staged Issue
<!-- James: open https://github.com/pewdiepie-archdaemon/odysseus/issues/new?template=bug_report.yml and paste below -->

**Steps to Reproduce**

1. Start Odysseus. Do not open the Cookbook tab.
2. Go to Settings and set a HuggingFace token in the token field.
3. Save settings and restart Odysseus.
4. Open the Cookbook tab and attempt a gated model download.

**Expected Behaviour**

The HuggingFace token persists across restarts and is available to the Cookbook downloader.

**Actual Behaviour**

The token is silently discarded. `data/cookbook_state.json` contains no `env.hfToken` entry.
The Cookbook reports authentication failure on gated model downloads even though the user
entered a valid token.

**Root Cause**

`_syncToServer()` in `cookbookRunning.js` has an early-return guard:
```js
if (!_envState || !Array.isArray(_envState.servers) || _envState.servers.length === 0) return;
```
`_envState.servers` is only populated when the Cookbook tab mounts and calls
`GET /api/cookbook/state`. If the token is set from any other settings panel before the
Cookbook tab has ever been opened in that session, `servers` is still `[]` and the
entire sync call silently returns without saving the token.

**Proposed Fix**

Add a dedicated `POST /api/cookbook/env/hf-token` endpoint that saves only the token,
bypassing the full-state sync and its hydration guard. The Settings token field calls
this endpoint directly instead of going through `_persistEnvState()` → `_syncToServer()`.

**Logs / Screenshots**

Confirmed by inspecting `data/cookbook_state.json` — no `hfToken` key present after
setting token outside Cookbook tab.

**Install Method:** Manual Python install

**OS:** Linux

**Willing to submit a fix:** Yes — I can open a PR

---

## Staged PR
<!-- James: file the issue first, get the number, fill in Fixes #NNN below, then open PR -->

### Summary

The HuggingFace token entered in Settings is silently discarded unless the Cookbook tab
has been opened in the same session. This is caused by a hydration guard in
`_syncToServer()` that returns early when `_envState.servers` is empty — which it always
is before the Cookbook tab mounts. Users on gated models are left with no indication
that their token was not saved.

Fix: add `POST /api/cookbook/env/hf-token` to persist only the token, bypassing the
guard. Wire the Settings token input to call this endpoint directly.

### Target branch
- [x] This PR targets **`dev`**, not `main`.

### Linked Issue

Fixes #

### Type of Change
- [x] Bug fix (non-breaking — fixes a confirmed issue)

### Checklist
- [x] Searched open issues and open PRs — not a duplicate
- [x] Targets `dev`
- [x] Changes limited to the scope described — no unrelated refactors
- [ ] App run locally and fix verified end-to-end *(must do before filing)*

### How to Test

1. Start Odysseus without opening the Cookbook tab.
2. Go to Settings → set a HuggingFace token and save.
3. Restart Odysseus.
4. Open the Cookbook and attempt a download of a gated model (e.g. meta-llama/Llama-3-8B).
5. Confirm the download proceeds without an authentication error.
6. Inspect `data/cookbook_state.json` — verify `env.hfToken` is present.

### Visual / UI changes

None — this change is backend only.
