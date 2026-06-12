# AI FEATURE: EMAIL
The Email system is a full-featured IMAP/SMTP client that allows the AI to read, draft, and send messages. It is the system's primary "Communication Bridge."

## 1. Connection Management
To maintain performance and avoid server rate-limits, the system implements:
- **Connection Pooling:** Uses a global `_IMAP_POOL` to reuse TCP/TLS handshakes across different requests.
- **Multi-Layer Caching:** 
    - **Folder Cache:** Caches the list of available folders to avoid redundant `LIST` commands.
    - **Read Cache:** Caches the bodies of recently read emails, preventing repeated fetches of the same message.
- **Prefetching:** Background pollers "warm" the cache for the newest emails in the INBOX.

## 2. Security & Sanitization
Because emails can contain malicious payloads, the system employs:
- **HTML Sanitization:** A custom `_EmailHtmlSanitizer` strips dangerous tags and attributes from received emails before rendering them in the UI.
- **Markdown Bridge:** Outgoing emails are composed in Markdown and converted to safe, clean HTML for the recipient.

## 3. AI-Driven Communication
- **Style Mechanics:** The system can analyze a user's previous emails to extract a "writing style" (ExtractStyleRequest), which is then used as a system prompt for drafting new replies.
- **Urgency Detection:** Background tasks can scan incoming mail for keywords or sentiment to flag "urgent" messages for the AI to bring to the user's attention.
- **Threading:** Automatically handles `In-Reply-To` and `References` headers to ensure messages are correctly threaded in the recipient's client.

## 4. AI Implementation Notes
When managing email, the AI should:
1.  **Respect Threads:** Always reply within the existing thread rather than starting a new email for the same conversation.
2.  **Draft First:** Unless explicitly told to "Send Now," the AI should create a draft for the user to review.
3.  **Use Styles:** When drafting, explicitly reference the user's writing style to ensure the tone is authentic.