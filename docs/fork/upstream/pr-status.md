# Upstream Contributions

One branch per contribution. Each branch is built from `upstream-mirror` and contains
only the changes for that one fix or feature — nothing fork-specific.

**Never push to upstream remote. Never file issues or PRs upstream without explicit
per-action authorization. Agents stage; you file.**

---

## ⚠ 2026-07-07 — rebase state after the 320-commit upstream ingest

`upstream-mirror` advanced to `c67deaa6` (`#5283`), including a module-extraction
refactor. **All staging branches were rebased onto current `upstream-mirror`:
54 clean, 19 conflict** (backed up at `backup/prerebase__*`). The 19 conflicts
need the same resolutions applied in the develop merge (recipes in the branch's
row and in scratch `SYNC_REPORT.md`). **Verify each branch's tests before filing —
a clean rebase is not a correctness guarantee** (spot-checked 7 candidates green /
212 tests; one brittle static test fails on the *superseded* `renderer-memory-reclaim`).

**Superseded by upstream — do not file:** `fix/agent-context-budget-discovery`
(#54) and the #57 lazy-probe research → upstream **#4886/#4909**. The fork's
`?limit=400` history pagination is superseded by the maintainer's history pager
(direct commit **`45ee5a71`**, NOT #5090 — #5090 is only a route-subpackage
refactor; verified via `gh` 2026-07-07). **CAVEAT: that upstream pager is INERT**
— a legacy `/api/history/{sid}` route shadows the paginated endpoint, so it never
paginates (see recon §8; fix staged on `fix/chat-history-dom-eviction`). The
fork's `fix/chat-history-server-paging` (merged to develop `6fac912d`) is *also*
built on this broken endpoint — **CONFIRMED inert on develop 2026-07-07**: develop
carries the identical collision (legacy `get_history` present; `session_routes`
registered before `history_routes`), and `_fetchOlderFromServer` calls
`_historyUrl(sid, {limit, offset})` → the shadow → full history in one fetch. Its
"150/150 reachable" test passes trivially (all returned at once, not paged).
**Action — DONE 2026-07-07:** route-shadowing fix cherry-picked to develop
(`268d713c`). Verifying it end-to-end surfaced a **severe pre-existing develop bug**:
`sessions.js._mapHistoryMessages` (added by server-paging `90b0ebba`) called
`markdownModule.renderContent` without importing `markdownModule` → `ReferenceError`
on every session load → **chat history rendered empty** (error swallowed by
selectSession's catch; missed by static/mock tests). Fixed by adding the import
(`a34ae5a0`) + a real-browser regression test (`dffed66b`, verified to fail without
the fix). After both fixes, verified end-to-end: history renders, scroll-up pages to
the oldest message, DOM stays bounded. The **eviction graft (commit 2) is NOT
cherry-picked** — it hooks the upstream `_installHistoryPager`, which is dead code on
develop (develop's active pager is the fork MessageWindow, which has its own eviction).

`fix/untrusted-tool-result-header` (#48) **rebuilt** as one clean commit on current
`upstream-mirror`, byte-identical to develop; PR draft corrected to the shipped header.

Nothing pushed yet (develop, integration+tag, and the rebased branches are local).

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
| `fix/tool-result-role` | [#4](https://github.com/jdmanring/odysseus/issues/4) | Bug | **Do not file: superseded by upstream #1629, branch deleted (2026-06-18).** #1629 wraps tool results via `untrusted_context_message()` as guarded `role: user` messages, so they stay inline and never collapse into `system_parts` (verified on develop). The fork's code path is dead. Draft marked SUPERSEDED. |
| `fix/dom-oom-virtualization` | [#2](https://github.com/jdmanring/odysseus/issues/2) | Bug | **More-complete alternative to open upstream PR #4661, with an independent architecture.** Provenance (precise): the MessageWindow architecture predates #4661 (first commit ~19h before #4661 opened), but the per-node teardown cleanup was **adapted from #4661 and extended** (per `memory-explosion-research.md` and draft line 58) — do NOT claim full code-independence. Ours adds bidirectional scroll-up and releases StreamRenderer/IntersectionObserver/hljs-defer refs beyond #4661; #4661 is smaller. Offer on merits, crediting #4661. Branch contamination (PR-draft .md) removed. **Plan: `docs/fork/plans/dom-oom-virtualization-upstream-plan.md` — its Part 4.5 is mandatory: the server-paging fold must carry the #129 chIdx-retag fix (`ac18291a`) and its regression test, or the filed PR ships a measured unbounded-DOM defect. Fork #129 stays open until this PR is filed.** |
| `feat/aria2c-downloader` | [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | Feature | Verified (2026-06-12): pause/resume (single+multi-file), split-file size, menu toggle, clear-finished, zombie detection, resume spinner, cancel mid-download. Windows buffering fix implemented (untested, needs Windows machine). aria2c is now the default (`use_aria2c: bool = True` in schema); hf-download is the pre-flight fallback when aria2c binary unavailable. Added `tests/test_aria2c_circuit.py` with `@pytest.mark.slow` on network classes + 4 static contract tests. **File before `fix/gguf-quality-scored`** (introduces `HfUrlResolver` base class). See pr-drafts/ |
| `feat/catppuccin-theme` | [#30](https://github.com/jdmanring/odysseus/issues/30) | Feature | Ready to file — see pr-drafts/feat-catppuccin-theme.md |
| `feat/ai-documentation-system` | [#18](https://github.com/jdmanring/odysseus/issues/18) | Docs | Ready to file — see pr-drafts/ |
| `feat/qt-native-linux-app` | [#14](https://github.com/jdmanring/odysseus/issues/14) | Feature | **File-ready (single squashed commit); pending only the standard issue-first + screenshot at filing.** Carries the full Qt-wrapper memory stack (#106 forcible-purge + RSS-ceiling, #112 host telemetry, #116 low-resource profile, #120 graduated PSI / `qt_psi.py`), folded 2026-06-26 because `qt_wrapper.py` is a *new* file (ships memory-managed, not patched after). **Gate 1 (history) RESOLVED:** squashed the 44-commit branch to one coherent commit (`feat(linux): native Linux desktop app … with renderer memory management`) on the `upstream-mirror` fork point; verified the squash changed only history (`git diff backup/feat-qt-pre-squash feat/qt-native-linux-app` is *only* the intended `docs/fork/` drops). The squash also dropped 8 fork-only files (debug screenshots + an unrelated deprecated draft) that had contaminated the branch. Voice pass applied (no em-dashes in code, log lines, tests, or the PR draft). **Gate 2 (verification) RESOLVED:** the `CRITICAL → _purge_renderer('psi-critical')` dispatch is now unit-tested deterministically via `qt_psi.dispatch_psi_action` (a headless harness and a cgroup-capped stress-ng cannot reach real CRITICAL), and the live app proves the integration (drain runs; `_purge_renderer` purges; `[PSI]` heartbeats with real `rss_mb`). Backups: `backup/feat-qt-native-linux-app-prefold` (pre-fold), `backup/feat-qt-pre-squash` (pre-squash). At file time, rebase onto then-current `upstream-mirror` per the standing requirement. See pr-drafts/feat-qt-native-linux-app.md |
| `fix/gpu-compositor-flicker` | [#32](https://github.com/jdmanring/odysseus/issues/32) | Bug | Ready to file — see pr-drafts/fix-gpu-compositor-flicker.md |
| `fix/css-render-perf` | [#33](https://github.com/jdmanring/odysseus/issues/33) | Perf | Ready to file — see pr-drafts/fix-css-render-perf.md |
| `fix/hf-token-env-fallback` | [#34](https://github.com/jdmanring/odysseus/issues/34) | Bug | Superseded — upstream landed same fix in #3459 (synced 2026-06-12). Draft moved to `deprecated/`. Do not file. |
| `feat/gh-cli-detection` | [#5](https://github.com/jdmanring/odysseus/issues/5) | Feature | Ready to file — module-level cache added (subprocess called once per server lifetime); 12 tests (11 behavioral + 1 cache test). See pr-drafts/feat-gh-cli-detection.md |
| `fix/gguf-quality-scored` | [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29) | Feature | Ready to file after `feat/aria2c-downloader` (extends `HfUrlResolver` — gguf discovery methods). Added `tests/test_gguf_scoring.py` with 20 pure-function tests (no network). See pr-drafts/feat-gguf-discovery.md |
| `fix/tool-code-pycall-parsing` | [#35](https://github.com/jdmanring/odysseus/issues/35) | Bug | Ready to file — see pr-drafts/fix-tool-code-pycall-parsing.md |
| `fix/longcat-tool-parsing` | [#38](https://github.com/jdmanring/odysseus/issues/38) | Bug | Ready to file — added `tests/test_longcat_tool_parsing.py` (13 tests, covers both Variant A/B, unknown-name pass-through behavior documented). See pr-drafts/fix-longcat-tool-parsing.md |
| `fix/google-compat-toolcalls` | [#39](https://github.com/jdmanring/odysseus/issues/39) | Bug | **Do not file: premise disproved, branch deleted (2026-06-18).** A live API test showed Google's compat endpoint sends snake_case `tool_calls` per spec, not camelCase; the fix chased a non-existent bug. The real related quirk (`finish_reason: stop`) does not affect Odysseus (tracked #52). See active-work.md; draft retained for history only. |
| `feat/logging` | [#31](https://github.com/jdmanring/odysseus/issues/31) | Feature | Ready to file — infrastructure and callsites combined in one PR. See pr-drafts/feat-logging.md |
| `fix/workspace-shell-access` | [#47](https://github.com/jdmanring/odysseus/issues/47) | Bug | **Folded into develop; standalone branch deleted.** The web_search/web_fetch workspace behavior is on develop and `tests/test_workspace_web_search_tools.py` passes there. To file upstream, recreate a clean branch from `upstream-mirror`. Entry was stale. |
| `fix/untrusted-tool-result-header` | [#48](https://github.com/jdmanring/odysseus/issues/48) | Bug | Ready to file — single clean commit. Fixes false-positive refusals introduced by upstream #1629 (2026-06-16). File upstream issue first. See pr-drafts/fix-untrusted-tool-result-header.md |
| `fix/api-token-utcnow-deprecated` | [#51](https://github.com/jdmanring/odysseus/issues/51) | Bug | Ready to file — single clean commit, 2 lines changed. Follow-up to upstream 790ef81b (missed instance). File upstream issue first. See pr-drafts/fix-api-token-utcnow-deprecated.md |
| `fix/chat-auto-scroll-threshold` | [#49](https://github.com/jdmanring/odysseus/issues/49) | Bug | Ready to file — single clean commit. Adaptive threshold replaces rigid 300px guard in _smoothScrollStep(). File upstream issue first. See pr-drafts/fix-chat-auto-scroll-threshold.md |
| `feat/thinking-overlay` | [#133](https://github.com/jdmanring/odysseus/issues/133) | Enhancement | Ready to file — single clean commit (`9d959850`) from `upstream-mirror`; cherry-picked to develop (`163cbc52`, `-x`). Thinking indicator becomes a zero-footprint sticky overlay (height:0 sticky anchor + absolute bubble): document bottom never moves on show/replace/remove (measured: scrollHeight and pinned bottom-distance identical), indicator stays visible when scrolled up, role=status for AT, no compositor-layer properties. 7 static guards. File upstream issue first. See pr-drafts/feat-thinking-overlay.md |

## Process-stack perf candidates (audit section E, 2026-06-25)

Three fork issues filed from `docs/fork/perf-audit-2026-06.md`. Their **branch origin
differs by whether the touched files exist on `upstream-mirror`** — getting this wrong
contaminates the branch:

| Fork issue | Touches | Origin / home | Independent? | Maps upstream to |
|---|---|---|---|---|
| [#111](https://github.com/jdmanring/odysseus/issues/111) lazy-connect cold MCP | `src/builtin_mcp.py`, `src/mcp_manager.py` (both on `upstream-mirror`) | **`perf/mcp-lazy-connect`** (cut from `upstream-mirror`; implemented, cherry-picked to develop; draft issue+PR staged; research in `mcp-lazy-connect-research.md`) | **Yes** | #2140, #3824; ROADMAP email-perf. #4812 reconciled (complementary; file after #4812, route eager branch through its `_spawn_bg` — see research doc) |
| [#112](https://github.com/jdmanring/odysseus/issues/112) host VmRSS telemetry | `qt_wrapper.py` (**not** on `upstream-mirror`) | **folded into `feat/qt-native-linux-app` (#14)** with the rest of the memory stack, 2026-06-26 | No — **part of #14** | ships inside the #14 PR |
| [#113](https://github.com/jdmanring/odysseus/issues/113) `--no-access-log` | `qt_wrapper.py` / `mac_wrapper.py` / `windows_wrapper.py` (**not** on `upstream-mirror`) | **DONE** on each `feat/qt-native-{linux,macos,windows}-app` branch; cherry-picked to develop (guard test on develop) | No — **rides each platform PR** | folds into #14 (linux) + macos/windows PRs. Real fix is `--no-access-log` (uvicorn default is ON) |

### Idle-quiescence candidates (audit C3 / #117, 2026-06-25)

| Fork issue | Branch | Touches | Status |
|--------|--------|---------|--------|
| [#117](https://github.com/jdmanring/odysseus/issues/117) (notes instance) | `fix/notes-quick-idle-quiescence` | `static/js/ui.js`, `static/style.css` | **DONE** — from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged; adds reusable `html.app-blurred` primitive. Independent. |
| [#115](https://github.com/jdmanring/odysseus/issues/115) | `fix/research-orbit-quiescence` | `static/js/research/panel.js`, `static/style.css` | **DONE — orbit ring REMOVED** (not just optimized): a compositor version needed a ~32 MB GPU layer for decoration, and VRAM is the model's context. From `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. Independent. |
| [#118](https://github.com/jdmanring/odysseus/issues/118) (audit D1+D2) | `fix/timer-visibility-gating` | `modalManager.js`, `emailInbox.js`, `tasks.js` | **DONE** — visibility-gate background timers; from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. Independent. |
| [#119](https://github.com/jdmanring/odysseus/issues/119) (audit D3) | `fix/sigcache-lru-bound` | `static/js/document.js` | **DONE** — LRU-bound `_sigCache`; from `upstream-mirror`, cherry-picked to develop; draft issue+PR staged. Independent. |

**✓ Staging gap RESOLVED (2026-06-26) — folded into #14.** The memory work
(`perf/renderer-memory-reclaim` = #106 forcible-purge/idle-purge/GC-catchup + #112 host
telemetry + #116 low-resource profile, and `perf/qt-psi-graduated-reclaim` = #120 graduated
PSI / `qt_psi.py`) could not be a standalone `upstream-mirror` PR because `qt_wrapper.py` is
introduced by #14. **Decision: fold all of it into #14** — `qt_wrapper.py` is a *new* file,
so the feature must ship in its correct memory-managed shape rather than be introduced naive
and patched by a follow-up series (which would also ask a reviewer to accept the
simulatePressure no-op that #106's research disproved). 13 commits were cherry-picked onto
`feat/qt-native-linux-app` (clean; backup `backup/feat-qt-native-linux-app-prefold`); the #14
PR draft was rewritten to the shipped design. `develop` already carries all of this work via
its own cherry-picks. The `perf/renderer-memory-reclaim` and `perf/qt-psi-graduated-reclaim`
branches are now **superseded by #14** for upstream purposes (retained as history; safe to
delete once #14 is filed). **#113** keeps its own row: the Linux part is in #14, the
mac/windows parts ride their platform PRs. **Do not file #14 until its upstream fate is
settled** (issue first, per CONTRIBUTING).

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
