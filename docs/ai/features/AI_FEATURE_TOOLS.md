# AI FEATURE TOOLS

The Tools system is the "hands" of Odysseus. It provides the agent with the ability to interact with the physical world (files, shell, network) and the internal system (memory, tasks, settings).

The system distinguishes between **Autonomous Agent Tools** (LLM-driven) and **Built-in Actions** (Logic-driven).

---

## 1. Built-in Actions (The Plumbing)

Built-in Actions (`src/builtin_actions.py`) are Python functions executed directly by the `TaskScheduler`. They do **not** require an LLM to run and are primarily used for system maintenance and scheduled automation.

### Core Categories
- **Housekeeping:** Actions like `action_tidy_sessions`, `action_tidy_documents`, and `action_tidy_research` that prune stale or broken data.
- **System Maintenance:** `action_consolidate_memory` uses an LLM (as a utility) to deduplicate and clean the vector index.
- **Low-Level Execution:** 
    - `action_ssh_command`: Executes a shell command on a remote host via SSH.
    - `action_run_script`: Runs a local or remote script with configurable timeouts.
    - `action_run_local`: A restricted version of script execution for local-only environments.

### Special Execution States
To prevent the Activity log from being flooded with "nothing happened" entries, the system uses specialized exceptions:
- `TaskNoop`: Raised when a task runs but finds no work to do. The run is silently dropped and not recorded in the user's history.
- `TaskDeferred`: Raised when a task is not ready to run. It pushes the next execution window forward (default 20 minutes) without marking the run as a failure.

---

## 2. Agent Tools (The LLM Loop)

Agent Tools are capabilities exposed to the LLM during a chat session. These allow the agent to "think" and "act" in a loop.

### The Tool Loop
1.  **Discovery:** The agent identifies the necessary tool based on a tool index and the user's prompt.
2.  **Invocation:** The agent emits a tool call (typically following the MCP or an internal JSON schema).
3.  **Execution:** The system executes the tool (e.g., searching the web, reading a file).
4.  **Observation:** The tool's output is fed back into the LLM context as an "Observation."
5.  **Synthesis:** The agent uses the observation to either call another tool or provide a final answer.

### Tool Types
- **Internal API Tools:** Access to Memory, Tasks, Notes, and Calendar.
- **External MCP Tools:** Integration with Model Context Protocol servers for third-party extensions.
- **System Tools:** File system access, shell execution, and web browsing.
- **Knowledge Tools:** Vector search over the user's "Brain" (Memory).

---

## 3. Security & Permissions

Because tools can perform destructive actions, the system implements a strict permission layer:

- **User-Based Access:** Most tools are available to all users, but "High-Risk" tools (e.g., `shell`, `python_exec`, `admin_wipe`) are restricted to the `admin` role.
- **Sandbox/Wrapper:** Shell commands are often wrapped in specific environments (e.g., `bash -c` on Linux or a Git Bash wrapper on Windows) to ensure consistent behavior.
- **Validation:** The `TaskCreate` route validates that a scheduled task's action is permitted for the owner who created it.