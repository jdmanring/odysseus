# AI FEATURE COOKBOOK

The Cookbook is Odysseus's model management subsystem. It handles the entire lifecycle of Local and Remote LLMs: from hardware-aware recommendation and downloading to deployment and serving.

## 1. Core Lifecycle: Download $\rightarrow$ Serve $\rightarrow$ Cache

The Cookbook removes the manual effort of setting up model servers by automating the plumbing.

### Model Downloading
- **Engine:** Primary use of the `hf download` CLI and `huggingface-hub` Python library.
- **Optimization:** Supports `hf_transfer` (a Rust-based parallel downloader) for maximum throughput, with an automatic fallback to the standard Python downloader for reliability.
- **Custom Tooling:** Integrates `aria2c` via a specialized script for high-speed multi-connection downloads.
- **Targeting:** Allows specifying `local_dir` to organize models into a flat-directory structure, which is then scanned by the system to populate the model picker.

### Model Serving
The Cookbook can launch and manage several serving engines:
- **vLLM:** High-throughput serving for FP8/AWQ models.
- **llama.cpp:** Flexible serving for GGUF models, with native Metal (macOS) and CUDA (Linux) acceleration.
- **Ollama:** Integration with the Ollama API for simplified local serving.

### Background Execution (The tmux/Detached Pattern)
Because model downloads and server startups can take minutes or hours, they must survive browser disconnects:
- **POSIX (Linux/macOS):** Runs commands inside `tmux` sessions. This allows the process to persist in the background and enables the UI to "attach" to the log stream via `tmux capture-pane`.
- **Windows:** Uses a detached-process wrapper (via Git Bash or `cmd.exe`) that writes output to a `.log` file and tracks a `.pid` file for liveness monitoring.

---

## 2. Remote Server Orchestration

The Cookbook extends its capabilities to remote GPU boxes via SSH.

- **SSH Key Management:** Can automatically generate an Ed25519 SSH key pair for the Cookbook, allowing it to authenticate with remote servers without manual password entry.
- **Remote Provisioning:** Can execute `apt` or `pacman` commands on the remote host to install required dependencies (e.g., `tmux`, `cmake`, `git`) before attempting to serve a model.
- **Remote Probing:** Actively checks for the existence of binaries (like `nvidia-smi` or `docker`) on the remote host to determine hardware capabilities.

---

## 3. Hardware Fitting ("What Fits?")

The Cookbook includes a hardware-aware recommendation engine:
- **VRAM Scanning:** Detects the available VRAM on local and remote GPUs.
- **Fit Scoring:** Compares model size (parameters $\times$ quantization) against available memory.
- **Recommendation:** Suggests specific model versions (e.g., "Llama-3-8B-GGUF-Q4_K_M") that are guaranteed to fit on the detected hardware.

---

## 4. Technical Implementation

### State Management
The system maintains a `data/cookbook_state.json` file which tracks:
- Downloaded models and their paths.
- Active server sessions and their PIDs.
- Configured remote servers and their SSH ports.
- **Secrets:** The HuggingFace (HF) token is encrypted before being written to this state file.

### Lifecycle Loop
`src/cookbook_serve_lifecycle.py` runs as a startup task in `app.py`. It monitors active serves, cleans up orphaned processes, and ensures that the state file remains in sync with the actual processes running on the host.

## 5. AI Agent Integration
The agent can interact with the Cookbook to:
- **Suggest Models:** Recommend a model to the user based on the task.
- **Manage Servers:** Start or stop a model server via the `cookbook_serve` builtin action.
- **Monitor Progress:** Track the download percentage of a new model to inform the user when it's ready.