# Upstream Contributions

One branch per contribution. Each branch is built from `upstream-mirror` and contains
only the changes for that one fix or feature — nothing fork-specific.

**Never push to upstream remote. Never file issues or PRs upstream without James's
explicit per-action authorization. Agents stage; James files.**

---

## Branch → Issue Map

| Branch | Issue | Type | Status |
|--------|-------|------|--------|
| `fix/agent-tool-budget` | [#10](https://github.com/jdmanring/odysseus/issues/10) | Bug | Ready to file — see pr-drafts/ |
| `fix/pytest-timeout-dependency` | [#6](https://github.com/jdmanring/odysseus/issues/6) | Bug | Ready to file — see pr-drafts/ |
| `fix/searxng-json-docs` | [#8](https://github.com/jdmanring/odysseus/issues/8) | Bug/Docs | Ready to file — see pr-drafts/ |
| `fix/basicsr-python314-compat` | [#9](https://github.com/jdmanring/odysseus/issues/9) | Bug | Ready to file — see pr-drafts/ |
| `fix/streamingtts-scope` | [#11](https://github.com/jdmanring/odysseus/issues/11) | Bug | Ready to file — see pr-drafts/ |
| `refactor/assets-move` | [#19](https://github.com/jdmanring/odysseus/issues/19) | Refactor | Ready to file — see pr-drafts/ |
| `fix/tool-result-role` | [#4](https://github.com/jdmanring/odysseus/issues/4) | Bug | Ready to file — see pr-drafts/fix-tool-result-role.md |
| `fix/dom-oom-virtualization` | [#2](https://github.com/jdmanring/odysseus/issues/2) | Bug | Ready to file — single clean commit, scroll verified. File upstream issue first, then open PR. See pr-drafts/ |
| `feat/aria2c-downloader` | [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | Feature | Verified (2026-06-12): pause/resume (single+multi-file), split-file size, menu toggle, clear-finished, zombie detection, resume spinner, cancel mid-download. Windows buffering fix implemented (untested, needs Windows machine) — see pr-drafts/ |
| `feat/catppuccin-theme` | [#30](https://github.com/jdmanring/odysseus/issues/30) | Feature | Ready to file — see pr-drafts/feat-catppuccin-theme.md |
| `feat/ai-documentation-system` | [#18](https://github.com/jdmanring/odysseus/issues/18) | Docs | Ready to file — see pr-drafts/ |
| `feat/qt-native-linux-app` | [#14](https://github.com/jdmanring/odysseus/issues/14) | Feature | Ready to file — see pr-drafts/feat-qt-native-linux-app.md |
| `fix/gpu-compositor-flicker` | [#32](https://github.com/jdmanring/odysseus/issues/32) | Bug | Ready to file — see pr-drafts/fix-gpu-compositor-flicker.md |
| `fix/css-render-perf` | [#33](https://github.com/jdmanring/odysseus/issues/33) | Perf | Ready to file — see pr-drafts/fix-css-render-perf.md |
| `fix/hf-token-persistence` | [#7](https://github.com/jdmanring/odysseus/issues/7) | Bug | Superseded — core bug fixed upstream (#3459, synced). See #34. |
| `fix/hf-token-env-fallback` | [#34](https://github.com/jdmanring/odysseus/issues/34) | Bug | Superseded — upstream landed same fix in #3459 (synced 2026-06-12). Also updates `fix/hf-token-persistence` note: the upstream utility `load_stored_hf_token()` in `cookbook_helpers.py` covers both issues. |
| `feat/github-integration` | [#5](https://github.com/jdmanring/odysseus/issues/5) | Feature | Ready to file — see pr-drafts/ |
| `fix/gguf-quality-scored` | [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29) | Feature | Ready to file — see pr-drafts/feat-gguf-discovery.md |
| `feat/logging-core` | [#31](https://github.com/jdmanring/odysseus/issues/31) | Feature | Ready to file — see pr-drafts/feat-logging-core.md |
| `feat/logging-timing` | [#31](https://github.com/jdmanring/odysseus/issues/31) | Feature | Ready to file after core — see pr-drafts/feat-logging-timing.md |

## PR Drafts

Staged PR descriptions live in `docs/fork/upstream/pr-drafts/`, one file per branch
(named after the branch with `/` → `-`). Each draft contains the proposed title,
description body, and filing notes for James. The description is written for upstream
reviewers — it does not assume they have seen our fork's issue tracker.

## Filing Procedure

1. File a GitHub issue on `pewdiepie-archdaemon/odysseus` (James does this)
2. Add the upstream issue number to the issue description here
3. Open PR from `jdmanring/odysseus:<branch>` → `pewdiepie-archdaemon/odysseus:dev`
4. All PRs target `dev`, not `main`

## Fork-Only Work (not going upstream)

| Branch | Issue | Notes |
|--------|-------|-------|
| `feat/upstream-sync-pipeline` | [#15](https://github.com/jdmanring/odysseus/issues/15) | Manages fork/upstream relationship — not applicable upstream |
