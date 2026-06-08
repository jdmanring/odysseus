# Non-Obvious Behaviors — Odysseus

Things that will surprise you if you don't know them. Required reading before touching
any of these subsystems.

---

## Frontend

**No bundler, no auto-discovery.**
A new `.js` file needs a `<script>` tag added to `static/index.html`. ES module imports
work between files; `node_modules` does not exist. Non-module scripts (`chatHistory.js`,
`qt-bridge.js`) must load before any modules that reference `window.chatHistory` or
`window.qtBridge`.

**Model picker autohides.**
The model picker closes automatically after 10 non-whitespace characters are typed.
This is intentional — the UI clears itself so you can see what you're typing.
It is not a bug and should not be "fixed" without understanding why it was added.

**Plan Window desync.**
The Plan mode window only updates when `update_plan` is explicitly called by the model.
If the agent completes work without calling it, the displayed plan becomes stale.
The UI shows the last-known plan state, not the live agent state.

**DOM virtualization.**
`chatHistory.js` sets `window.chatHistory` (MessageWindow class). It paginates history
at session load (WINDOW_SIZE=50 messages) and live-prunes the DOM during a session
(prunes at 80 nodes, keeps 60). `sessions.js:selectSession()` calls
`window.chatHistory.reset()` before clearing `#chat-history`. If you touch the session
switching or history rendering code, you must preserve this call or the virtualizer
will corrupt state on tab switches.

**Scroll-to-bottom recalculates `target` every frame.**
`const target` is declared inside the `step()` animation callback in `index.html` — not
outside. This is deliberate: `#chat-history` scroll position can change between frames
during a live stream. Moving `target` outside `step()` causes the button to miss the
bottom when messages are still arriving.

---

## Native Linux App (`linux_wrapper.py`)

**The wrapper owns the server lifecycle.**
`linux_wrapper.py` spawns uvicorn. If you also run uvicorn separately, both compete
for port 8000. Running the native app and bare uvicorn simultaneously will cause one
to fail at startup.

**`QWebEngineView` is Chromium but not a browser.**
The Web EyeDropper API does not exist in `QWebEngineView`. `colorPicker.js` detects
`window.__QT_WRAPPER__` via `platform.js` and calls `window.qtBridge.openColorDialog()`
instead. Any new UI feature that touches a browser-only API needs a Qt compat check.

**External links need `OdysseusPage`.**
`QWebEngineView` normally opens navigation in the same view. `OdysseusPage` subclasses
`QWebEnginePage` and overrides `acceptNavigationRequest` and `createWindow` to route
external URLs to `QDesktopServices.openUrl()` (system browser). Without this, links
would navigate the entire app away.

**Hardcoded profile path.**
`linux_wrapper.py` passes `~/.local/share/odysseus/webengine` to `QWebEngineView` as
the profile storage path. This is not yet wired through `src/constants.py`. Before
filing this as an upstream contribution, this needs to be reconciled with whatever
constants the project defines for user data paths.

---

## Downloads (aria2c)

**HF signed URLs expire.**
`hf_url_resolver.py` re-resolves a fresh signed URL on every download start.
Never cache the resolved URL across sessions — it will be invalid.

**`_dlFileTracker` is module-level state.**
In `cookbookRunning.js`, this object accumulates completed-file bytes across poll ticks.
It is intentionally not reset between ticks — that persistence is what makes the overall
model download progress percentage correct. Resetting it (e.g., on poll error) breaks
the running total.

**aria2c progress line format (leading space is literal).**
Lines look like: `·[#a1b2c3 1GiB/5GiB(21%) CN:4 DL:50MiB ETA:1m20s]`
The space before `[` is always present. Regexes must match `^\s*\[#` — not `^\[#`.
Getting this wrong causes the progress parser to silently drop every status line.

---

## Backend / LLM

**Anthropic tool results must stay inline.**
`src/llm_core.py:_build_anthropic_payload()` extracts all `role=system` messages into
Anthropic's top-level `system` field — except messages prefixed with `[Tool execution results]`.
Those stay as inline `role=user` messages at their temporal position in the conversation.
Collapsing them into the system prompt loses round ordering and breaks multi-turn agent sessions.

**`data/settings.json` overrides `src/settings.py`.**
`DEFAULT_SETTINGS` in `src/settings.py` is the fallback. Any value the user has saved
appears in `data/settings.json` and wins at runtime. When debugging settings issues,
check both files — the JSON wins.

**Agent tool budget defaults to 20.**
`agent_max_tool_calls` in `DEFAULT_SETTINGS` is 20. If you see agent runs stopping
early, check `data/settings.json` — a 0 value there from an older install will cap the
loop at zero tool calls.

---

## Cookbook / Model Serving

**Cookbook serves models via tmux sessions (upstream).**
In the upstream project, stopping a model is a `tmux kill-session` operation — the
Cookbook does not just `kill` a subprocess. This means tmux must be installed on
the host for the serve feature to work.

**aria2c progress lines are updates, not new downloads.**
Each aria2c status report line shows the current state of an active download session.
They are not additive — a new line for the same `#hash` replaces the previous one.
If the UI appends each report as a new row instead of updating in place, it will appear
as if 4 new parallel downloads are starting on every poll tick. The correct behavior is
to match on the session hash and update the existing card.
