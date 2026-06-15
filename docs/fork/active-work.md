# Active Work

Last updated: 2026-06-14. Fork is at milestone `v1.0.0-fork.1` — all CI passing on main.

---

## In Progress

| Issue | Branch | Status |
|-------|--------|--------|
| [#36 hf_transfer removal](https://github.com/jdmanring/odysseus/issues/36) | not started | Strip all hf_transfer install/enable code. Blocked pending upstream acceptance of feat/aria2c-downloader. |
| [#37 LongCat tool_call parsing](https://github.com/jdmanring/odysseus/issues/37) | not started | `<longcat_tool_call>` format not parsed or stripped. Needs full format capture before implementing. |
| [#38 LongCat tool call support](https://github.com/jdmanring/odysseus/issues/38) | `fix/longcat-tool-parsing` | Parser for both Variant A (JSON) and Variant B (tag-pair) formats + "longcat" keyword in _model_supports_tools. Branch complete. |
| [#39 Google toolCalls camelCase](https://github.com/jdmanring/odysseus/issues/39) | `fix/google-compat-toolcalls` | Fix delta.get("tool_calls") to also check "toolCalls". Branch complete. |
| [#40 Google native API path](https://github.com/jdmanring/odysseus/issues/40) | not started | Full GoogleProvider implementation in llm_core.py. Substantial feature, no existing SDK deps. |
| [#41 Gemma 4 local serving format](https://github.com/jdmanring/odysseus/issues/41) | not started | Low priority. Raw `<\|tool_call>` tokens leak only through self-hosted Ollama/llama-cpp-python/mlx-lm when chat template is incomplete. Google's hosted API is unaffected (already translates to `<tool_code>` format). |
| [#42 Expanded quality-scored resolver — all backends + imatrix tiers](https://github.com/jdmanring/odysseus/issues/42) | not started | Depends on `feat/aria2c-downloader` and `fix/gguf-quality-scored` landing upstream. Scope: add imatrix variants to QUANT_HIERARCHY, extend HfUrlResolver with find_vllm_sources(), wire resolver into all download paths (not just missing-config fallback). |
| [#43 macOS native wrapper](https://github.com/jdmanring/odysseus/issues/43) | not started | PyQt6 wrapper for macOS. Minus D-Bus; port 7860 (AirPlay); QColorDialog; macOS log/data dirs. Plan at `docs/fork/plans/mac-wrapper-plan.md`. Needs macOS hardware. |
| [#44 Windows native wrapper](https://github.com/jdmanring/odysseus/issues/44) | not started | PyQt6 wrapper for Windows. Minus D-Bus; ANGLE/D3D11 flags; Windows paths; taskkill zombie cleanup. Plan at `docs/fork/plans/windows-wrapper-plan.md`. Needs Windows hardware. |
| [#45 FreeBSD (KDE Plasma) wrapper](https://github.com/jdmanring/odysseus/issues/45) | `feat/qt-native-freebsd-app` | build-freebsd-app.sh and install.sh done. qt_wrapper.py platform guard pending FreeBSD hardware. Plan at `docs/fork/plans/freebsd-wrapper-plan.md`. |
| [#46 OpenBSD native wrapper](https://github.com/jdmanring/odysseus/issues/46) | not started | Extend qt_wrapper.py for OpenBSD; qt6-qtwebengine in ports (amd64/aarch64). pkill/pgrep FileNotFoundError guards. Plan at `docs/fork/plans/openbsd-wrapper-plan.md`. Needs OpenBSD hardware. |

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
| `refactor/assets-move` | [#19](https://github.com/jdmanring/odysseus/issues/19) | Single commit, ready |
| `fix/tool-result-role` | [#4](https://github.com/jdmanring/odysseus/issues/4) | Single commit, ready |
| `fix/dom-oom-virtualization` | [#2](https://github.com/jdmanring/odysseus/issues/2) | Single commit, ready. File upstream issue first. |
| `feat/aria2c-downloader` | [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | Single commit, ready. Verified 2026-06-12: pause/resume, split-file, zombie detection, clear-finished, resume spinner, cancel. Windows buffering fix in — untested. |
| `feat/catppuccin-theme` | [#30](https://github.com/jdmanring/odysseus/issues/30) | Single commit, ready |
| `feat/ai-documentation-system` | [#18](https://github.com/jdmanring/odysseus/issues/18) | Single commit, ready |
| `feat/qt-native-linux-app` | [#14](https://github.com/jdmanring/odysseus/issues/14) | Single commit, ready |
| `fix/gpu-compositor-flicker` | [#32](https://github.com/jdmanring/odysseus/issues/32) | Single commit, ready |
| `fix/css-render-perf` | [#33](https://github.com/jdmanring/odysseus/issues/33) | Single commit, ready |
| `feat/gh-cli-detection` | [#5](https://github.com/jdmanring/odysseus/issues/5) | Two commits, ready. Detects gh CLI and injects GitHub context into agent system prompt; exports GH_TOKEN so bash tool subprocesses can use gh on keyring-auth systems. Force-push needed (branch was amended and renamed). |
| `fix/tool-code-pycall-parsing` | [#35](https://github.com/jdmanring/odysseus/issues/35) | Single commit, ready. Parses and strips `<tool_code>` Python-call format (Google Gemma style) in tool_parsing.py. |
| `fix/gguf-quality-scored` | [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29) | Single commit, ready. File after `feat/aria2c-downloader` (extends HfUrlResolver with GGUF discovery). |
| `fix/longcat-tool-parsing` | [#38](https://github.com/jdmanring/odysseus/issues/38) | Single commit, ready. |
| `fix/google-compat-toolcalls` | [#39](https://github.com/jdmanring/odysseus/issues/39) | Single commit, ready. |
| `feat/logging` | [#31](https://github.com/jdmanring/odysseus/issues/31) | Single commit, ready. Infrastructure + timing callsites combined — callsites are untestable without infrastructure. Replaces feat/logging-core and feat/logging-timing. |

---

## Superseded / Closed

| Issue | Branch | Notes |
|-------|--------|-------|
| [#7 HF token not saved outside Cookbook tab](https://github.com/jdmanring/odysseus/issues/7) | `fix/hf-token-persistence` | Closed 2026-06-12 — superseded by upstream #3459 (`load_stored_hf_token()` in cookbook_helpers.py) |
| [#34 HF token env fallback](https://github.com/jdmanring/odysseus/issues/34) | `fix/hf-token-env-fallback` | Closed 2026-06-12 — same upstream fix covers this |
| [#9 basicsr Python 3.14 compat](https://github.com/jdmanring/odysseus/issues/9) | `fix/basicsr-python314-compat` | Superseded — upstream PR #3741 fixes same bug in `cookbook_helpers.py` with tests. Delete branch once #3741 merges into upstream-mirror. |
| [#11 streamingTTS scope](https://github.com/jdmanring/odysseus/issues/11) | `fix/streamingtts-scope` | Superseded — upstream PR #2418 makes same hoist fix with broader scope and a test. Delete branch once #2418 merges into upstream-mirror. |

---

## Fork-Only Work

| Issue | Branch | Notes |
|-------|--------|-------|
| [#15 Upstream sync pipeline](https://github.com/jdmanring/odysseus/issues/15) | `feat/upstream-sync-pipeline` | Manages fork/upstream relationship — not applicable upstream |
