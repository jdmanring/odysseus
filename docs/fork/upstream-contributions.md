# Planned Upstream Contributions

These are bugs and improvements discovered while setting up this fork that are
worth contributing back to `pewdiepie-archdaemon/odysseus`. Each entry includes
what was found, why it matters, and the proposed fix so an agent can implement
and open a PR without re-researching.

---

## 1. HF token not saved when set outside Cookbook tab

**File**: `static/js/cookbookRunning.js`, `static/js/cookbook.js`

**Bug**: When a user sets their HuggingFace token in Settings → Cookbook →
HuggingFace Token (or anywhere outside the Cookbook tab itself), the token is
held in `_envState.hfToken` but the `_syncToServer()` call that persists it to
disk is silently dropped.

The guard in `_syncToServer()` (cookbookRunning.js):
```js
if (!_envState || !Array.isArray(_envState.servers) || _envState.servers.length === 0) return;
```
`_envState.servers` is only hydrated when the Cookbook tab/component loads and
calls `GET /api/cookbook/state`. If the user enters the token from a different
settings panel before the Cookbook component has mounted, `servers` is still the
initial `[]` and the sync is silently skipped. The token is lost on next restart.

Evidence: `data/cookbook_state.json` has no `env.hfToken` entry even after the
user set one in the UI.

**Proposed fix**: Add a dedicated `POST /api/cookbook/env/hf-token` endpoint that
saves only the token, bypassing the full state sync and its hydration guard. The
Settings → Cookbook → HuggingFace Token field should call this endpoint directly
rather than relying on `_persistEnvState()` → `_syncToServer()`. Alternatively,
ensure the state is hydrated before `_syncToServer()` skips rather than silently
dropping writes.

---

## 2. Login username not remembered (QWebEngineView localStorage)

**Affects**: Native Qt wrapper only (`odysseus-app`) — not the browser version.

**Bug**: The login page saves the username to `localStorage['odysseus-last-user']`
to pre-fill on next login. When accessed through a `QWebEngineView`, the default
storage profile is **off-the-record** (in-memory). All localStorage, sessionStorage,
cookies, and IndexedDB are wiped when the Qt process exits. The username is never
remembered.

This also affects any other state that Odysseus stores in localStorage across
sessions when used via the native Qt wrapper.

**Fix applied in this fork**: `odysseus-app` now uses `QWebEngineProfile("odysseus")`
with explicit persistent storage paths:
```python
profile = QWebEngineProfile("odysseus", app)
profile.setPersistentStoragePath(os.path.expanduser("~/.local/share/odysseus/webengine"))
profile.setCachePath(os.path.expanduser("~/.cache/odysseus/webengine"))
profile.setPersistentCookiesPolicy(
    QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
)
page = QWebEnginePage(profile, view)
view.setPage(page)
```

**For upstream**: If/when upstream ships a native Linux wrapper (see contribution
#5 below), include this persistent profile pattern. Without it, localStorage-based
preferences (username, theme, etc.) don't survive restarts.

---

## 3. `pytest-timeout` not in test requirements

**File**: `requirements.txt` or `pyproject.toml`

**Bug**: The test runner calls pytest with `--timeout=60` in CI context (and our
fork's pipeline uses it too) but `pytest-timeout` is not listed in any requirements
file. This causes `PytestUnknownMarkWarning` and potentially silent test hangs on
clean environments where the package is not installed.

**Fix**: Add `pytest-timeout` to the test/dev requirements section of
`pyproject.toml` or a `requirements-dev.txt`.

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
# Add:
# timeout = 60
```

And in dev requirements:
```
pytest-timeout>=2.3.0
```

---

## 4. SearXNG JSON format not documented

**File**: `.env.example`

**Bug/gap**: `.env.example` tells users to set `SEARXNG_INSTANCE` but does not
mention that SearXNG's JSON API format must be explicitly enabled in the SearXNG
`settings.yml`. Without `formats: [html, json]`, every Odysseus search request
(`/search?format=json`) returns a 404.

The default SearXNG config only enables `html`. A user following the Odysseus
docs to set up SearXNG will have searches silently fail.

**Fix**: Add a comment in `.env.example`:
```bash
# SearXNG instance URL (self-hosted, for web search).
# IMPORTANT: your SearXNG settings.yml must include `formats: [html, json]`
# under the `search:` key — SearXNG disables JSON output by default and
# Odysseus queries the JSON API exclusively.
SEARXNG_INSTANCE=http://localhost:8080
```

---

## 5. `build-linux-app.sh` — native Linux desktop install script & Lifecycle Manager

**Status**: Being written in this fork. Will contribute once written and tested.

**Context**: Upstream has `build-macos-app.sh` for macOS native app packaging
but no equivalent for Linux. This fork has a working native KDE/Qt implementation
with a reference script planned at `build-linux-app.sh`.

See `docs/fork/build-linux-app.md` for full design. Key aspects upstream would
want:
- **PyQt6 + QWebEngineView wrapper**: (no browser chrome).
- **XDG-compliant per-user install**: (no sudo).
- **Integrated Lifecycle Management**: Implement a PID-tracking system using a state file (e.g., `~/.odysseus/services.pid`). On startup, the wrapper should purge stale PIDs from previous crashes to prevent port conflicts; on shutdown, it should kill all tracked services. This ensures a reliable "one-click" experience without zombie processes.
- **Desktop Integration**: `StartupWMClass` + `setDesktopFileName` for correct taskbar grouping.
- **Performance/UI Flags**: `--use-gl=desktop` to avoid Vulkan fallback lag and `--enable-features=EyeDropper` for the color picker.
- **Compatibility**: Works on KDE, GNOME, and other freedesktop-compliant desktops.

**Contribute after**: `build-linux-app.sh` and the associated lifecycle wrapper are tested locally.

---

## 6. `realesrgan` / `basicsr` incompatible with Python 3.14

**File**: Cookbook dependency installer (the `pip install realesrgan` path)

**Bug**: `basicsr` (a required dependency of `realesrgan`) is fundamentally broken on Python 3.14. It fails in two stages:
1. **Build-time**: Uses a legacy `setup.py` pattern (`exec()+locals()`) that causes `KeyError: '__version__'` during wheel build.
2. **Runtime**: Attempts to import `rgb_to_grayscale` from `torchvision.transforms.functional_tensor`, which has been moved to `torchvision.transforms.functional` in recent versions.

**Impact**: Users on Python 3.14 cannot install via the Cookbook. Even if installed via a patched wheel, the package crashes on import, causing the Cookbook to report it as "Not Installed" (a "Zombie Installation").

**Confirmed fix**:
1. **Build**: Use the `install-basicsr.sh` patch to fix `get_version()` using a namespace dictionary.
2. **Runtime**: Surgical import fix in `basicsr/data/degradations.py`: change `torchvision.transforms.functional_tensor` $\rightarrow$ `torchvision.transforms.functional`.

**Options for upstream**:
1. Patch `basicsr` or provide a pre-patched wheel for Python 3.14+.
2. Implement a version gate in the Cookbook installer to detect Python 3.13+ and warn the user.
3. Improve the error reporting in the installer to distinguish between "Package not found" and "Package crashed on import."

---

---

## How to contribute

Each item above is self-contained. To open a PR upstream:
1. Fork `pewdiepie-archdaemon/odysseus` from the `dev` branch
2. Apply the fix described above
3. Run the test suite: `venv/bin/pytest tests/`
4. Open a PR against `pewdiepie-archdaemon/odysseus:dev`

Do not push fork-specific changes (KDE integration, SearXNG lifecycle management,
pipeline tooling) upstream — those are fork-only.

## Agent Tool Budget Default
- **What was found:** The default value for `agent_max_tool_calls` in `settings.json` was set to 0.
- **Why it matters:** This effectively disables the agent's ability to use any tools, even when the system is explicitly set to "Agent Mode." This creates a "shackled" state where the LLM can propose tool calls but the execution engine refuses them due to a zero-budget limit.
- **Proposed Fix:** Update the default value in `settings.json` to a reasonable number (e.g., 20) to ensure out-of-the-box functionality for the agent loop.
