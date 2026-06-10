# PR Draft: fix(tools): remove dead workspace import crashing filesystem tools

**Branch:** `fix/agent-tools-workspace-import`
**Fork issue:** [#28](https://github.com/jdmanring/odysseus/issues/28)
**Target:** `pewdiepie-archdaemon/odysseus:dev`

---

## Title

`fix(tools): remove dead workspace import crashing filesystem tools`

## Description

`c1674fc` (refactor: migrate execution logic to `src/agent_tools/` package) was
authored before `0aba00f` (refactor: remove dead workspace-confinement plumbing)
deleted `_resolve_tool_path_in_workspace()`. When `c1674fc` landed after `0aba00f`,
`filesystem_tools.py` imported a function that no longer existed. Every filesystem
tool call — `read_file`, `write_file`, `edit_file`, `grep`, `glob`, `ls` — raises
`ImportError` at runtime, leaving the agent unable to use any of these tools.

**Fix:**

- `src/agent_tools/filesystem_tools.py`: remove `_resolve_tool_path_in_workspace`
  from all six tool class imports; replace the `if workspace else _resolve_tool_path()`
  branches with a direct `_resolve_tool_path()` call. Workspace was always `None`
  after `0aba00f` removed the feature entry point.
- `src/tool_execution.py`: remove residual `workspace=` param from `_direct_fallback`
  and `execute_tool_block` signatures, and the stray `workspace=workspace` kwarg in
  the `edit_file` dispatch. Drop `_resolve_tool_path_in_workspace` entirely.

No behavior change beyond restoring the tools to working order.

## Files Changed

- `src/agent_tools/filesystem_tools.py`
- `src/tool_execution.py`

## Testing

Full test suite passes. The crash is reproducible by invoking any filesystem tool
in agent mode on the affected commit range.

## Filing Notes

- File an upstream issue first; add the upstream issue number to the PR body
- Single clean commit — no squashing needed
