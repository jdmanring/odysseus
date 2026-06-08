# Upstream Contribution Staging Index

Full draft docs (issue + PR templates, ready for copy-paste) are in
`docs/fork/upstream/drafts/`.

**Workflow:** Read `docs/fork/upstream/how-to-contribute.md` before filing anything.
The short version: file the issue first, get the number, then open the PR.
**Agents never file upstream issues or PRs directly — James does.**

---

## Upstream Contributions

| # | Title | Type | Fork issue | Upstream issue | Branch | Fork Status |
|---|-------|------|-----------|----------------|--------|-------------|
| [01](upstream/drafts/01-hf-token-persistence.md) | HF Token Not Saved Outside Cookbook Tab | Bug | [#7](https://github.com/jdmanring/odysseus/issues/7) | Not filed | `fix/hf-token-persistence` | Workaround only — proper fix not yet implemented |
| [02](upstream/drafts/02-pytest-timeout-dependency.md) | pytest-timeout Not Declared as Dependency | Bug | [#6](https://github.com/jdmanring/odysseus/issues/6) | Not filed | `fix/pytest-timeout-dependency` | Fix on branch — `requirements.txt` |
| [03](upstream/drafts/03-searxng-json-docs.md) | SearXNG JSON Format Undocumented | Bug/Docs | [#8](https://github.com/jdmanring/odysseus/issues/8) | Not filed | `fix/searxng-json-docs` | Fix on branch — `.env.example` |
| [04](upstream/drafts/04-basicsr-python314-compat.md) | realesrgan / basicsr Broken on Python 3.14 | Bug | [#9](https://github.com/jdmanring/odysseus/issues/9) | Not filed | `fix/basicsr-python314-compat` | Fix on branch — `install-basicsr.sh` |
| [05](upstream/drafts/05-agent-tool-budget.md) | agent_max_tool_calls Defaults to 0 | Bug | [#10](https://github.com/jdmanring/odysseus/issues/10) | Not filed | `fix/agent-tool-budget` | Fix on branch — `src/settings.py` default changed to 20 |
| [06](upstream/drafts/06-dom-oom-virtualization.md) | Renderer OOM — No DOM Virtualization | Bug | [#2](https://github.com/jdmanring/odysseus/issues/2) | Not filed | `fix/dom-oom-virtualization` | Fix on `develop` — screenshots needed before filing |
| [07](upstream/drafts/07-streamingtts-scope-fix.md) | streamingTTS ReferenceError in catch Block | Bug | [#11](https://github.com/jdmanring/odysseus/issues/11) | Not filed | `fix/streamingtts-scope` | Fix on branch — cherry-picked from `develop` onto `upstream/dev` |
| [08](upstream/drafts/08-aria2c-downloader.md) | aria2c Downloader — Replace hf_transfer | Feature | [#12](https://github.com/jdmanring/odysseus/issues/12) | Not filed | `feat/aria2c-downloader` | Implemented on `develop` — tests + screenshot needed |
| [09](upstream/drafts/09-qt-native-linux-app.md) | Native Linux Desktop App (Qt Wrapper) | Feature | [#14](https://github.com/jdmanring/odysseus/issues/14) | Not filed | `feat/qt-native-linux-app` | Implemented on `develop` — screenshots needed; constants check required |
| [10](upstream/drafts/10-agents-md-ai-entry-point.md) | AGENTS.md — AI Agent Entry Point | Docs | [#21](https://github.com/jdmanring/odysseus/issues/21) | Not filed | `upstream/agents-md` (to build) | Staged — upstream-only content separated from fork rules |
| 11 | Move media assets from docs/ to assets/ | Refactor | [#19](https://github.com/jdmanring/odysseus/issues/19) | Not filed | `refactor/assets-move` | Branch ready — clean commit on `upstream/dev` |

---

## Filing Readiness

| # | Ready to file? | Blocker |
|---|---------------|---------|
| 01 | No | Proper fix not implemented — backend endpoint + JS needed |
| 02 | Yes | — |
| 03 | Yes | — |
| 04 | Yes | — |
| 05 | Yes | Review whether upstream wants `src/settings.py` change or a first-run migration |
| 06 | No | Screenshots per PR checklist (long session, scroll-up batch load, DevTools DOM count) |
| 07 | Yes | — |
| 08 | No | Run `python -m pytest tests/test_aria2c_circuit.py -v` + screenshot of download in progress |
| 09 | No | Screenshots (taskbar, external link → system browser, color picker dialog); audit `linux_wrapper.py` for hardcoded paths against `src/constants.py` before filing |
| 10 | Yes | Documentation only — no app changes, no screenshot needed. Build clean branch from `upstream-mirror`. |
| 11 | Yes | Branch already built clean from `upstream/dev` |

---

## Roadmap Alignment

Contributions that close or advance items in the upstream ROADMAP.md:

| # | Roadmap item addressed |
|---|----------------------|
| 06 | "SQUASH BUGS" — V8 Oilpan OOM crashes from unbounded DOM growth |
| 07 | "SQUASH BUGS" — ReferenceError aborting catch block on every stream error |
| 09 | "Fresh install smoke tests on Linux" — complete native Linux install and launch story |
| 09 | "SQUASH BUGS" — crash recovery for renderer OOM in the native app |
| 09 | "Cookbook reliability on other computers" — `build-linux-app.sh` reproducible Linux install |

---

## Fork-Only Work (not appropriate for upstream)

| Title | Status | Notes |
|-------|--------|-------|
| Upstream sync pipeline (`tooling/sync-upstreams/`) | Complete | Manages fork/upstream relationship — not applicable upstream |
| Docs system (`CLAUDE.md`, `AI_ONBOARDING.md`, `docs/fork/`) | Complete | Fork-specific AI agent orientation and fork management docs |
