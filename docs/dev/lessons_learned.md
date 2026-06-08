# Lessons Learned & Developer Gotchas

## Tool Access and the "Workspace" Shackle

**Issue:** Agents may encounter "outside the allowed roots" errors even after modifying `src/tool_execution.py` to include the project root in `_tool_path_roots()`.

**Cause:** The Odysseus UI has a **Workspace** setting (found on the left side of the chat box). If this is set (e.g., to `/data`), the system uses `_resolve_tool_path_in_workspace()` instead of `_resolve_tool_path()`. This function enforces a strict containment policy that restricts all tool access to descendants of the specified workspace directory, overriding any global root configurations.

**Lesson:** When debugging "allowed roots" errors:
1. **First**, check the UI Workspace setting. If it's set to a subfolder, the agent is "shackled" to that folder.
2. **Second**, ensure the Workspace is set to the project root or left blank to allow the global root policy to take effect.
3. **Avoid** trying to hack the core tool execution logic until the UI configuration has been verified.

**Action Item:** Improve user-facing documentation to explicitly explain the Workspace flag's impact on tool permissions.

---

## Misread Symptoms → Hours of Wrong Debugging (Download Progress Case)

**Issue:** Download progress appeared to show double the expected size (e.g., 18 GB
reported as 36 GB). An AI agent diagnosed this as zombie aria2c processes running in
parallel and spent hours destroying system state, killing processes, and iterating
nonsense fixes.

**Cause:** It was a display bug. The `_dlFileTracker` in `cookbookRunning.js` was only
summing the 4 actively-downloading files, not the full model. The "doubling" was a
coincidence of model shard count and file sizes making the partial sum look doubled.

**Lesson:** Before assuming process-level failures (zombie processes, race conditions,
double-spawning), verify the symptom source. A number that looks wrong is far more likely
to be a display/calculation bug than an actual infrastructure failure. Fix the tracker
that reads the number before dismantling the system that produces it.

The correct fix was a 20-line change to `cookbookRunning.js` (`_dlFileTracker` Map to
accumulate completed-file bytes). The wrong path was `pkill`, port analysis, and process
archaeology that changed nothing.
