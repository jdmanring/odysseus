# SYSTEM OVERVIEW: ODYSSEUS

## 🗺️ GLOBAL ARCHITECTURAL MAP
Odysseus is a modular, service-oriented framework for AI orchestration and personal knowledge management. It is designed to be an "Operating System for AI."

### 1. LAYERED ARCHITECTURE
The system follows a strict tiered approach:
- **Interface Layer**: (Not in this repo) The UI that communicates via JSON-RPC/REST.
- **Routing Layer (`/routes`)**: The entry point for all requests. Every `.py` file here maps a set of capabilities to the backend logic.
- **Service Layer (`/core`, `/mcp_servers`, `/integrations`)**: The business logic. This is where the "work" happens.
- **Data Layer (`/core/database.py`, `/core/models.py`)**: Persistent storage and state management.

### 2. THE KNOWLEDGE REPOSITORY (`/docs`)
| Folder | Purpose | Key Documents |
| :--- | :--- | :--- |
| `/architecture` | High-level design | `system_overview.md` |
| `/lessons_learned` | Post-mortems | `zombie_process_failure.md` |
| `/operations` | Maintenance | Local environment setup |

### 3. KEY COMPONENT DIRECTORIES
| Directory | Purpose | AI Guidance |
| :--- | :--- | :--- |
| `/routes` | API Endpoints | Look here to see *what* the system can do. |
| `/core` | System Foundation | Look here to see *how* the system manages state, auth, and IO. |
| `/mcp_servers` | Model Context Protocol | Look here for tool-providing servers (Memory, RAG, Image Gen). |
| `/integrations` | External AI Bridges | Look here for specific logic for Claude, Codex, etc. |
| `/scripts` | Utility & CLI | Look here for maintenance and standalone operations. |
| `/docs` | Source of Truth | **READ THIS FIRST.** See `AI_ONBOARDING.md` for the entry sequence. |

### 3. CRITICAL EXECUTION CONTEXT
- **Local First:** This system runs on a **LOCAL machine**. Ignore any legacy `ssh` code unless explicitly instructed to target a remote host.
- **Process Management:** The system frequently spawns external processes (like `aria2c`). It is the AI's responsibility to ensure these are cleaned up using absolute `pkill` or port-specific kills.

## 🛠️ NAVIGATION GUIDE FOR AI
When tasked with a feature or bug:
1. **Consult `/docs`** to find the architectural intent.
2. **Check `/routes`** to identify the entry point.
3. **Trace into `/core` or `/services`** to find the logic.
4. **Verify in `/core/models.py`** for data structure constraints.
