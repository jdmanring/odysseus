# Service Lifecycle Management (Artix s6 KDE)

This document describes the "Smart Lifecycle" implementation for managing backend services in the Odysseus fork, specifically tailored for environments using s6 and KDE Plasma.

## Architecture

To avoid polluting system-level s6 services and ensure that Odysseus services only run when the application is active, the lifecycle is managed entirely at the user level.

### Components
- **Startup Script (`~/.local/bin/odysseus`)**: Responsible for spawning the required backend services (Server, SearXNG, ChromaDB).
- **UI Wrapper (`~/.local/bin/odysseus-app`)**: The Master Controller. It manages the start/stop triggers and monitors the state of the services.
- **PID State File (`~/.odysseus/services.pid`)**: A persistent record of all active service PIDs.

## The Workflow

### 1. Launch Sequence
When the user clicks the taskbar icon:
1. The `.desktop` file executes `odysseus-app`.
2. **Pre-flight Check**: `odysseus-app` reads `~/.odysseus/services.pid`. If any PIDs are found, it checks if the processes are still running.
3. **Crash Recovery**: If stale processes are found (indicating a previous crash), they are killed immediately to free ports and prevent zombie behavior.
4. **Service Start**: `odysseus-app` calls the `odysseus` startup script.
5. **PID Registration**: The startup script launches each service and writes the PID to `~/.odysseus/services.pid` in the format `service_name:pid`.
6. **UI Start**: The main application interface is launched.

### 2. Shutdown Sequence
When the user closes the application:
1. The `odysseus-app` wrapper intercepts the exit signal.
2. **Precise Termination**: It reads `~/.odysseus/services.pid` and sends a termination signal to every registered PID.
3. **Cleanup**: The `services.pid` file is deleted to signal a clean state.

## Configuration Details

### PID File Format
The file `~/.odysseus/services.pid` stores entries as:
```text
odysseus-server:1234
searxng:1235
chromadb:1236
```

### KDE Integration
The system is integrated via a custom `.desktop` entry that points exclusively to the `odysseus-app` wrapper, ensuring the lifecycle manager is always the entry point.
