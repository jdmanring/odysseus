# AI SYSTEM SETTINGS MAP

This document provides a 1:1 mapping of the Odysseus Settings menu to its technical implementation. This is designed for AI agents to understand exactly which settings affect which behaviors without needing to explore the UI.

## 1. AI Plumbing (The Model Stack)

### Add Models
- **Purpose:** Configuration of LLM endpoints (Local and Cloud).
- **Implementation:** Managed via `static/js/settings.js` and `src/model_discovery.py`.
- **Key Actions:**
    - **Network Discovery:** Probes for local providers (Ollama, vLLM, llama.cpp).
    - **Endpoint Addition:** Adds base URLs and API keys to the provider list.
- **Impact:** Affects which models are available in the model picker and for internal agent tasks.

### AI Defaults
- **Purpose:** Global defaults for agent behavior and model selection.
- **Implementation:** `data/settings.json`.
- **Key Keys:**
    - `default_endpoint_id`: The primary LLM endpoint used for general chat.
    - `default_model`: The specific model used by default.
    - `utility_endpoint_id` / `utility_model`: A faster/cheaper model used for internal utility tasks (e.g., summarization, classification).
    - `teacher_model` / `teacher_enabled`: A high-capability model used to "teach" or refine other outputs.
    - `agent_max_tool_calls`: Limit on how many tools the agent can call in a single turn.
    - `agent_max_rounds`: Limit on the total number of turns in an agent loop.
    - `agent_input_token_budget`: Soft limit for context window management.

### Search
- **Purpose:** Configuration of web search capabilities.
- **Implementation:** `data/settings.json` and `src/search_provider.py` (or similar).
- **Key Keys:**
    - `search_provider`: Primary provider (`tavily`, `searxng`, `duckduckgo`).
    - `search_fallback_chain`: Ordered list of providers to try if the primary fails.
    - `search_url`: Custom URL for self-hosted instances (e.g., SearXNG).
    - `search_result_count`: Number of results to retrieve per query.
    - `search_safesearch`: Filter level (`strict`, `moderate`, `off`).
    - **API Keys:** `tavily_api_key`, `brave_api_key`, `google_pse_key`, `serper_api_key`.

---

## 2. Integrations & Communication

### Integrations
- **Purpose:** Connection to external services.
- **Implementation:** Scattered across `services/` (STT, TTS, Email, Calendar).
- **Key Configurations:**
    - **STT (Speech-to-Text):** `stt_enabled`, `stt_provider`, `stt_model`.
    - **TTS (Text-to-Speech):** `tts_enabled`, `tts_provider`, `tts_model`, `tts_voice`.

### Email
- **Purpose:** Integration with email for notifications and alerts.
- **Implementation:** Managed via `services/email/` and `data/settings.json`.
- **Key Keys:**
    - `reminder_email_to`: Recipient address for email reminders.
    - `urgent_email_prompt`: The system prompt used by the AI to decide if an email is "urgent."

### Reminders
- **Purpose:** Notification delivery system.
- **Implementation:** `data/settings.json` and `routes/note_routes.py`.
- **Key Keys:**
    - `reminder_channel`: Where reminders are sent (`browser`, `email`, `ntfy`).
    - `reminder_llm_synthesis`: Whether the AI should summarize reminders before sending.
    - `reminder_ntfy_topic`: The topic string used for `ntfy.sh` notifications.

---

## 3. User Interface & Control

### Appearance
- **Purpose:** Visual styling and themes.
- **Implementation:** `static/js/theme.js` and `static/style.css`.
- **Persistence:** Theme state is typically stored in browser `localStorage` or a user profile in the database.

### Shortcuts
- **Purpose:** Keyboard accelerators for power users.
- **Implementation:** `data/settings.json` $\rightarrow$ `keybinds`.
- **Key Mappings:**
    - `search`: `ctrl+k`
    - `toggle_sidebar`: `ctrl+b`
    - `new_session`: `ctrl+alt+n`
    - `admin_panel`: `ctrl+shift+u`

---

## 4. Admin & System

### Account / Users
- **Purpose:** Access control and identity.
- **Implementation:** `core/database.py` (Users table) and `routes/auth_routes.py`.

### Admin / Agent Tools
- **Purpose:** Advanced configuration of the agent's capabilities.
- **Implementation:** `src/builtin_actions.py` and `src/agent_loop.py`.

### System (The Danger Zone)
- **Purpose:** Destructive maintenance and system resets.
- **Implementation:** `routes/admin_wipe_routes.py`.
- **Key Actions:**
    - **Wipes:** Ability to clear sessions, memories, tasks, and user data.
    - **Danger Zone:** Explicit UI warnings for irreversible actions.