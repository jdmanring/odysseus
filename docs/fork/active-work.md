# Active Work

Current in-progress items as of 2026-06-08.

---

## In Progress

| Issue | Branch | Status |
|-------|--------|--------|
| [#7 HF token not saved outside Cookbook tab](https://github.com/jdmanring/odysseus/issues/7) | `fix/hf-token-persistence` | WIP — workaround script only; backend endpoint + JS needed |
| [#5 gh CLI unusable in Odysseus agent context](https://github.com/jdmanring/odysseus/issues/5) | none | Needs investigation — how should Odysseus handle non-interactive gh operations? |

---

## Recently Completed (on develop)

| Issue | Branch | Notes |
|-------|--------|-------|
| [#2 Renderer OOM — DOM virtualization](https://github.com/jdmanring/odysseus/issues/2) | `fix/dom-oom-virtualization` | `chatHistory.js` load pagination + live pruning. Upstream draft staged — needs screenshots. |
| [#3 External links don't navigate in Qt wrapper](https://github.com/jdmanring/odysseus/issues/3) | `feat/qt-native-linux-app` | `OdysseusPage` subclass routes external URLs to system browser |
| [#4 Tool results misattributed as user messages](https://github.com/jdmanring/odysseus/issues/4) | `fix/tool-result-role` | `agent_loop.py` + `llm_core.py` Anthropic payload builder fix |
| [#11 streamingTTS ReferenceError in catch block](https://github.com/jdmanring/odysseus/issues/11) | `fix/streamingtts-scope` | `let` hoisted out of try block. Upstream draft staged — ready to file. |
| [#12 aria2c downloader](https://github.com/jdmanring/odysseus/issues/12) | `feat/aria2c-downloader` | Multi-connection HF downloads + BinManager auto-install layer. `tests/tooling/test_bin_manager.py` covers BinManager. Upstream draft staged — needs integration test run + screenshot. |
| [#13 Color picker eyedropper broken in Qt](https://github.com/jdmanring/odysseus/issues/13) | `feat/qt-native-linux-app` | `qtBridge.openColorDialog()` replaces Web EyeDropper. Merged into #14. |
| [#14 Native Linux desktop app](https://github.com/jdmanring/odysseus/issues/14) | `feat/qt-native-linux-app` | `linux_wrapper.py`, crash recovery, lifecycle. Upstream draft staged — needs screenshots + constants audit. |
| [#16 Download UI overhaul](https://github.com/jdmanring/odysseus/issues/16) | `feat/download-ui-overhaul` | Per-file progress rows, accurate overall progress, `_dlFileTracker` |
| [#17 QWebEngineView localStorage wipes on exit](https://github.com/jdmanring/odysseus/issues/17) | `feat/qt-native-linux-app` | Persistent profile path set. Merged into #14. |
| [#20 BinManager test suite and fork testing standards](https://github.com/jdmanring/odysseus/issues/20) | `develop` (direct) | `tests/tooling/test_bin_manager.py` + `docs/fork/testing.md`. Landed before issue-first workflow was established. |

---

## Staged for Upstream (awaiting James to file)

See `docs/fork/upstream/pr-status.md` for full readiness status of all upstream contributions.
