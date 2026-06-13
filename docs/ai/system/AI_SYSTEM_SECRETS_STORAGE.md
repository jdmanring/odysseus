# AI SYSTEM SECRETS STORAGE

This document defines how Odysseus handles secrets, API keys, and sensitive configuration. For an AI agent, this is critical for understanding where to look for keys and how to modify them.

## 1. Secret Storage Tiers

Odysseus uses a dual-tier storage system for secrets to balance deployment flexibility with user-level configurability.

### Tier 1: System-Level Secrets (`.env`)
- **Storage:** A plain-text `.env` file in the project root.
- **Purpose:** Deployment-level overrides and core system credentials.
- **Load Mechanism:** Loaded at startup via `python-dotenv` in `app.py`.
- **Priority:** Highest. Environment variables set in the shell take precedence over `.env`.
- **Examples of Tier 1 Secrets:**
    - `DATABASE_URL`: Connection string for the application database.
    - `ODYSSEUS_ADMIN_PASSWORD`: Initial admin password.
    - `OPENAI_API_KEY`: System-wide OpenAI key.
    - `AUTH_ENABLED`: Global toggle for authentication.

### Tier 2: User-Level Secrets (`data/settings.json`)
- **Storage:** A JSON file in the `data/` directory.
- **Purpose:** App-level configuration and provider keys that a user can change via the Settings UI without restarting the server.
- **Load Mechanism:** Read/written by the Python backend and exposed via API endpoints.
- **Examples of Tier 2 Secrets:**
    - `tavily_api_key`: Search provider key.
    - `brave_api_key`: Search provider key.
    - `google_pse_key`: Google Search key.
    - `serper_api_key`: Serper search key.

---

## 2. Key Management Flow

### Adding a New Secret
1. **For System Secrets:** Add the key to `.env` (or `.env.example` for template) and restart the server.
2. **For User Secrets:** Update the value via **Settings $\rightarrow$ Search** (or other relevant menu), which writes directly to `data/settings.json`.

### Accessing Secrets in Code
- **Tier 1:** Accessed via `os.getenv("KEY_NAME")` or imported from `core.constants`.
- **Tier 2:** Accessed via the settings management logic (which reads `data/settings.json`).

---

## 3. Security Profile
- **Encryption:** Currently, secrets in `.env` and `settings.json` are stored in **plain text**.
- **Access Control:** Security relies on filesystem permissions of the host machine and the `AUTH_ENABLED` toggle to prevent unauthorized API access to the settings endpoints.
- **Exposure Risk:** API keys in `settings.json` are transmitted to the frontend for the Settings UI; they are handled as sensitive strings.