# Active Work

Current in-progress items as of 2026-06-11. (GPU flicker fix added 2026-06-11)

---

## In Progress

| Issue | Branch | Status |
|-------|--------|--------|
| [#4 Tool results misattributed as user messages](https://github.com/jdmanring/odysseus/issues/4) | `fix/tool-result-role` | Fix rebuilt from current upstream-mirror (ccf5342). Both agent_loop.py + llm_core.py changes now correctly in develop. Needs end-to-end verification before closing. |
| [#7 HF token not saved outside Cookbook tab](https://github.com/jdmanring/odysseus/issues/7) | `fix/hf-token-persistence` | WIP — workaround script only; backend endpoint + JS needed |
| [#5 gh CLI unusable in Odysseus agent context](https://github.com/jdmanring/odysseus/issues/5) | `feat/github-integration` | GitHub preset added to integrations framework. Agent uses api_call tool with token auth. Staged — ready to file upstream. |
| [#3 External links don't navigate in Qt wrapper](https://github.com/jdmanring/odysseus/issues/3) | `feat/qt-native-linux-app` | Fix in develop. Reopened — upstream contribution not yet tracked (part of #14 Qt wrapper PR). |
| [#18 AI-first documentation system](https://github.com/jdmanring/odysseus/issues/18) | `feat/ai-documentation-system` | Reopened — was incorrectly closed as fork-only. AI_RULES.md + AI_CONTEXT.md are upstream-candidate. See also #21, #22. |
| [#20 BinManager test suite](https://github.com/jdmanring/odysseus/issues/20) | `develop` (direct) | Tests in develop. Reopened — was incorrectly labeled fork-only. Tests go upstream bundled with #12 (aria2c downloader). |

---

## Recently Completed (on develop)

| Issue | Branch | Notes |
|-------|--------|-------|
| [#26 Filesystem access broken](https://github.com/jdmanring/odysseus/issues/26) | ~~`fix/filesystem-access-regression`~~ | Retired — superseded by upstream #3665 (workspace confinement). Use `/workspace` to grant file access. Issue closed. |
| [#28 Filesystem tools crash — dead workspace import](https://github.com/jdmanring/odysseus/issues/28) | ~~`fix/agent-tools-workspace-import`~~ | Retired — upstream #3665 properly defines `_resolve_tool_path_in_workspace`. Branch emptied; issue closed. |

---

## Previously Completed

| Issue | Branch | Notes |
|-------|--------|-------|
| [#2 Renderer OOM — DOM virtualization](https://github.com/jdmanring/odysseus/issues/2) | `fix/dom-oom-virtualization` | Staging branch rebuilt as single clean commit (8db240a). Drain and session-load scroll verified working. Ready to file — create upstream issue, then open PR from staging branch. |
| [#9 realesrgan / basicsr broken on Python 3.14](https://github.com/jdmanring/odysseus/issues/9) | `fix/basicsr-python314-compat` | `install-basicsr.sh` patches incompatible C extension. In develop. Upstream draft staged — ready to file. |
| [#11 streamingTTS ReferenceError in catch block](https://github.com/jdmanring/odysseus/issues/11) | `fix/streamingtts-scope` | `let` hoisted out of try block. Upstream draft staged — ready to file. |
| [#12 aria2c downloader](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | `feat/aria2c-downloader` | Multi-connection HF downloads + BinManager + reliability fixes (folded from #23: tmux width, totalFiles fallback, conn_per_file 3, tab indent, HfUrlResolver fallback). Needs integration test run + screenshot. |
| [#24 Dynamic GGUF source discovery](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29) | `fix/gguf-quality-scored` | Quality-scored discovery, mmproj filter, model.quant precedence, tier-aware closest-quant fallback. **Verified 2026-06-11**: Llama-3.2-11B-Vision-Instruct downloaded Q4_K_M (not mmproj); DeepSeek-V2-Lite-Chat downloaded IQ4_XS (best in tier 4 from imatrix-only repo). Ready to file — see pr-drafts/feat-gguf-discovery.md. |
| [#13 Color picker eyedropper broken in Qt](https://github.com/jdmanring/odysseus/issues/13) | `feat/qt-native-linux-app` | `qtBridge.openColorDialog()` replaces Web EyeDropper. Merged into #14. |
| [#14 Native Linux desktop app](https://github.com/jdmanring/odysseus/issues/14) + [#32](https://github.com/jdmanring/odysseus/issues/32) | `feat/qt-native-linux-app` + `fix/gpu-compositor-flicker` | `linux_wrapper.py` GPU flag fix committed to staging branch. CSS backdrop-filter fix on separate branch. Both in develop. Needs verification — restart app and test sidebar hover, dropdowns, Settings/Providers. Upstream draft needs update before filing. |
| [#16 Download UI overhaul](https://github.com/jdmanring/odysseus/issues/16) | `feat/download-ui-overhaul` | Per-file progress rows, accurate overall progress, `_dlFileTracker` |
| [#17 QWebEngineView localStorage wipes on exit](https://github.com/jdmanring/odysseus/issues/17) | `feat/qt-native-linux-app` | Persistent profile path set. Merged into #14. |

---

## Staged for Upstream (awaiting James to file)

See `docs/fork/upstream/pr-status.md` for full readiness status of all upstream contributions.
