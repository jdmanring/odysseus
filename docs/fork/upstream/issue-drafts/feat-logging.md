# Upstream Issue Draft: feat-logging

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/feat-logging.md`
**Branch:** `feat/logging`
**Type:** Feature / Security hardening

---

## Title

`[Logging] No request correlation, PII in log output, and no auth audit trail`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Summary:**

The upstream hardening audit ([#3803](https://github.com/odysseus-dev/odysseus/issues/3803)) identified two classes of logging defect:

> "PII (emails, usernames, message bodies) logged at INFO level in several paths"
> "No audit trail for sensitive operations (auth events, vault unlock, admin wipes)"

**Current behaviour:**

1. **No request correlation.** All log lines from different concurrent requests are interleaved with no shared identifier. When a user reports an error, there is no way to isolate the log lines belonging to their specific request.

2. **PII in log output.** Email addresses, usernames, and message bodies are logged at INFO level in several routes. Anyone with access to the log file (including the server owner in a shared hosting scenario) can read plaintext user content.

3. **No auth audit trail.** Login successes and failures, password changes, admin user creation and deletion, and vault unlock events generate no dedicated log entries. There is no record of who authenticated when, or what sensitive operations were performed.

4. **No timing data.** When users report slow operations (slow Cookbook downloads, slow email polling, slow embedding), there is no timing instrumentation to identify which subsystem is the bottleneck.

**Steps to reproduce:**

1. Run `uvicorn app:app --host 0.0.0.0 --port 7000` with `ODYSSEUS_DEBUG=1`.
2. Open two browser tabs and send concurrent requests.
3. Observe that log lines from both requests are interleaved with no way to separate them.
4. Trigger a login event — confirm no `auth.login.*` entry appears in the log.
5. Change a setting via the UI — confirm no `settings.audit` entry appears.
6. Search your email in Odysseus — observe that the email address appears in the log output.

**Expected:**

- Each HTTP request has a UUID correlation ID visible in both logs and the `X-Request-ID` response header.
- PII fields (email addresses, API keys, message content) are scrubbed from log output using a key-name-based denylist.
- Login, logout, password change, admin ops, and vault access each generate a structured audit log entry.
- Critical I/O paths (email polling, embedding, SearXNG, agent completion) emit timing data at INFO level when thresholds are exceeded.

**Related upstream issues:** #3803 (hardening audit), #3799 (PII scrubbing pass)

**Note:** This issue does not address all items in #3803 — only the logging-specific gaps. Other hardening items from that audit are tracked separately.
