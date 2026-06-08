# AI Capabilities Audit
## Available Tools
- `bash`: Full shell access for system operations.
- `grep`: Regular expression search across files.
- `read_file`: Read content of specific files.
- `write_file`: Create/Overwrite files on disk.
- `edit_file`: Targeted string replacement in files.
- `glob`: File discovery by pattern.
- `ls`: Directory listing.
- `update_plan`: Syncs the active plan window.
- `manage_memory`: RAG-based persistent memory management.
- `ui_control`: Controls UI elements (themes, panels, toggles).
- `serve_model`: Launches vLLM/Ollama/SGLang servers.

## Invisible Links
- `update_plan` $\rightarrow$ Updates the docked Plan Window.
- `ui_control (set_theme)` $\rightarrow$ Modifies CSS variables in the frontend.
- `serve_model` $\rightarrow$ Creates a tmux session on the remote host.
