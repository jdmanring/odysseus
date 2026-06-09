# AI FEATURE: VAULT
The Vault is a secure credential management system that integrates with industry-standard encrypted vaults to protect sensitive keys and passwords.

## 1. Integration Logic
The system does not store passwords in plain text. Instead, it acts as a secure wrapper around the **Bitwarden/Vaultwarden CLI (`bw`)**:
- **Session Management:** The `BW_SESSION` key is stored in `data/vault.json` with highly restrictive POSIX permissions (`0o600`), ensuring only the system process can read it.
- **Secure Pipe:** To prevent passwords from appearing in process lists (e.g., `ps aux`), passwords are passed to the CLI via `stdin` rather than command-line arguments.

## 2. Lifecycle Operations
The AI manages the vault through a strict state machine:
- **Login:** Authenticates the master password to establish a session.
- **Unlock:** Uses the session key to decrypt the vault.
- **Lock:** Immediately clears the session from memory.
- **Logout:** Ends the session and destroys the local key.

## 3. AI Implementation Notes
When managing the vault, the AI should:
1.  **Minimize Exposure:** Unlock the vault only when a secret is explicitly needed and Lock it immediately after the secret is retrieved.
2.  **Never Log Secrets:** Never print the retrieved secret to the chat or log files; instead, pass it directly to the tool that requires it.
3.  **Session Awareness:** Check if the vault is `unlocked` before attempting to retrieve a secret to avoid unnecessary login prompts.