# AI FEATURE: SKILLS & MCP
The Extension layer allows the system to expand its capabilities dynamically through custom Python scripts (Skills) and the Model Context Protocol (MCP).

## 1. Custom Skills
Skills are user-defined Python functions that extend the AI's toolset:
- **Dynamic Loading:** Skills are stored as standalone scripts and loaded into the agent's runtime on demand.
- **Tool Registration:** Each skill defines its own input schema (JSON) and description, which the AI uses to determine when to call the skill.
- **Local Execution:** Skills run within the system's secure environment, allowing them to interact with local files or APIs.

## 2. Model Context Protocol (MCP)
The system implements the **MCP Standard**, a protocol designed to unify how LLMs connect to external data and tools:
- **MCP Servers:** The system can connect to remote MCP servers via JSON-RPC (over stdio or HTTP).
- **Automatic Discovery:** When connected to an MCP server, the system automatically discovers all available tools and resources exposed by that server.
- **Context-on-Demand:** MCP allows the server to provide "snippets" of data (e.g., a specific database row or a file block) only when the AI specifically requests it, preventing the context window from being flooded with irrelevant data.

## 3. AI Implementation Notes
When using extensions, the AI should:
1.  **Verify Tool Capability:** Before calling a Skill or MCP tool, check the tool's description to ensure it is the right fit for the current task.
2.  **Handle Protocol Errors:** If an MCP server returns an error (e.g., timeout or invalid parameters), explain the failure to the user rather than hallucinating a result.
3.  **Suggest New Skills:** If the user repeatedly asks for a task that isn't supported by existing tools, suggest creating a new **Skill** script to automate it.