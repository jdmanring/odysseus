# PR Draft: fix/hf-token-env-fallback

**Fork issue:** [#34](https://github.com/jdmanring/odysseus/issues/34)
**Branch:** `fix/hf-token-env-fallback` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`

---

## Proposed title

`fix(cookbook): fall back to HF_TOKEN env var in _load_stored_hf_token()`

---

## PR description (for upstream reviewers)

### Problem

`_load_stored_hf_token()` in `routes/cookbook_routes.py` reads only from
`data/cookbook_state.json`. When no token has been saved via the Cookbook UI,
it returns `""` — even if `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` is set in
the process environment.

This affects Linux users, Docker setups, and CI environments that set the token
via env var rather than the Cookbook settings UI. The symptoms:

- `[odysseus] HF token: NOT SET — gated/private models will be denied.` appears
  in the log even though the env var is present and correct.
- The generated download script omits the explicit `export HF_TOKEN=...` line
  (guarded by `if req.hf_token:` at line ~479). The subprocess *inherits* the
  env var, so the download itself still works — but only by accident, and the
  warning is misleading.
- `_validate_token()` is called on `""`, which produces an unhelpful validation
  state.

### Fix

Prefer the stored (encrypted) token from `cookbook_state.json`; fall back to
`HF_TOKEN`, then `HUGGING_FACE_HUB_TOKEN`:

```python
def _load_stored_hf_token() -> str:
    if _cookbook_state_path.exists():
        try:
            state = json.loads(_cookbook_state_path.read_text(encoding="utf-8"))
            env = state.get("env") if isinstance(state, dict) else {}
            stored = _decrypt_secret(env.get("hfToken") if isinstance(env, dict) else "")
            if stored:
                return stored
        except Exception:
            pass
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or ""
```

The stored token always takes priority, so a token set in the Cookbook UI is
never silently shadowed by an env var. The fallback only fires when no stored
token exists or the state file is unreadable.

`HUGGING_FACE_HUB_TOKEN` is the older canonical name used by `huggingface_hub`
before `HF_TOKEN` was standardised; both are checked for compatibility.

### Relation to other work

- PR #3459 (`fix: detect HuggingFace token when downloading cookbook models`,
  merged) fixed a duplicate JS handler that cleared the token on save and added
  `_load_stored_hf_token()` as a backend fallback. This PR completes that
  fallback by also checking the environment.
- PR #3864 (`fix(cookbook): point HF token hint at Cookbook -> Settings`, open)
  fixes the hint message text. Orthogonal — no file overlap.

### Testing

1. Set `HF_TOKEN` in your shell environment; do **not** save a token via
   Cookbook → Settings → HuggingFace Token.
2. Start Odysseus and attempt to download a gated model.
3. Confirm the log shows `[odysseus] HF token: applied` (not `NOT SET`).
4. Confirm the generated download script contains `export HF_TOKEN=...`.
5. Set a token via Cookbook → Settings and confirm it takes priority over the
   env var (stored token is returned, not the env var value).

### Files changed

| File | Change |
|------|--------|
| `routes/cookbook_routes.py` | 10 insertions, 8 deletions — `_load_stored_hf_token()` only |

---

## Filing notes

1. No upstream issue needed first — open the PR directly. Reference upstream
   #3829 and PR #3459 in the description for context.
2. Target branch: `dev` (not `main`).
3. This is a pure Python change; no JS, HTML, or CSS files touched.
4. The change is backward-compatible: behaviour is identical when a stored
   token exists; the fallback only fires when the function previously returned `""`.
