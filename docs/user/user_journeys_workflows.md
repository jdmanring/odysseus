# Odysseus User Journeys

This document describes the step-by-step interaction flow for the most critical operations within the Odysseus system.

## 1. Session Management
**Goal:** Initialize a workspace and organize conversation history.

### Starting a New Session
1.  **Action:** Click the `+` (New Chat) button on the Navigation Rail (`#rail-new-session`).
2.  **System Response:** The current chat history is cleared, and a new session ID is generated.
3.  **Outcome:** A clean slate for a new task or query.

### Renaming a Session
1.  **Action:** Click on the current session name in the Sidebar header (`#current-meta`).
2.  **System Response:** The `#rename-session-modal` opens.
3.  **Action:** Type the new name into the input field and click "Save".
4.  **Outcome:** The session is updated in the history list and the header.

### Archiving a Session
1.  **Action:** Click the Archive button in the Sidebar (`#tool-archive-btn`).
2.  **System Response:** The session is marked as archived.
3.  **Outcome:** The session is removed from the active "Recent" list and moved to archives.

## 2. Brain (Memory & Skills) Management
**Goal:** Augment the AI's long-term knowledge and operational capabilities.

### Adding a New Memory
1.  **Action:** Click the Memory Tool on the Rail (`#tool-memory-btn`).
2.  **Action:** In the Brain modal, select the "Add" tab.
3.  **Action:** Enter the fact or piece of information into the "New memory text" field.
4.  **Action:** Click "Add Memory".
5.  **Outcome:** The fact is persisted to the user's long-term memory store and becomes available for retrieval in future chats.

### Importing a New Skill
1.  **Action:** Open the Brain modal $\rightarrow$ "Skills" tab.
2.  **Action:** Enter a URL into the "Skill import URL" field.
3.  **Action:** The system fetches the skill definition (JSON/Markdown).
4.  **Action:** Review and save the skill.
5.  **Outcome:** The AI now has a structured "how-to" for a specific complex problem.

## 3. Model Orchestration (The Cookbook)
**Goal:** Deploy and switch between different LLMs or Diffusion models.

### Launching a Model
1.  **Action:** Click the Cookbook Tool on the Rail (`#tool-cookbook-btn`).
2.  **Action:** Browse the "Cached Models" or search for a HuggingFace repo.
3.  **Action:** Select a serve preset or enter a custom launch command.
4.  **Action:** Click "Serve Model".
5.  **System Response:** A tmux session is created on the target GPU server, and vLLM/SGLang/Ollama is launched.
6.  **Outcome:** The model becomes available in the model-picker for chatting.

## 4. Complex Task Execution (The Plan Mode)
**Goal:** Use the AI to execute multi-step projects with transparent progress tracking.

### Initiating a Plan
1.  **Action:** Prompt the AI with a complex request (e.g., "Audit the codebase and write a manual").
2.  **Action:** The AI proposes a plan in the chat.
3.  **Action:** User approves the plan.
4.  **System Response:** The AI calls `update_plan()`, and the Plan Window appears/updates.
5.  **Outcome:** A living checklist is now visible in the UI, syncing in real-time as the AI completes steps.

## 5. Personal Knowledge Integration
**Goal:** Link chat context to persistent external data.

### Creating a Note from Chat
1.  **Action:** Request the AI to "Save this as a note."
2.  **System Response:** AI calls `manage_notes(action='add', ...)` with a title and content.
3.  **Outcome:** The information is stored in the Notes panel, accessible across all sessions.

### Scheduling a Task
1.  **Action:** Prompt the AI to "Remind me to check this tomorrow at 10 AM."
2.  **System Response:** AI calls the calendar/task integration API.
3.  **Outcome:** An entry is created in the user's calendar/task list.