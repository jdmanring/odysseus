# Upstream Contributions

One branch per contribution. Each branch is built from `upstream-mirror` and contains
only the changes for that one fix or feature — nothing fork-specific.

**Never push to upstream remote. Never file issues or PRs upstream without James's
explicit per-action authorization. Agents stage; James files.**

---

## Branch → Issue Map

| Branch | Issue | Type | Status |
|--------|-------|------|--------|
| `fix/agent-tool-budget` | [#10](https://github.com/jdmanring/odysseus/issues/10) | Bug | Ready to file |
| `fix/pytest-timeout-dependency` | [#6](https://github.com/jdmanring/odysseus/issues/6) | Bug | Ready to file |
| `fix/searxng-json-docs` | [#8](https://github.com/jdmanring/odysseus/issues/8) | Bug/Docs | Ready to file |
| `fix/basicsr-python314-compat` | [#9](https://github.com/jdmanring/odysseus/issues/9) | Bug | Ready to file |
| `fix/streamingtts-scope` | [#11](https://github.com/jdmanring/odysseus/issues/11) | Bug | Ready to file |
| `refactor/assets-move` | [#19](https://github.com/jdmanring/odysseus/issues/19) | Refactor | Ready to file |
| `fix/tool-result-role` | [#4](https://github.com/jdmanring/odysseus/issues/4) | Bug | Ready to file — rebuilt 2026-06-08 from current upstream-mirror |
| `fix/dom-oom-virtualization` | [#2](https://github.com/jdmanring/odysseus/issues/2) | Bug | Needs squash (2 commits → 1) + screenshot before filing |
| `feat/aria2c-downloader` | [#12](https://github.com/jdmanring/odysseus/issues/12) | Feature | Needs integration test run + screenshot |
| `feat/download-ui-overhaul` | [#16](https://github.com/jdmanring/odysseus/issues/16) | Feature | File after aria2c (#12) merges upstream |
| `feat/qt-native-linux-app` | [#14](https://github.com/jdmanring/odysseus/issues/14) | Feature | Needs screenshots before filing |
| `fix/hf-token-persistence` | [#7](https://github.com/jdmanring/odysseus/issues/7) | Bug | WIP — proper fix not implemented yet |

## Filing Procedure

1. File a GitHub issue on `pewdiepie-archdaemon/odysseus` (James does this)
2. Add the upstream issue number to the issue description here
3. Open PR from `jdmanring/odysseus:<branch>` → `pewdiepie-archdaemon/odysseus:dev`
4. All PRs target `dev`, not `main`

## Fork-Only Work (not going upstream)

| Branch | Issue | Notes |
|--------|-------|-------|
| `feat/upstream-sync-pipeline` | [#15](https://github.com/jdmanring/odysseus/issues/15) | Manages fork/upstream relationship — not applicable upstream |
