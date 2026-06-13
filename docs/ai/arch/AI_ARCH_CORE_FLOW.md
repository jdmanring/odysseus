# AI ARCHITECTURE CORE FLOW

This document serves as the Master Map of Odysseus. It describes the lifecycle of a single request and how all the documented features intersect to produce a response.

## 1. The Request Lifecycle (Data Path)

When a user sends a message, the request follows this precise sequence:

### Phase 1: Contextualization & Routing
1.  **Setting Resolution:** The system checks `AI_SYSTEM_SETTINGS_MAP.md` to determine which model endpoint and utility model to use.
2.  **User Profile:** The system loads user preferences, including the active **Theme** (`AI_FEATURE_THEME.md`) and timezone.
3.  **Routing:** The request is routed to the appropriate handler (Standard Chat, **Compare Mode** `AI_FEATURE_COMPARE.md`, or **Deep Research** `AI_FEATURE_DEEP_RESEARCH.md`).

### Phase 2: The Brain (Augmentation)
Before the LLM sees the prompt, the system queries the **Brain** (`AI_FEATURE_BRAIN.md`):
1.  **Vector Retrieval:** The prompt is embedded and compared against the ChromaDB index.
2.  **Context Injection:** Relevant memories (facts, preferences, project notes) are injected into the system prompt as "Known Context."
3.  **Session History:** The last $N$ messages are retrieved to maintain conversational continuity.

### Phase 3: The Agent Loop (Action)
If the model determines that the user's request requires an action, it enters the **Tool Loop** (`AI_FEATURE_TOOLS.md`):
1.  **Thought:** The model generates a reasoning step.
2.  **Tool Call:** The model calls a tool (e.g., searching the web, reading a file, or updating a **Task** `AI_FEATURE_TASKS.md`).
3.  **Execution:** The system executes the tool, potentially using a **Cookbook**-managed server (`AI_FEATURE_COOKBOOK.md`) for specialized processing.
4.  **Observation:** The result is fed back to the model.
5.  **Repeat:** This loop continues until the model has sufficient information.

### Phase 4: Generation & Delivery
1.  **Final Synthesis:** The model generates the final response using the accumulated context and tool observations.
2.  **UI Rendering:** The response is streamed to the UI, where it is styled according to the **Theme** (`AI_FEATURE_THEME.md`).
3.  **Post-Processing:** 
    - The response is saved to the session history.
    - The **Brain** may trigger a background task to extract new memories from the interaction.

---

## 2. Cross-Feature Dependency Map

| Feature | Depends On | Provides To |
| :--- | :--- | :--- |
| **Brain** | Settings (Embeddings) | Agent Loop, Final Synthesis |
| **Tools** | Settings (API Keys), Brain | Agent Loop, Task Scheduler |
| **Cookbook** | Secrets (HF Token), System HW | Model Endpoints, Agent Tools |
| **Deep Research** | Tools (Search), Settings | Final Synthesis, Brain (Research Logs) |
| **Tasks** | Tools (Actions), Brain | Agent Loop, User Notifications |
| **Compare** | Settings (Model Endpoints) | UI Rendering |
| **Theme** | User Prefs | UI Rendering, Favicon/Browser Integration |
| **Settings** | Secrets (Env Vars) | Every other feature in the system |

---

## 3. State & Persistence Layer

The entire system is backed by a tiered storage strategy:
- **Configuration:** `data/settings.json` $\rightarrow$ Global and User preferences.
- **Secrets:** `.env` $\rightarrow$ System-level API keys and admin credentials.
- **Memory:** `ChromaDB` $\rightarrow$ Vectorized personal knowledge.
- **Automation:** `ScheduledTask` & `TaskRun` $\rightarrow$ Background automation state.
- **Models:** `data/cookbook_state.json` $\rightarrow$ Model paths and server PIDs.
- **Visuals:** `localStorage` $\rightarrow$ Theme and custom color overrides.