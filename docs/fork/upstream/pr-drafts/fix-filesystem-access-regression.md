# PR Draft: fix/filesystem-access-regression

**Fork issue:** [#26](https://github.com/jdmanring/odysseus/issues/26)
**Branch:** `fix/filesystem-access-regression`
**Status:** Ready to file

---

## Proposed Title

`fix(tools): restore filesystem access — keyword hints + $HOME path root`

## Proposed Body

Two upstream changes combined to break the agent's ability to read local files for admin users:

**Root cause 1 — `3b01760` removed file tools from `ALWAYS_AVAILABLE`.** `read_file`, `write_file`, `edit_file`, `grep`, `glob`, `ls` are now RAG-only. No keyword hints exist for disk-file queries, so when a user says "browse /home/user/project" or "read the file at src/app.py", the model never receives `read_file` in its tool list and falls back to saying "I don't have direct access to your local file system."

**Root cause 2 — `_resolve_tool_path` allows only `data/` and `/tmp` by default.** Even when `read_file` is retrieved via RAG, any path outside those roots fails with "path is outside the allowed roots". The `workspace` feature that previously expanded this was removed in `e6b1009`, leaving no default mechanism for admin users to read project files on their own machine.

### Fix

**`src/tool_index.py`** — Add a keyword-hint set that surfaces `read_file`, `write_file`, `edit_file`, `grep`, `glob`, `ls`, and `bash` when the user mentions file paths, source code, file extensions, or code-navigation verbs. Distinct from the existing `"my files/docs"` → `manage_documents` hint, which targets the editor panel, not the filesystem.

**`src/tool_execution.py`** — Add `$HOME` to `_tool_path_roots()` by default. Admin users legitimately need to read project files on their own machine. Credentials and shell configs (`.ssh`, `.gnupg`, `.env`, `id_rsa`, etc.) are still blocked by the existing sensitive-subpath deny list. Non-admin users are unaffected — `tool_security.py` already gates all file tools as admin-only.

### Testing

```bash
# Verify path confinement still blocks credentials:
python3 -c "
from src.tool_execution import _resolve_tool_path
try:
    _resolve_tool_path('/home/user/.ssh/id_rsa')
    print('FAIL — should have been blocked')
except ValueError as e:
    print('PASS —', e)
"

# Verify $HOME paths are now allowed:
python3 -c "
from src.tool_execution import _resolve_tool_path
path = _resolve_tool_path('/home/user/Projects/myapp/README.md')
print('PASS — allowed:', path)
"

# Verify keyword hints surface file tools:
# (requires ChromaDB running)
from src.tool_index import get_tool_index
idx = get_tool_index()
tools = idx.get_tools_for_query('read the file at src/app.py')
assert 'read_file' in tools, f'read_file missing: {tools}'
```

---

## Filing Notes

- Both files changed are in `src/` — no fork-specific code
- The `_resolve_tool_path_in_workspace` function in `tool_execution.py` is dead code left by the `c1674fc` migration (workspace is always `None` since `e6b1009`) — this PR does not clean that up to keep scope minimal
- Upstream issue: file on `pewdiepie-archdaemon/odysseus` before opening PR
- Target: `pewdiepie-archdaemon/odysseus:dev`
