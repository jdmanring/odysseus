# Upstream Issue Draft: fix-api-hosts-provider-gaps

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-api-hosts-provider-gaps.md`
**Branch:** `fix/api-hosts-provider-gaps`
**Type:** Bug

---

## Title

`[Agent] Five provider domains missing from _API_HOSTS — tool schemas not injected for Google AI Studio, Pollinations, Moonshot, Together, BigModel`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Problem:**

`_API_HOSTS` in `src/agent_loop.py` gates tool-call schema injection: if the endpoint host is not recognized, tool schemas are not sent. The following provider domains are missing:

| Provider | Missing domain |
|----------|----------------|
| Google AI Studio (direct API) | `generativelanguage.googleapis.com` |
| Pollinations | `text.pollinations.ai` |
| Moonshot AI | `api.moonshot.cn` |
| Together AI | `api.together.ai` |
| Zhipu AI / BigModel | `open.bigmodel.cn` |

Users who configure these endpoints can send messages and get responses, but agent sessions with these providers run without tool calling even when the underlying models support it. There is no error — tools are silently absent from the request payload.

**Steps to reproduce:**

1. Add a Together AI endpoint (`api.together.ai`) in Settings → Endpoints.
2. Select a Together model that supports tool calling.
3. Start an agent session with a task that requires tool use.
4. Observe: the agent does not offer tools. Check the outgoing request payload — no `tools` key is present.

**Expected:** All five domains are recognized as valid API hosts and tool schemas are injected when the selected model supports tool calling.

**Affected file:** `src/agent_loop.py` — `_API_HOSTS`
