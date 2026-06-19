# Active Work

Last updated: 2026-06-18. Upstream ingest run 2026-06-18 (LKG-20260618-0805, 17 new upstream commits). All staging branches rebased. Three new branches added this session: `fix/workspace-shell-access` (extended to cover web_search/web_fetch), `fix/untrusted-tool-result-header`, `fix/api-token-utcnow-deprecated`. Auto-scroll branch rebuilt clean as `fix/chat-auto-scroll-threshold` (replaced contaminated `fix/chat-auto-scroll-bottom`). All four new branches cherry-picked to develop. **None of the four new branches are user-verified yet.**

---

## In Progress

| Issue | Branch | Status |
|-------|--------|--------|
| [#36 hf_transfer removal](https://github.com/jdmanring/odysseus/issues/36) | not started | Strip all hf_transfer install/enable code. Blocked pending upstream acceptance of feat/aria2c-downloader. |
| [#38 LongCat tool call support](https://github.com/jdmanring/odysseus/issues/38) | `fix/longcat-tool-parsing` | JSON format only (official, per vLLM LongcatFlashToolParser + model card). Tag-pair format stripped but not executed — origin unverifiable. Branch complete. |
| [#39 Google toolCalls camelCase](https://github.com/jdmanring/odysseus/issues/39) | `fix/google-compat-toolcalls` | Fix delta.get("tool_calls") to also check "toolCalls". Branch complete. |
| [#40 Google native API path](https://github.com/jdmanring/odysseus/issues/40) | not started | Full GoogleProvider implementation in llm_core.py. Substantial feature, no existing SDK deps. |
| [#41 Gemma 4 local serving format](https://github.com/jdmanring/odysseus/issues/41) | not started | Low priority. Raw `<\|tool_call>` tokens leak only through self-hosted Ollama/llama-cpp-python/mlx-lm when chat template is incomplete. Google's hosted API is unaffected (already translates to `<tool_code>` format). |
| [#42 Expanded quality-scored resolver — all backends + imatrix tiers](https://github.com/jdmanring/odysseus/issues/42) | not started | Depends on `feat/aria2c-downloader` and `fix/gguf-quality-scored` landing upstream. Scope: add imatrix variants to QUANT_HIERARCHY, extend HfUrlResolver with find_vllm_sources(), wire resolver into all download paths (not just missing-config fallback). |
| [#43 macOS native wrapper](https://github.com/jdmanring/odysseus/issues/43) | `feat/qt-native-macos-app` | build-mac-app.sh done (.app + .dmg, NSSupportsAutomaticGraphicsSwitching). mac_wrapper.py pending macOS hardware. Plan at `docs/fork/plans/mac-wrapper-plan.md`. |
| [#44 Windows native wrapper](https://github.com/jdmanring/odysseus/issues/44) | `feat/qt-native-windows-app` | build-windows-app.ps1 + install.bat done (pythonw.exe, Start Menu + Desktop shortcuts). windows_wrapper.py pending Windows hardware. Plan at `docs/fork/plans/windows-wrapper-plan.md`. |
| [#45 FreeBSD (KDE Plasma) wrapper](https://github.com/jdmanring/odysseus/issues/45) | `feat/qt-native-freebsd-app` | build-freebsd-app.sh and install.sh done. qt_wrapper.py platform guard pending FreeBSD hardware. Plan at `docs/fork/plans/freebsd-wrapper-plan.md`. |
| [#46 OpenBSD native wrapper](https://github.com/jdmanring/odysseus/issues/46) | `feat/qt-native-openbsd-app` | build-openbsd-app.sh done. qt_wrapper.py pkill/pgrep guards pending OpenBSD hardware. Plan at `docs/fork/plans/openbsd-wrapper-plan.md`. |

---

## Staged for Upstream — Ready to File

All branches are built from `upstream-mirror`, contain only their specific changes, and are
pushed to `origin`. See `docs/fork/upstream/pr-status.md` for
full status and `docs/fork/upstream/pr-drafts/` for draft descriptions.

| Branch | Issue(s) | Notes |
|--------|----------|-------|
| `fix/agent-tool-budget` | [#10](https://github.com/jdmanring/odysseus/issues/10) | Single commit, ready |
| `fix/pytest-timeout-dependency` | [#6](https://github.com/jdmanring/odysseus/issues/6) | Single commit, ready |
| `fix/searxng-json-docs` | [#8](https://github.com/jdmanring/odysseus/issues/8) | Single commit, ready |
| `refactor/assets-move` | [#19](https://github.com/jdmanring/odysseus/issues/19) | Single commit, ready. Rework complete: SVG → `static/icons/`, manifest SVG entry added, build-macos-app.sh updated. |
| `fix/tool-result-role` | [#4](https://github.com/jdmanring/odysseus/issues/4) | Single commit, ready |
| `fix/dom-oom-virtualization` | [#2](https://github.com/jdmanring/odysseus/issues/2) | Single commit, ready. File upstream issue first. |
| `feat/aria2c-downloader` | [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | Single commit, ready. Verified 2026-06-12: pause/resume, split-file, zombie detection, clear-finished, resume spinner, cancel. Windows buffering fix in — untested. |
| `feat/catppuccin-theme` | [#30](https://github.com/jdmanring/odysseus/issues/30) | Single commit, ready |
| `feat/ai-documentation-system` | [#18](https://github.com/jdmanring/odysseus/issues/18) | Single commit, ready |
| `feat/qt-native-linux-app` | [#14](https://github.com/jdmanring/odysseus/issues/14) | Single commit, ready |
| `fix/gpu-compositor-flicker` | [#32](https://github.com/jdmanring/odysseus/issues/32) | Single commit, ready |
| `fix/css-render-perf` | [#33](https://github.com/jdmanring/odysseus/issues/33) | Single commit, ready |
| `feat/gh-cli-detection` | [#5](https://github.com/jdmanring/odysseus/issues/5) | Single commit, ready. Detects gh CLI and injects GitHub context into agent system prompt; module-level cache ensures subprocess is called once per server lifetime; exports GH_TOKEN for keyring-auth systems. |
| `fix/tool-code-pycall-parsing` | [#35](https://github.com/jdmanring/odysseus/issues/35) | Single commit, ready. Parses and strips `<tool_code>` Python-call format (Google Gemma style) in tool_parsing.py. |
| `fix/gguf-quality-scored` | [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29) | Single commit, ready. File after `feat/aria2c-downloader` (extends HfUrlResolver with GGUF discovery). |
| `fix/longcat-tool-parsing` | [#38](https://github.com/jdmanring/odysseus/issues/38) | Single commit, ready. |
| `fix/google-compat-toolcalls` | [#39](https://github.com/jdmanring/odysseus/issues/39) | Single commit, ready. |
| `feat/logging` | [#31](https://github.com/jdmanring/odysseus/issues/31) | Single commit, ready. Infrastructure + timing callsites combined — callsites are untestable without infrastructure. Replaces feat/logging-core and feat/logging-timing. |
| `fix/basicsr-python314-compat` | [#9](https://github.com/jdmanring/odysseus/issues/9) | Single commit, ready. Previously marked superseded; re-activated 2026-06-15. #3741 covers only the Serve panel; ours also covers the Dependencies tab and adds an inline POSIX abort. File upstream issue first. |
| `fix/workspace-shell-access` | [#47](https://github.com/jdmanring/odysseus/issues/47) | Single commit, ready. bash/python verified 2026-06-16. web_search/web_fetch unverified — #47 reopened. File upstream issue first. |
| `fix/untrusted-tool-result-header` | [#48](https://github.com/jdmanring/odysseus/issues/48) | Single commit, ready. Fixes over-application of untrusted-result header introduced by upstream #1629 (2026-06-16). File upstream issue first. |
| `fix/api-token-utcnow-deprecated` | [#51](https://github.com/jdmanring/odysseus/issues/51) | Single commit, ready. Follow-up to upstream 790ef81b — missed instance of deprecated datetime.utcnow() in api-token last_used_at update. File upstream issue first. |
| `fix/chat-auto-scroll-threshold` | [#49](https://github.com/jdmanring/odysseus/issues/49) | Single commit, ready. Adaptive viewport-based threshold replaces rigid 300px guard in _smoothScrollStep(). File upstream issue first. Rebuilt clean from contaminated `fix/chat-auto-scroll-bottom`. |

---

## Superseded / Closed

| Issue | Branch | Notes |
|-------|--------|-------|
| [#37 LongCat tool_call parsing](https://github.com/jdmanring/odysseus/issues/37) | — | Closed — investigation subsumed by #38 (`fix/longcat-tool-parsing`). Implementation handles all format variants. |
| [#7 HF token not saved outside Cookbook tab](https://github.com/jdmanring/odysseus/issues/7) | `fix/hf-token-persistence` | Closed 2026-06-12 — superseded by upstream #3459 (`load_stored_hf_token()` in cookbook_helpers.py) |
| [#34 HF token env fallback](https://github.com/jdmanring/odysseus/issues/34) | `fix/hf-token-env-fallback` | Closed 2026-06-12 — same upstream fix covers this |
| [#11 streamingTTS scope](https://github.com/jdmanring/odysseus/issues/11) | `fix/streamingtts-scope` | Superseded — upstream PR #2418 ("fix(chat): render abort messages — hoist streamingTTS out of the try block") makes same hoist fix with broader scope and a test. Still open as of 2026-06-15, no comments. Delete branch once #2418 merges into upstream-mirror. |

---

## Fork-Only Work

| Issue | Branch | Notes |
|-------|--------|-------|
| [#15 Upstream sync pipeline](https://github.com/jdmanring/odysseus/issues/15) | `feat/upstream-sync-pipeline` | Manages fork/upstream relationship — not applicable upstream |
