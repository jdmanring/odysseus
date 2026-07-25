# Upstream Issue Draft: fix-searxng-json-docs

**File on:** `odysseus-dev/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-searxng-json-docs.md`
**Branch:** `fix/searxng-json-docs`
**Type:** Bug / Documentation gap

---

## Title

`[Search] SearXNG integration silently returns HTTP 404: JSON output format requirement not documented anywhere`

---

## Body

**Install method:** Docker / manual Python

**OS / device:** Any

**Browser (if applicable):** Any

**Steps to Reproduce:**
1. Set up a default SearXNG instance (without manually enabling JSON output format in its `settings.yml`).
2. Set `SEARXNG_INSTANCE` in `.env` to point to that instance.
3. Perform any search in Odysseus.

**Expected:** Either the search succeeds, or a clear error message explains that SearXNG requires JSON output to be enabled.

**Actual:** Every search silently fails. The Odysseus search panel shows a failure with no explanation. The underlying cause (HTTP 404 from the SearXNG instance because JSON output is disabled) is not surfaced to the user and is not documented anywhere in the repository.

**Logs / Error Output:**
HTTP 404 returned by the SearXNG instance for all JSON-format search requests.

**Additional context:** SearXNG disables its JSON output format by default. Odysseus requests search results in JSON format, which causes a 404 on any default SearXNG install. To fix, users must add the following to their SearXNG `settings.yml`:

```yaml
search:
  formats:
    - html
    - json
```

This requirement is not mentioned in `.env.example`, `README.md`, or any other file in the repository. It is a common setup stumbling block that produces a confusing failure with no guidance.
