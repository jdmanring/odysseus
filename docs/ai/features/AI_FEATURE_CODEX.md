# AI FEATURE: CODEX & KNOWLEDGE
The Codex system is the centralized knowledge management layer. it integrates document storage, versioning, workspace management, and a secure API bridge for external agents.

## 1. The Document Library
The system treats documents as living entities rather than static files:
- **Versioning:** Every document has a full version history (`DocumentVersion` table), allowing the AI to track changes or revert to previous states.
- **Language Detection:** Uses `_sniff_doc_language` to automatically categorize documents by language.
- **PDF Integration:**
    - **AcroForms:** If a PDF contains form fields, the system creates a "form-backed markdown" document, allowing the AI to read and write specifically to form fields.
    - **Standard PDFs:** Plain PDFs are converted to markdown wrappers for searchability.

## 2. The Codex API Bridge
The Codex provides a specialized API surface that allows external plugins to interact with the system under a "Scoped Permission" model:
- **Scopes:** External agents must be granted specific scopes (e.g., `documents:read`, `email:send`, `calendar:write`) to perform actions.
- **Unified Interface:** Codex abstracts the complexity of the various routes (Email, Memory, Calendar) into a single, consistent API for plugins.

## 3. Workspace & Editor Management
- **Workspace Routing:** An admin-only feature that allows the system to map a specific server directory as the "Active Workspace," defining where tools (like shell or python) should execute.
- **Editor Drafts:** To prevent data loss, the system persists the state of active editor sessions (including canvas layers and offsets) in the database, ensuring that work-in-progress survives session restarts.

## 4. AI Implementation Notes
When managing knowledge, the AI should:
1.  **Utilize Versioning:** When making substantial changes to a document, summarize the changes in the version note.
2.  **Check Scopes:** If acting as a plugin via Codex, always verify that the requested action is within the granted scope.
3.  **Prefer Markdown:** Always store knowledge in Markdown to maintain compatibility with the system's rendering and search engines.