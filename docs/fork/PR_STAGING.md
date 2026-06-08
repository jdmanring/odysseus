# Upstream Contribution Staging Index

Full draft docs (issue + PR templates, ready for copy-paste) are in
`docs/fork/upstream/drafts/`.

**Workflow:** Read `docs/fork/upstream/how-to-contribute.md` before filing anything.
The short version: file the issue first, get the number, then open the PR.
**Agents never file upstream issues or PRs directly — James does.**

---

## Upstream Contributions

| # | Title | Type | Issue | PR | Tests | Fork Status |
|---|-------|------|-------|----|-------|-------------|
| [01](drafts/01-hf-token-persistence.md) | HF Token Not Saved Outside Cookbook Tab | Bug | Not filed | Not opened | None | No fix yet |
| [02](drafts/02-pytest-timeout-dependency.md) | pytest-timeout Not Declared as Dependency | Bug | Not filed | Not opened | N/A — `pyproject.toml` change | N/A |
| [03](drafts/03-searxng-json-docs.md) | SearXNG JSON Format Undocumented | Bug/Docs | Not filed | Not opened | N/A — `.env.example` change | Documented internally |
| [04](drafts/04-basicsr-python314-compat.md) | realesrgan / basicsr Broken on Python 3.14 | Bug | Not filed | Not opened | N/A — install script patch | Patched via `install-basicsr.sh` |
| [05](drafts/05-agent-tool-budget.md) | agent_max_tool_calls Defaults to 0 | Bug | Not filed | Not opened | None — needs a settings default test | Fixed in `data/settings.json` |
| [06](drafts/06-dom-oom-virtualization.md) | Renderer OOM — No DOM Virtualization | Bug | Not filed | Not opened | Manual steps documented in draft — visual verification required before filing | Fix applied to `develop` — screenshots needed before filing |
| [07](drafts/07-streamingtts-scope-fix.md) | streamingTTS ReferenceError in catch Block | Bug | Not filed | Not opened | Manual steps documented in draft — single-line fix, no automated test | Fixed in `develop` (commit `9fabdc6`) |
| [08](drafts/08-aria2c-downloader.md) | aria2c Downloader — Replace hf_transfer | Feature | Not filed | Not opened | `tests/test_aria2c_circuit.py` — 8 tests: BinManager install, executable check, `--version` smoke, URL resolution, real download of `gpt2/tokenizer.json`, resume idempotency, PATH fallback | Implemented in `develop` |

---

## Filing Readiness

| # | Ready to file? | Blocker |
|---|---------------|---------|
| 01 | No | No fix implemented yet |
| 02 | Yes | — |
| 03 | Yes | — |
| 04 | Yes | — |
| 05 | No | No automated test for the settings default |
| 06 | No | Fix applied to `develop` — take screenshots per PR checklist, then file |
| 07 | Yes | — |
| 08 | Yes | Run `python -m pytest tests/test_aria2c_circuit.py -v` + screenshot of running download before filing |

---

## Internal (Fork-Only) Contributions

Tracked in `docs/fork/fork-only/`. Not appropriate for upstream (Qt integration,
Linux native app, sync tooling).

| # | Title | Status |
|---|-------|--------|
| [01](../fork-only/01-native-linux-app.md) | Native Linux Application (Qt Wrapper) | Active development |
| [02](../fork-only/02-qwebengine-localstorage.md) | QWebEngineView localStorage Persistence | Complete |
| [03](../fork-only/03-sync-pipeline-tooling.md) | Upstream Sync Pipeline Tooling | Complete |
