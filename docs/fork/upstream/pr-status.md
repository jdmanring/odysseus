# Upstream Contributions

One branch per contribution. Each branch is built from `upstream-mirror` and contains
only the changes for that one fix or feature — nothing fork-specific.

**Never push to upstream remote. Never file issues or PRs upstream without explicit
per-action authorization. Agents stage; you file.**

---

## Branch → Issue Map

| Branch | Issue | Type | Status |
|--------|-------|------|--------|
| `fix/agent-tool-budget` | [#10](https://github.com/jdmanring/odysseus/issues/10) | Bug | Ready to file — added `tests/test_agent_tool_budget.py` (5 tests: zero-bypass guard present, 0=unlimited at any call count, default=20, positive limit triggers at threshold). See pr-drafts/ |
| `fix/pytest-timeout-dependency` | [#6](https://github.com/jdmanring/odysseus/issues/6) | Bug | Ready to file — see pr-drafts/ |
| `fix/searxng-json-docs` | [#8](https://github.com/jdmanring/odysseus/issues/8) | Bug/Docs | Ready to file — see pr-drafts/ |
| `fix/basicsr-python314-compat` | [#9](https://github.com/jdmanring/odysseus/issues/9) | Bug | Ready to file — single squashed commit. PR #3741 covers the Serve panel only; this PR also covers the Dependencies tab (`shell_routes.py`) and adds inline POSIX abort. File upstream issue first (draft in issue-drafts/). See pr-drafts/ |
| `fix/streamingtts-scope` | [#11](https://github.com/jdmanring/odysseus/issues/11) | Bug | Superseded — upstream PR #2418 makes the same hoist fix, also restores abort message rendering (broader scope), and has a test. Do not file. Delete branch once #2418 merges into upstream-mirror. |
| `refactor/assets-move` | [#19](https://github.com/jdmanring/odysseus/issues/19) | Refactor | Ready to file — see pr-drafts/ |
| `fix/tool-result-role` | [#4](https://github.com/jdmanring/odysseus/issues/4) | Bug | Ready to file — fixed broken `test_agent_loop.py` assertion (role user→system); added `TestRecentContextForRetrieval` (6 tests, old and new format exclusion); new `tests/test_tool_result_role.py` (6 tests for `_build_anthropic_payload` inline routing). See pr-drafts/fix-tool-result-role.md |
| `fix/dom-oom-virtualization` | [#2](https://github.com/jdmanring/odysseus/issues/2) | Bug | **More-complete alternative to open upstream PR #4661, with an independent architecture.** Provenance (precise): the MessageWindow architecture predates #4661 (first commit ~19h before #4661 opened), but the per-node teardown cleanup was **adapted from #4661 and extended** (per `memory-explosion-research.md` and draft line 58) — do NOT claim full code-independence. Ours adds bidirectional scroll-up and releases StreamRenderer/IntersectionObserver/hljs-defer refs beyond #4661; #4661 is smaller. Offer on merits, crediting #4661. Branch contamination (PR-draft .md) removed. **Plan: `docs/fork/plans/dom-oom-virtualization-upstream-plan.md`.** |
| `feat/aria2c-downloader` | [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | Feature | Verified (2026-06-12): pause/resume (single+multi-file), split-file size, menu toggle, clear-finished, zombie detection, resume spinner, cancel mid-download. Windows buffering fix implemented (untested, needs Windows machine). aria2c is now the default (`use_aria2c: bool = True` in schema); hf-download is the pre-flight fallback when aria2c binary unavailable. Added `tests/test_aria2c_circuit.py` with `@pytest.mark.slow` on network classes + 4 static contract tests. **File before `fix/gguf-quality-scored`** (introduces `HfUrlResolver` base class). See pr-drafts/ |
| `feat/catppuccin-theme` | [#30](https://github.com/jdmanring/odysseus/issues/30) | Feature | Ready to file — see pr-drafts/feat-catppuccin-theme.md |
| `feat/ai-documentation-system` | [#18](https://github.com/jdmanring/odysseus/issues/18) | Docs | Ready to file — see pr-drafts/ |
| `feat/qt-native-linux-app` | [#14](https://github.com/jdmanring/odysseus/issues/14) | Feature | Ready to file — see pr-drafts/feat-qt-native-linux-app.md |
| `fix/gpu-compositor-flicker` | [#32](https://github.com/jdmanring/odysseus/issues/32) | Bug | Ready to file — see pr-drafts/fix-gpu-compositor-flicker.md |
| `fix/css-render-perf` | [#33](https://github.com/jdmanring/odysseus/issues/33) | Perf | Ready to file — see pr-drafts/fix-css-render-perf.md |
| `fix/hf-token-env-fallback` | [#34](https://github.com/jdmanring/odysseus/issues/34) | Bug | Superseded — upstream landed same fix in #3459 (synced 2026-06-12). Draft moved to `deprecated/`. Do not file. |
| `feat/gh-cli-detection` | [#5](https://github.com/jdmanring/odysseus/issues/5) | Feature | Ready to file — module-level cache added (subprocess called once per server lifetime); 12 tests (11 behavioral + 1 cache test). See pr-drafts/feat-gh-cli-detection.md |
| `fix/gguf-quality-scored` | [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29) | Feature | Ready to file after `feat/aria2c-downloader` (extends `HfUrlResolver` — gguf discovery methods). Added `tests/test_gguf_scoring.py` with 20 pure-function tests (no network). See pr-drafts/feat-gguf-discovery.md |
| `fix/tool-code-pycall-parsing` | [#35](https://github.com/jdmanring/odysseus/issues/35) | Bug | Ready to file — see pr-drafts/fix-tool-code-pycall-parsing.md |
| `fix/longcat-tool-parsing` | [#38](https://github.com/jdmanring/odysseus/issues/38) | Bug | Ready to file — added `tests/test_longcat_tool_parsing.py` (13 tests, covers both Variant A/B, unknown-name pass-through behavior documented). See pr-drafts/fix-longcat-tool-parsing.md |
| `fix/google-compat-toolcalls` | [#39](https://github.com/jdmanring/odysseus/issues/39) | Bug | Ready to file — 4 tests: 3 presence checks + 1 ordering test (verifies `tool_calls` checked before `toolCalls` in fallback chain). See pr-drafts/fix-google-compat-toolcalls.md |
| `feat/logging` | [#31](https://github.com/jdmanring/odysseus/issues/31) | Feature | Ready to file — infrastructure and callsites combined in one PR. See pr-drafts/feat-logging.md |
| `fix/workspace-shell-access` | [#47](https://github.com/jdmanring/odysseus/issues/47) | Bug | Ready to file — single clean commit, verified 2026-06-16. Covers bash/python + web_search/web_fetch. File upstream issue first. Companion to PR #4398. See pr-drafts/fix-workspace-shell-access.md |
| `fix/untrusted-tool-result-header` | [#48](https://github.com/jdmanring/odysseus/issues/48) | Bug | Ready to file — single clean commit. Fixes false-positive refusals introduced by upstream #1629 (2026-06-16). File upstream issue first. See pr-drafts/fix-untrusted-tool-result-header.md |
| `fix/api-token-utcnow-deprecated` | [#51](https://github.com/jdmanring/odysseus/issues/51) | Bug | Ready to file — single clean commit, 2 lines changed. Follow-up to upstream 790ef81b (missed instance). File upstream issue first. See pr-drafts/fix-api-token-utcnow-deprecated.md |
| `fix/chat-auto-scroll-threshold` | [#49](https://github.com/jdmanring/odysseus/issues/49) | Bug | Ready to file — single clean commit. Adaptive threshold replaces rigid 300px guard in _smoothScrollStep(). File upstream issue first. See pr-drafts/fix-chat-auto-scroll-threshold.md |

## Process-stack perf candidates (audit section E, 2026-06-25)

Three fork issues filed from `docs/fork/perf-audit-2026-06.md`. Their **branch origin
differs by whether the touched files exist on `upstream-mirror`** — getting this wrong
contaminates the branch:

| Fork issue | Touches | Origin / home | Independent? | Maps upstream to |
|---|---|---|---|---|
| [#111](https://github.com/jdmanring/odysseus/issues/111) lazy-connect cold MCP | `src/builtin_mcp.py`, `src/mcp_manager.py` (both on `upstream-mirror`) | **`perf/mcp-lazy-connect`** (cut from `upstream-mirror`; implemented, cherry-picked to develop; draft issue+PR staged; research in `mcp-lazy-connect-research.md`) | **Yes** | #2140, #3824; ROADMAP email-perf. #4812 reconciled (complementary; file after #4812, route eager branch through its `_spawn_bg` — see research doc) |
| [#112](https://github.com/jdmanring/odysseus/issues/112) host VmRSS telemetry | `qt_wrapper.py` (**not** on `upstream-mirror`) | **folded into `perf/renderer-memory-reclaim`** (the telemetry owner; done, cherry-picked to develop) | No — **depends on #14** | rides the Qt-wrapper stack |
| [#113](https://github.com/jdmanring/odysseus/issues/113) `--no-access-log` | `qt_wrapper.py` / `mac_wrapper.py` / `windows_wrapper.py` (**not** on `upstream-mirror`) | **DONE** on each `feat/qt-native-{linux,macos,windows}-app` branch; cherry-picked to develop (guard test on develop) | No — **rides each platform PR** | folds into #14 (linux) + macos/windows PRs. Real fix is `--no-access-log` (uvicorn default is ON) |

### Idle-quiescence candidates (audit C3 / #117, 2026-06-25)

| Fork issue | Branch | Touches | Status |
|--------|--------|---------|--------|
| [#117](https://github.com/jdmanring/odysseus/issues/117) (notes instance) | `fix/notes-quick-idle-quiescence` | `static/js/ui.js`, `static/style.css` | **DONE** — from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged; adds reusable `html.app-blurred` primitive. Independent. |
| [#115](https://github.com/jdmanring/odysseus/issues/115) | `fix/research-orbit-quiescence` | `static/js/research/panel.js` | **DONE** — from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. JS-only, single concern. Independent. |
| [#118](https://github.com/jdmanring/odysseus/issues/118) (audit D1+D2) | `fix/timer-visibility-gating` | `modalManager.js`, `emailInbox.js`, `tasks.js` | **DONE** — visibility-gate background timers; from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. Independent. |
| [#119](https://github.com/jdmanring/odysseus/issues/119) (audit D3) | `fix/sigcache-lru-bound` | `static/js/document.js` | **DONE** — LRU-bound `_sigCache`; from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. Independent. |

**⚠ Pre-existing staging gap surfaced:** `perf/renderer-memory-reclaim` (the bulk of this
cycle's memory work: #106 forciblyPurge, idle-purge, GC catch-up, and now #112 host telemetry)
is **stacked on `feat/qt-native-linux-app` (#14)** and has **no `pr-status` row, no draft
upstream issue, and no draft PR**. It cannot be a standalone `upstream-mirror` PR because
`qt_wrapper.py` is introduced by #14. **Decision needed:** stage it as a PR stacked on #14
(filed only after #14 lands upstream), or fold the Qt-side diagnostics into #14 itself. #112
and #113 inherit the same decision. **Do not file any of these until #14's upstream fate is
settled.**

## PR Drafts and Issue Drafts

Staged PR descriptions live in `docs/fork/upstream/pr-drafts/`, one file per branch
(named after the branch with `/` → `-`). Each draft contains the proposed title,
description body, and filing notes. The description is written for upstream
reviewers — it does not assume they have seen our fork's issue tracker.

For branches that require a new upstream issue to be filed first, a pre-written issue
(title + body, ready to paste) lives in `docs/fork/upstream/issue-drafts/<name>.md`.
File the issue on `pewdiepie-archdaemon/odysseus`, get its number, fill it into
`Fixes #` in the PR draft, then open the PR.

## Filing Procedure

1. File a GitHub issue on `pewdiepie-archdaemon/odysseus` (from `issue-drafts/<name>.md`)
2. Add the upstream issue number to `Fixes #` in the PR draft
3. Open PR from `<your-fork>:<branch>` → `pewdiepie-archdaemon/odysseus:dev`
4. All PRs target `dev`, not `main`

## Fork-Only Work (not going upstream)

| Branch | Issue | Notes |
|--------|-------|-------|
| `feat/upstream-sync-pipeline` | [#15](https://github.com/jdmanring/odysseus/issues/15) | Manages fork/upstream relationship — not applicable upstream |
