# Upstream Issue Draft: fix-provider-logo-ordering

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-provider-logo-ordering.md`
**Branch:** `fix/provider-logo-ordering`
**Type:** Bug

---

## Title

`[UI] Provider logos missing for Groq, Together, Fireworks, Pollinations; Google Gemini logo shown for OpenAI models`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Steps to reproduce:**

1. Add endpoints for Groq (`api.groq.com`), Together AI (`api.together.xyz`), Fireworks AI (`api.fireworks.ai`), and Pollinations (`text.pollinations.ai`) in Settings → Endpoints.
2. Open the model picker. Observe: these providers show a generic placeholder icon rather than their logo.
3. Add an OpenAI endpoint (`api.openai.com`) alongside a Google Gemini endpoint. Observe: the OpenAI entry may show the Google Gemini logo.

**Root cause:**

`_PROVIDERS` in `static/js/providers.js` (or equivalent) uses first-match URL pattern matching. Two bugs:

1. **Missing entries:** Groq, Together, Fireworks, and Pollinations have no entries in `_PROVIDERS`. Their API domains return no match, so the generic placeholder icon is shown.

2. **Ordering bug — Google catches OpenAI:** The Google Gemini catch-all entry (`google.com`) appears before the OpenAI entry in the list. `models.openai.com` contains `openai.com` which does not contain `google.com`, but if the matching logic is substring-based and the list order matters, placing Google's broad catch-all before more specific entries causes misidentification. The fix moves Google's entry to appear after all OpenAI-family entries.

Additionally, the Ollama Cloud entry (`ollama.ai`) is duplicated — two entries with the same host and logo.

**Expected:** Each provider domain matches its own logo. The Google Gemini logo appears only for Gemini/Google AI Studio endpoints. Ollama Cloud appears once.

**Affected file:** `static/js/providers.js` (or wherever `_PROVIDERS` is defined)
