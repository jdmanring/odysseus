# Issue Tracker

All issues for this fork are on GitHub: https://github.com/jdmanring/odysseus/issues

---

## Workflow

**Issue first, branch second.** Every piece of work — bugs, features, upstream contributions,
fork-only changes — starts with a GitHub Issue on `jdmanring/odysseus`. The branch is named
to match the issue's subject. This is the single source of truth for what work exists,
what its status is, and what branch carries the fix.

```
1. Create issue on https://github.com/jdmanring/odysseus/issues
2. Determine branch origin:
   - upstream-candidate → branch from upstream-mirror
   - fork-only          → branch from develop
   - upstream-candidate work on a file that exists only on develop (a staged
     contribution not yet upstream) → branch from develop. File location forces
     the origin, NOT the classification — the work is still upstream-candidate
     and folds into the staged branch before its PR is filed.
3. Do the work on that branch (upstream-candidate: one clean commit, fork files only)
4. Merge/cherry-pick to develop. Closing the issue depends on classification:
   fork-only closes when the fix is verified on develop; upstream-candidate
   STAYS OPEN until the upstream PR carrying the fix is filed — the filed PR
   is the only thing that closes it.
5. If upstream-candidate:
   - Write PR draft in docs/fork/upstream/pr-drafts/<name>.md
   - Write issue draft in docs/fork/upstream/issue-drafts/<name>.md
   - Update docs/fork/upstream/pr-status.md with status
   - File: issue first (from issue-drafts/), then PR (from pr-drafts/)
```

Full branch procedure is in `docs/dev/git-branch-workflow.md`.

Agents do not create branches without a corresponding issue. If no issue exists for the
work, create one first.

---

## Issue Labels

| Label | Meaning |
|-------|---------|
| `upstream-candidate` | Default for almost all work — fixes, features, docs, new files |
| `fork-only` | Narrow exception: sync pipeline, fork CI, fork management docs only |
| `bug` | Something broken |
| `enhancement` | New feature or improvement |
| `documentation` | Docs work |

**Label guidance:** When in doubt, use `upstream-candidate`. The `fork-only` label applies
only to work that manages the fork/upstream relationship itself — the sync pipeline
(`tooling/sync-upstreams/`), `.github/workflows/sync-upstream.yml`, and the docs in
`docs/fork/` and `docs/dev/git-branch-workflow.md`. Everything else — including the Qt
wrapper, the download stack, AI documentation, and application bug fixes — is
`upstream-candidate` regardless of how large or fork-specific it feels.

---

## Current Open Issues

| # | Title | Label | Branch |
|---|-------|-------|--------|
| [#3](https://github.com/jdmanring/odysseus/issues/3) | External links don't navigate in Qt wrapper | upstream-candidate | `feat/qt-native-linux-app` |
| [#4](https://github.com/jdmanring/odysseus/issues/4) | Tool results misattributed as user messages | upstream-candidate | `fix/tool-result-role` |
| [#5](https://github.com/jdmanring/odysseus/issues/5) | gh CLI unusable in Odysseus agent context | upstream-candidate | `feat/github-integration` |
| [#7](https://github.com/jdmanring/odysseus/issues/7) | HF token not saved outside Cookbook tab | upstream-candidate | `fix/hf-token-persistence` |
| [#9](https://github.com/jdmanring/odysseus/issues/9) | realesrgan / basicsr broken on Python 3.14 | upstream-candidate | `fix/basicsr-python314-compat` |
| [#12](https://github.com/jdmanring/odysseus/issues/12) | Replace hf_transfer with aria2c | upstream-candidate | `feat/aria2c-downloader` |
| [#14](https://github.com/jdmanring/odysseus/issues/14) | Native Linux desktop app (Qt wrapper) | upstream-candidate | `feat/qt-native-linux-app` |
| [#15](https://github.com/jdmanring/odysseus/issues/15) | Upstream sync pipeline | fork-only | `feat/upstream-sync-pipeline` |
| [#16](https://github.com/jdmanring/odysseus/issues/16) | Download UI overhaul (depends on #12) | upstream-candidate | `feat/download-ui-overhaul` |
| [#18](https://github.com/jdmanring/odysseus/issues/18) | AI-first documentation system | upstream-candidate | `feat/ai-documentation-system` (Ready to File) |
| [#19](https://github.com/jdmanring/odysseus/issues/19) | Move media assets from docs/ to assets/ | upstream-candidate | `refactor/assets-move` |
| [#20](https://github.com/jdmanring/odysseus/issues/20) | BinManager test suite | upstream-candidate | `develop` (direct — goes upstream with #12) |
| [#21](https://github.com/jdmanring/odysseus/issues/21) | AI_RULES.md — AI agent rules (upstream) | upstream-candidate | `feat/ai-documentation-system` (Ready to File) |
| [#22](https://github.com/jdmanring/odysseus/issues/22) | AI_CONTEXT.md — architecture primer (upstream) | upstream-candidate | `feat/ai-documentation-system` (Ready to File) |
| [#29](https://github.com/jdmanring/odysseus/issues/29) | GGUF source resolution returns low-quality results | upstream-candidate | `fix/gguf-quality-scored` |
| [#148](https://github.com/jdmanring/odysseus/issues/148) | GGUF resolver substitutes a completely unrelated model when no true quant exists | upstream-candidate | `fix/gguf-quality-scored` (`bf51d93e`; develop `e5b41dcc`) |
| [#149](https://github.com/jdmanring/odysseus/issues/149) | HW-Fit fabricates Q4_K_M/llama.cpp identity for safetensors models with no GGUF | upstream-candidate | `fix/hwfit-scan-honesty` (`3c047f60`; develop `1aa7a4fe`) |
| [#150](https://github.com/jdmanring/odysseus/issues/150) | HW-Fit lists unservable architectures as runnable — servability gate | upstream-candidate | `fix/hwfit-scan-honesty` (`16b37659`; develop `792df19f`) |
| [#151](https://github.com/jdmanring/odysseus/issues/151) | HW-Fit list: sort refetch lag; quant filter leaks Q4_K_M Ollama rows | upstream-candidate | `fix/hwfit-scan-honesty` (`eefc1861`; develop `9e4fd14b`) |
| [#152](https://github.com/jdmanring/odysseus/issues/152) | Per-frame decoration cost: full-screen backdrop-filter flicker (QtWebEngine), standing will-change layers | upstream-candidate | **Split by theme across two existing staged branches** (rebuilt 2026-07-20 after a contaminated first pass — a whole-file conflict resolution had imported develop's entire style.css; now 55 on-theme lines): backdrop-filter work on `fix/gpu-compositor-flicker` (`4d11aa39`..`5d7e3ae3`), will-change work on `fix/css-render-perf` (`fa8faa54`, guard scoped to this PR's three removals — a global will-change guard can't pass on the upstream baseline, other staged branches own the remaining removals; the global guard lives on develop). Develop: `675fe400`, `be191d9d`, `8613e26a`, `10759b67`. The clear-all flicker was a develop *regression*: upstream's `92daf4e5` re-added blur the June branch had removed, and the branch guard was branch-only — develop's `test_css_no_fullscreen_backdrop_blur.py` closes that. |
| [#30](https://github.com/jdmanring/odysseus/issues/30) | feat: add Catppuccin Mocha theme with Odysseus color palette | upstream-candidate | `feat/catppuccin-theme` |
| [#31](https://github.com/jdmanring/odysseus/issues/31) | World-class structured logging system | upstream-candidate | 2 PRs: `feat/logging-core`, `feat/logging-timing` |
| [#120](https://github.com/jdmanring/odysseus/issues/120) | qt_wrapper graduated PSI monitor (some/full, tunable thresholds) | upstream-candidate | implemented on `perf/qt-psi-graduated-reclaim`; **folded into `feat/qt-native-linux-app` (#14)** 2026-06-26 — ships inside the #14 PR with the rest of the memory stack |
| [#121](https://github.com/jdmanring/odysseus/issues/121) | Installed models don't grey out: duplicated downloaded-detection matcher | upstream-candidate | **Implemented** on `fix/model-downloaded-detection` (from `upstream-mirror`, `c17973f2`); cherry-picked to develop. One canonical `static/js/model/downloaded.js` predicate; all sites consolidated; node test locks the better-quant case + guard test blocks reintroduction; plus base-name matching so discovered community quants (no gguf_sources) gray out too (verified against the real on-disk download set). Plan: `docs/fork/plans/model-downloaded-detection-consolidation.md` |
| [#122](https://github.com/jdmanring/odysseus/issues/122) | Add API Models provider list not alphabetical (static order drift) | upstream-candidate | **Implemented** on `fix/provider-picker-alpha-sort` (from `upstream-mirror`); cherry-picked to develop. Render-time sort in `_renderPickerMenu`, append-proof. |
| [#123](https://github.com/jdmanring/odysseus/issues/123) | Persist catalog<->download association for discovered models (retire client base-name heuristic) | upstream-candidate | needs branch (from `upstream-mirror`). Root-cause for #121's client heuristic; relates to upstream #4049/#2342. Plan: the [#123 issue body](https://github.com/jdmanring/odysseus/issues/123) (provenance design: capture at download, store as update-surviving user state, exact join, heuristic as one-shot backfill). |

For upstream filing status (which are ready, which need screenshots, blockers):
`docs/fork/upstream/pr-status.md`

**Note:** #16 (Download UI) has no upstream staging draft yet. Create after #12 merges upstream.

**Note:** #5 (gh CLI non-interactive) is a genuine Odysseus bug — the agent cannot use gh
CLI because gh requires interactive prompts the agent cannot satisfy. Needs a fix or
documented workaround inside Odysseus.

**Note:** #21 and #22 track the upstream contributions of AI_RULES.md and AI_CONTEXT.md
respectively. The work lives on the `feat/ai-documentation-system` branch alongside #18.

---

## Closed Issues

Branches remain open for upstream PR filing. PR drafts are in `docs/fork/upstream/pr-drafts/`.

| # | Title | Branch | PR Draft |
|---|-------|--------|----------|
| [#2](https://github.com/jdmanring/odysseus/issues/2) | Renderer OOM — DOM virtualization | `fix/dom-oom-virtualization` | `fix-dom-oom-virtualization.md` — needs squash (2→1) |
| [#6](https://github.com/jdmanring/odysseus/issues/6) | pytest-timeout not declared as dependency | `fix/pytest-timeout-dependency` | `fix-pytest-timeout-dependency.md` |
| [#8](https://github.com/jdmanring/odysseus/issues/8) | SearXNG JSON output not documented | `fix/searxng-json-docs` | `fix-searxng-json-docs.md` |
| [#10](https://github.com/jdmanring/odysseus/issues/10) | agent_max_tool_calls defaults to 0 | `fix/agent-tool-budget` | `fix-agent-tool-budget.md` |
| [#11](https://github.com/jdmanring/odysseus/issues/11) | streamingTTS ReferenceError in catch | `fix/streamingtts-scope` | `fix-streamingtts-scope.md` |
| [#13](https://github.com/jdmanring/odysseus/issues/13) | Qt native color picker | part of `feat/qt-native-linux-app` | covered by #14 PR draft (upstream-candidate) |
| [#17](https://github.com/jdmanring/odysseus/issues/17) | QWebEngineView localStorage persistence | part of `feat/qt-native-linux-app` | covered by #14 PR draft (upstream-candidate) |
