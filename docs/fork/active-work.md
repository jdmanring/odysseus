# Active Work

Current in-progress items as of 2026-06-08.

---

## In Progress

| Issue | Branch | Status |
|-------|--------|--------|
| [#4 Tool results misattributed as user messages](https://github.com/jdmanring/odysseus/issues/4) | `fix/tool-result-role` | Fix rebuilt from current upstream-mirror (ccf5342). Both agent_loop.py + llm_core.py changes now correctly in develop. Needs end-to-end verification before closing. |
| [#7 HF token not saved outside Cookbook tab](https://github.com/jdmanring/odysseus/issues/7) | `fix/hf-token-persistence` | WIP — workaround script only; backend endpoint + JS needed |
| [#5 gh CLI unusable in Odysseus agent context](https://github.com/jdmanring/odysseus/issues/5) | none | Needs investigation — how should Odysseus handle non-interactive gh operations? |
| [#3 External links don't navigate in Qt wrapper](https://github.com/jdmanring/odysseus/issues/3) | `feat/qt-native-linux-app` | Fix in develop. Reopened — upstream contribution not yet tracked (part of #14 Qt wrapper PR). |
| [#18 AI-first documentation system](https://github.com/jdmanring/odysseus/issues/18) | `feat/ai-documentation-system` | Reopened — was incorrectly closed as fork-only. AI_RULES.md + AI_CONTEXT.md are upstream-candidate. See also #21, #22. |
| [#20 BinManager test suite](https://github.com/jdmanring/odysseus/issues/20) | `develop` (direct) | Tests in develop. Reopened — was incorrectly labeled fork-only. Tests go upstream bundled with #12 (aria2c downloader). |

---

## Recently Completed (on develop)

| Issue | Branch | Notes |
|-------|--------|-------|
| [#2 Renderer OOM — DOM virtualization](https://github.com/jdmanring/odysseus/issues/2) | `fix/dom-oom-virtualization` | `chatHistory.js` — three-phase DOM virtualization + 4 rounds of hardening. CSS compositor flicker: will-change removed from chat-container, chat-input-bar (3×), textarea#message. `sessions.js` scrollHistoryInstant() moved after hljs for correct initial scroll (overflow-anchor:none disables auto-compensation). 5 commits on staging branch, needs squash → 1 before filing. File upstream issue first. PR draft complete. |
| [#11 streamingTTS ReferenceError in catch block](https://github.com/jdmanring/odysseus/issues/11) | `fix/streamingtts-scope` | `let` hoisted out of try block. Upstream draft staged — ready to file. |
| [#12 aria2c downloader](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | `feat/aria2c-downloader` | Multi-connection HF downloads + BinManager + reliability fixes (folded from #23: tmux width, totalFiles fallback, conn_per_file 3, tab indent, HfUrlResolver fallback). Needs integration test run + screenshot. |
| [#24 Dynamic GGUF source discovery](https://github.com/jdmanring/odysseus/issues/24) | `feat/gguf-discovery` | find_gguf_sources(), /api/cookbook/resolve-gguf, cookbookDownload.js auto-discovery. Upstream draft staged — file after #12. |
| [#13 Color picker eyedropper broken in Qt](https://github.com/jdmanring/odysseus/issues/13) | `feat/qt-native-linux-app` | `qtBridge.openColorDialog()` replaces Web EyeDropper. Merged into #14. |
| [#14 Native Linux desktop app](https://github.com/jdmanring/odysseus/issues/14) | `feat/qt-native-linux-app` | `linux_wrapper.py`, crash recovery, lifecycle. Upstream draft staged — needs screenshots + constants audit. |
| [#16 Download UI overhaul](https://github.com/jdmanring/odysseus/issues/16) | `feat/download-ui-overhaul` | Per-file progress rows, accurate overall progress, `_dlFileTracker` |
| [#17 QWebEngineView localStorage wipes on exit](https://github.com/jdmanring/odysseus/issues/17) | `feat/qt-native-linux-app` | Persistent profile path set. Merged into #14. |

---

## Staged for Upstream (awaiting James to file)

See `docs/fork/upstream/pr-status.md` for full readiness status of all upstream contributions.
