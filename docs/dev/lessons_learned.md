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

## Misread Symptoms Lead to Hours of Wrong Debugging (Download Progress Case)

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

---

## Split-Brain Logic and The "No Files Matched" Ghost

**Issue:** A "No files matched" error persisted during GGUF downloads even after the discovery logic was fixed and verified.

**Cause:** `tooling/aria2c_download.py` had its own internal implementation of the file-resolution logic instead of using the central `HfUrlResolver`. The fix was applied to the resolver, but the downloader continued to use its own broken, rigid filtering logic.

**Lesson:** Before dismantling a system because of a "failure," verify if the failure is happening in the *discovery* phase or the *execution* phase. This "split-brain" architecture creates an illusion of failure in the system when only one component is broken. Always centralize critical business logic (like file resolution) into a single service or class used by all callers.

**Action Item:** Audit other `tooling/` scripts for duplicate logic that should be moved into central resolver or manager classes.

---

## Aggressive Connection Counts $\rightarrow$ Home Router Failure

**Issue:** Large model downloads caused home routers to lag or crash (the "shitting itself" phase).

**Cause:** The `aria2c` configuration was set to 4 concurrent files with 16 threads per file, totaling 64 concurrent TCP connections. Many consumer-grade routers have small NAT tables and cannot handle this volume of high-speed streams, leading to CPU exhaustion and memory overflows on the routing hardware.

**Lesson:** High-concurrency settings that work in data centers can be destructive on residential hardware. Always balance `max-concurrent-downloads` and `split` to stay within a reasonable total connection budget (e.g., 12-16 total connections) for consumer-grade equipment.

**Action Item:** Standardize "Balanced" vs "Aggressive" profiles for downloader tools.

---
