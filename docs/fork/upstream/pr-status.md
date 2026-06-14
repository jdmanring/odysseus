# Upstream Contributions

One branch per contribution. Each branch is built from `upstream-mirror` and contains
only the changes for that one fix or feature — nothing fork-specific.

**Never push to upstream remote. Never file issues or PRs upstream without explicit
per-action authorization. Agents stage; you file.**

---

## Branch → Issue Map

| Branch | Issue | Type | Status |
|--------|-------|------|--------|
| `fix/agent-tool-budget` | [#10](https://github.com/jdmanring/odysseus/issues/10) | Bug | Ready to file — see pr-drafts/ |
| `fix/pytest-timeout-dependency` | [#6](https://github.com/jdmanring/odysseus/issues/6) | Bug | Ready to file — see pr-drafts/ |
| `fix/searxng-json-docs` | [#8](https://github.com/jdmanring/odysseus/issues/8) | Bug/Docs | Ready to file — see pr-drafts/ |
| `fix/basicsr-python314-compat` | [#9](https://github.com/jdmanring/odysseus/issues/9) | Bug | Superseded — upstream PR #3741 fixes the same bug, integrated into `cookbook_helpers.py` with tests (better approach). Do not file. Delete branch once #3741 merges into upstream-mirror. |
| `fix/streamingtts-scope` | [#11](https://github.com/jdmanring/odysseus/issues/11) | Bug | Ready to file — see pr-drafts/ |
| `refactor/assets-move` | [#19](https://github.com/jdmanring/odysseus/issues/19) | Refactor | Ready to file — see pr-drafts/ |
| `fix/tool-result-role` | [#4](https://github.com/jdmanring/odysseus/issues/4) | Bug | Ready to file — see pr-drafts/fix-tool-result-role.md |
| `fix/dom-oom-virtualization` | [#2](https://github.com/jdmanring/odysseus/issues/2) | Bug | Ready to file — single clean commit, scroll verified. **File after `fix/streamingtts-scope`** (depends on `let streamingTTS` hoist being present). File upstream issue first. See pr-drafts/ |
| `feat/aria2c-downloader` | [#12](https://github.com/jdmanring/odysseus/issues/12) + [#23](https://github.com/jdmanring/odysseus/issues/23) | Feature | Verified (2026-06-12): pause/resume (single+multi-file), split-file size, menu toggle, clear-finished, zombie detection, resume spinner, cancel mid-download. Windows buffering fix implemented (untested, needs Windows machine). **File before `fix/gguf-quality-scored`** (introduces `HfUrlResolver` base class). See pr-drafts/ |
| `feat/catppuccin-theme` | [#30](https://github.com/jdmanring/odysseus/issues/30) | Feature | Ready to file — see pr-drafts/feat-catppuccin-theme.md |
| `feat/ai-documentation-system` | [#18](https://github.com/jdmanring/odysseus/issues/18) | Docs | Ready to file — see pr-drafts/ |
| `feat/qt-native-linux-app` | [#14](https://github.com/jdmanring/odysseus/issues/14) | Feature | Ready to file — see pr-drafts/feat-qt-native-linux-app.md |
| `fix/gpu-compositor-flicker` | [#32](https://github.com/jdmanring/odysseus/issues/32) | Bug | Ready to file — see pr-drafts/fix-gpu-compositor-flicker.md |
| `fix/css-render-perf` | [#33](https://github.com/jdmanring/odysseus/issues/33) | Perf | Ready to file — see pr-drafts/fix-css-render-perf.md |
| `fix/hf-token-env-fallback` | [#34](https://github.com/jdmanring/odysseus/issues/34) | Bug | Superseded — upstream landed same fix in #3459 (synced 2026-06-12). Draft moved to `deprecated/`. Do not file. |
| `feat/gh-cli-detection` | [#5](https://github.com/jdmanring/odysseus/issues/5) | Feature | Ready to file — see pr-drafts/feat-gh-cli-detection.md |
| `fix/gguf-quality-scored` | [#24](https://github.com/jdmanring/odysseus/issues/24) + [#29](https://github.com/jdmanring/odysseus/issues/29) | Feature | Ready to file after `feat/aria2c-downloader` (extends `HfUrlResolver` — gguf discovery methods). See pr-drafts/feat-gguf-discovery.md |
| `fix/tool-code-pycall-parsing` | [#35](https://github.com/jdmanring/odysseus/issues/35) | Bug | Ready to file — see pr-drafts/fix-tool-code-pycall-parsing.md |
| `fix/longcat-tool-parsing` | [#38](https://github.com/jdmanring/odysseus/issues/38) | Bug | Ready to file — see pr-drafts/fix-longcat-tool-parsing.md |
| `fix/google-compat-toolcalls` | [#39](https://github.com/jdmanring/odysseus/issues/39) | Bug | Ready to file — see pr-drafts/fix-google-compat-toolcalls.md |
| `feat/logging` | [#31](https://github.com/jdmanring/odysseus/issues/31) | Feature | Ready to file — infrastructure and callsites combined in one PR. See pr-drafts/feat-logging.md |

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
