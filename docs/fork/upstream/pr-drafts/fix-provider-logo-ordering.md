# PR Draft: fix/provider-logo-ordering → pewdiepie-archdaemon/odysseus:dev

**Branch:** `fix/provider-logo-ordering`
**Fork issue:** [#59](https://github.com/jdmanring/odysseus/issues/59) (open)
**Status:** Single clean commit (`a35b1b1d`). File upstream issue first, fill in `Fixes #___`, then open PR.

---

## Upstream PR title

`fix(providers): add missing logos and fix first-match ordering for OpenAI-path providers`

---

## Summary

### Problem

`_PROVIDERS` in `static/js/providers.js` is a first-match array: the first regex that
matches a model ID or endpoint URL wins the logo. Providers whose API endpoint path
contains the substring `openai` (e.g. `/openai/v1`) must appear **before** the OpenAI
entry (`/openai|gpt-|.../i`) or they receive the OpenAI logo instead of their own.

Four providers were missing from `_PROVIDERS` entirely, and Google Gemini was placed
**after** OpenAI. The affected endpoints:

| Provider | Endpoint | Why wrong logo |
|----------|----------|---------------|
| Groq | `api.groq.com/openai/v1` | `/openai/v1` in path → OpenAI logo |
| Together AI | `api.together.xyz/v1` or `api.together.ai/v1` | no entry → no logo |
| Fireworks AI | `api.fireworks.ai/inference/v1` | no entry → no logo |
| Pollinations AI | `text.pollinations.ai/openai` | `/openai` in path → OpenAI logo if present |
| Google Gemini | `generativelanguage.googleapis.com/v1beta/openai` | `/openai` in path → OpenAI logo |

Additionally:
- A duplicate Ollama Cloud entry existed after the primary Ollama entry (dead code,
  different SVG path).
- The xAI regex `/x-ai|xai|grok/i` did not match the actual API hostname `api.x.ai`
  (the `x.ai` dot is a regex wildcard in this context — `x\.ai` is required).
- Pollinations AI had no entry in `_ENDPOINT_LABELS`, so its hostname displayed raw
  instead of as "Pollinations".
- Pollinations AI was missing from the quick-add provider dropdown in `index.html`.

### Fix

**`static/js/providers.js`:**

Five entries added to `_PROVIDERS` before the OpenAI entry, with ordering comments:

```js
// Groq — must precede OpenAI: endpoint path contains /openai/v1
[/groq/i, '<svg ...lightning bolt.../>'],

// Together AI — must precede OpenAI: endpoint path may contain /openai/v1
// Three Venn-diagram circles — evenodd punches slots at pairwise intersections
[/together/i, '<svg fill-rule="evenodd" .../>'],

// Fireworks AI — must precede OpenAI: endpoint path may contain /openai/v1
[/fireworks/i, '<svg .../>'],

// Pollinations AI — must precede OpenAI: endpoint path contains /openai
[/pollinations/i, '<svg ...five petal circles + centre.../>'],

// Google Gemini — must precede OpenAI: endpoint path /v1beta/openai contains "openai"
[/google|gemini|gemma/i, '<svg ...Gemini star.../>'],
```

Google Gemini entry **moved** from its previous position (after OpenAI) to before it.

Duplicate Ollama Cloud entry removed (the primary Ollama entry at the top of the array
already matches; the second entry was dead code with a different SVG path).

xAI regex corrected: `/x-ai|xai|grok/i` → `/x-ai|xai|x\.ai|grok/i`

`_ENDPOINT_LABELS` extended:
```js
[/(^|\.)pollinations\.ai$/i, "Pollinations"],
```

**`static/index.html`:**

Pollinations AI added to the quick-add provider dropdown:
```html
<option value="https://text.pollinations.ai/openai" data-logo="pollinations">Pollinations AI</option>
```

### Scope

- `static/js/providers.js` — +24 / -10 lines
- `static/index.html` — +1 line
- `tests/test_groq_together_fireworks_logos_js.py` — new, 17 tests

---

## How to Test

1. Open Settings → AI Defaults. Confirm the quick-add dropdown contains "Pollinations AI".
2. Set each endpoint below and confirm the correct logo appears in the endpoint name field:
   - `https://api.groq.com/openai/v1` → Groq logo (lightning bolt), not OpenAI ring
   - `https://api.together.xyz/v1` → Together AI logo (three circles), not OpenAI ring
   - `https://api.fireworks.ai/inference/v1` → Fireworks logo, not OpenAI ring
   - `https://text.pollinations.ai/openai` → Pollinations logo (flower), not OpenAI ring
   - `https://generativelanguage.googleapis.com/v1beta/openai` → Gemini star, not OpenAI ring
3. Set endpoint `https://api.x.ai/v1` — confirm xAI logo (X), not a fallback.
4. Confirm there is no duplicate Ollama entry in the provider logo section.

### Tests

`tests/test_groq_together_fireworks_logos_js.py` (17 tests, run via Node.js):

| Class | Tests |
|-------|-------|
| `TestGroqLogo` | model-ID match; URL match; not-OpenAI-logo |
| `TestTogetherLogo` | model-ID match; .xyz URL; .ai URL; not-OpenAI-logo; SVG has `evenodd` |
| `TestFireworksLogo` | model-ID match; URL match; not-OpenAI-logo |
| `TestPollinationsLogo` | model-ID match; URL match; not-OpenAI-logo |
| `TestGoogleGeminiLogo` | model-ID match; googleapis URL match; not-OpenAI-logo |

Run directly with Node (pytest conftest requires a full environment):
```
node --input-type=module - < tests/test_groq_together_fireworks_logos_js.py  # (see test file for runner approach)
```
Or run all 17 assertions inline as shown in the test file's Node.js subprocess pattern.

---

## Filing Notes

- Single commit (`a35b1b1d`). No squash needed.
- Branch: `fix/provider-logo-ordering` — built from `upstream-mirror`.
- **File upstream issue first.** Add the upstream issue number to `Fixes #___` before opening.
- PR targets `pewdiepie-archdaemon/odysseus:dev`.

## Visual / UI changes

This PR changes which logo SVG is rendered for Groq, Together AI, Fireworks AI,
Pollinations AI, Google Gemini, and xAI endpoints. Screenshots required:

- Provider list or endpoint name chip showing the correct logo for each affected provider
- Quick-add dropdown showing "Pollinations AI" entry

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

- [x] I searched [open issues](https://github.com/pewdiepie-archdaemon/odysseus/issues) and [open PRs](https://github.com/pewdiepie-archdaemon/odysseus/pulls); this is not a duplicate.
- [x] This PR targets `dev`
- [x] My changes are limited to the scope described above; no unrelated refactors or whitespace changes mixed in.
- [ ] **I am not an LLM agent submitting a bulk PR.** I reviewed and tested this change personally before submitting.
