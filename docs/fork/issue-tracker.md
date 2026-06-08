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
3. Do the work on that branch (upstream-candidate: one clean commit, fork files only)
4. Merge/cherry-pick to develop; close the issue when fix is verified
5. If upstream-candidate: update docs/fork/upstream/pr-status.md — branch IS the staging
```

Full branch procedure is in `docs/dev/git-branch-workflow.md`.

Agents do not create branches without a corresponding issue. If no issue exists for the
work, create one first.

---

## Issue Labels

| Label | Meaning |
|-------|---------|
| `upstream-candidate` | Fix/feature worth contributing to `pewdiepie-archdaemon/odysseus` |
| `fork-only` | Work that belongs only in this fork (Qt wrapper, sync tooling, docs) |
| `bug` | Something broken |
| `enhancement` | New feature or improvement |
| `documentation` | Docs work |

---

## Current Open Issues

| # | Title | Label | Branch |
|---|-------|-------|--------|
| [#4](https://github.com/jdmanring/odysseus/issues/4) | Tool results misattributed as user messages | upstream-candidate | `fix/tool-result-role` |
| [#5](https://github.com/jdmanring/odysseus/issues/5) | gh CLI unusable in Odysseus agent context | bug | no branch yet |
| [#6](https://github.com/jdmanring/odysseus/issues/6) | pytest-timeout not declared as dependency | upstream-candidate | `fix/pytest-timeout-dependency` |
| [#7](https://github.com/jdmanring/odysseus/issues/7) | HF token not saved outside Cookbook tab | upstream-candidate | `fix/hf-token-persistence` |
| [#8](https://github.com/jdmanring/odysseus/issues/8) | SearXNG JSON output not documented | upstream-candidate | `fix/searxng-json-docs` |
| [#9](https://github.com/jdmanring/odysseus/issues/9) | realesrgan / basicsr broken on Python 3.14 | upstream-candidate | `fix/basicsr-python314-compat` |
| [#10](https://github.com/jdmanring/odysseus/issues/10) | agent_max_tool_calls defaults to 0 | upstream-candidate | `fix/agent-tool-budget` |
| [#12](https://github.com/jdmanring/odysseus/issues/12) | Replace hf_transfer with aria2c | upstream-candidate | `feat/aria2c-downloader` |
| [#14](https://github.com/jdmanring/odysseus/issues/14) | Native Linux desktop app (Qt wrapper) | upstream-candidate | `feat/qt-native-linux-app` |
| [#15](https://github.com/jdmanring/odysseus/issues/15) | Upstream sync pipeline | fork-only | `feat/upstream-sync-pipeline` |
| [#16](https://github.com/jdmanring/odysseus/issues/16) | Download UI overhaul (depends on #12) | upstream-candidate | `feat/download-ui-overhaul` |
| [#18](https://github.com/jdmanring/odysseus/issues/18) | AI-first documentation system (fork docs) | fork-only | `feat/ai-documentation-system` |
| [#21](https://github.com/jdmanring/odysseus/issues/21) | AGENTS.md — AI agent entry point (upstream) | upstream-candidate | `upstream/agents-md` (to build) |
| [#22](https://github.com/jdmanring/odysseus/issues/22) | AI_ONBOARDING.md — architecture primer (upstream) | upstream-candidate | `upstream/ai-onboarding` (to build) |
| [#19](https://github.com/jdmanring/odysseus/issues/19) | Move media assets from docs/ to assets/ | upstream-candidate | `refactor/assets-move` |

For upstream filing status (which are ready, which need screenshots, blockers):
`docs/fork/upstream/pr-status.md`

**Note:** #16 (Download UI) has no upstream staging draft yet. Draft 08 covers the aria2c
backend only and explicitly defers the UI. Create the draft for #16 after #12 merges upstream.

**Note:** #5 (gh CLI non-interactive) is a genuine Odysseus bug — the agent cannot use gh
CLI because gh requires interactive prompts the agent cannot satisfy. Needs a fix or
documented workaround inside Odysseus.
