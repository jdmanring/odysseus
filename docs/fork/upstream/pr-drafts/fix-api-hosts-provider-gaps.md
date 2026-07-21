# PR Draft: fix/api-hosts-provider-gaps → odysseus-dev/odysseus:dev

**Branch:** `fix/api-hosts-provider-gaps`
**Fork issue:** [#62](https://github.com/jdmanring/odysseus/issues/62) (open)
**Status:** Single clean commit (`4047e40a`). File upstream issue first, fill in `Fixes #___`, then open PR.

---

## Upstream PR title

`fix(agent): expand _API_HOSTS to cover provider secondary domains and proxies`

---

## Summary

### Problem

`_API_HOSTS` is a frozenset of hostname substrings. The expression:

```python
_is_api_model = any(h in endpoint_url for h in _API_HOSTS) or _model_supports_tools
```

determines whether to send OpenAI-style function schemas (`True`) or fall back to
fenced-block tool descriptions (`False`). When neither arm matches, tool results are
also routed through `untrusted_context_message()` as `role: "user"` instead of
`role: "tool"`, degrading reliability for models that support structured tool calling.

Five provider endpoints are missing from `_API_HOSTS`, causing silent degradation:

| Provider | Missing hostname | Notes |
|----------|-----------------|-------|
| Google Gemini (OpenAI compat) | `generativelanguage.googleapis.com` | `/v1beta/openai` path; official OpenAI-compat adapter |
| Pollinations AI | `pollinations.ai` | `text.pollinations.ai/openai`; free OpenAI-compatible proxy |
| Kimi / Moonshot CN | `moonshot.cn` | `api.moonshot.cn`; domestic CN endpoint, distinct from `api.kimi.com` |
| Together AI (secondary) | `together.ai` | `api.together.ai`; primary `api.together.xyz` is already listed |
| Zhipu / BigModel | `bigmodel.cn` | `open.bigmodel.cn`; GLM models, OpenAI-compat endpoint |

For Google Gemini, model names (`gemini-2.0-flash`, `gemini-1.5-pro`) contain no
keyword in `_model_supports_tools`, so the belt-and-suspenders path also fails.

For Together AI's secondary domain, `api.together.xyz` is listed but `api.together.ai`
is not; users who configure the `.ai` domain get degraded behavior.

### Fix

**`src/agent_loop.py` — `_API_HOSTS`:**

```python
# Provider secondary domains and endpoints whose model names do not
# contain a keyword in _model_supports_tools — without explicit host
# coverage they silently degrade to fenced-block tool calling.
"generativelanguage.googleapis.com",  # Google Gemini OpenAI-compat
"pollinations.ai",                    # text.pollinations.ai proxy
"moonshot.cn",                        # api.moonshot.cn (Kimi/Moonshot CN)
"together.ai",                        # api.together.ai (Together secondary)
"bigmodel.cn",                        # open.bigmodel.cn (Zhipu GLM)
```

Substring matching means `"pollinations.ai"` matches both `text.pollinations.ai`
and any other subdomain of that provider. `"moonshot.cn"` matches `api.moonshot.cn`
without conflicting with the existing `"api.kimi.com"` entry.

### What is not changed

`_model_supports_tools` is not modified by this PR. That keyword list is a
belt-and-suspenders fallback for model names served via arbitrary hosts (e.g. Nemotron
on a self-hosted vLLM instance). The host list is the primary gate and is the correct
place for this fix since all five providers have known, stable hostnames.

### Scope

One file changed: `src/agent_loop.py` (+8 lines in `_API_HOSTS`). No tests exist
for `_API_HOSTS` membership in the current test suite; the fix is trivially verifiable
by inspection.

---

## Related upstream work (prior-art search, 2026-07-07)

Searched merged commits and open issues/PRs on `dev`:

- **#4729** (merged) *detect llama.cpp servers and label local providers* — **complements; distinct path.** #4729 is provider *discovery/labeling* (fingerprinting local serving ports via `/props`); this PR extends the `_API_HOSTS` allowlist that decides which endpoints receive native tool schemas. No shared code, no conflict.
- **#5206** (open) *per-endpoint native tool-calling toggle in Added Models* — **complements.** #5206 adds a manual per-endpoint override; this PR fixes the *default* host detection so well-behaved providers get native schemas without manual toggling. Valid regardless of merge order — worth a note to the reviewer to coordinate.

**Verdict:** complements; not a duplicate. If #5206 lands first, this remains the sensible default-detection fix beneath the toggle.

## How to Test

For each provider below, configure the endpoint and start an Agent session with at
least one tool enabled. Verify the request payload contains a `tools` array (not
fenced-block system-prompt descriptions), and that tool results are sent as
`role: "tool"` messages.

| Provider | Endpoint to configure |
|----------|----------------------|
| Google Gemini (OpenAI compat) | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Pollinations AI | `https://text.pollinations.ai/openai` |
| Kimi / Moonshot CN | `https://api.moonshot.cn/v1` |
| Together AI (secondary) | `https://api.together.ai/v1` |
| Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4` |

Also verify that the existing primary `api.together.xyz` endpoint is unaffected.

---

## Filing Notes

- Single commit (`4047e40a`). No squash needed.
- Branch: `fix/api-hosts-provider-gaps` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #___` before opening.
- PR targets `odysseus-dev/odysseus:dev`.
- `fix/nvidia-native-tool-calling` addresses the same class of bug for NVIDIA NIM and
  can be filed separately or bundled. They are independent commits on separate branches.

## Visual / UI changes

None. Backend-only change.

## Target branch

- [x] This PR targets **`dev`**, not `main`.

## Linked Issue

Fixes # <!-- [add upstream issue number before filing] -->

## Type of Change

- [x] Bug fix (non-breaking, fixes a confirmed issue)
- [ ] New feature (non-breaking, adds new behaviour)
- [ ] Breaking change (changes or removes existing behaviour)
- [ ] Refactor / cleanup (behaviour unchanged)
- [ ] Documentation only
- [ ] CI / tooling / configuration

## Checklist

- [x] I searched [open issues](https://github.com/odysseus-dev/odysseus/issues) and [open PRs](https://github.com/odysseus-dev/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.
