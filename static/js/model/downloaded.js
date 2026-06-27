// static/js/model/downloaded.js
//
// Pure helper for "is this catalog model already downloaded?". No DOM, so it is
// safe to import anywhere and to unit-test under node.
//
// This is the single source of truth for that decision. It used to be
// reimplemented at every render site (the downloaded dot, the card greying, the
// serve gate, the row re-mark) with subtly different rules. Most copies matched
// only on the catalog name, so a model downloaded from an auto-discovered
// quant repo (e.g. catalog name "meta-llama/Meta-Llama-3.1-8B-Instruct" but the
// file actually pulled from "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF") was
// reported as not-downloaded by some sites and downloaded by others. That split
// is the bug that kept regressing; keep every caller pointed here.

// Collect the identities a catalog model may be known by, independent of which
// quant was actually downloaded. Accepts a model object, a bare id string, or an
// array of id strings (used by the row re-mark, which only carries strings).
export function modelIdentities(model) {
  const full = new Set();
  const add = (v) => { if (typeof v === 'string' && v) full.add(v); };
  if (typeof model === 'string') {
    add(model);
  } else if (Array.isArray(model)) {
    model.forEach(add);
  } else if (model) {
    add(model.name);
    add(model.repo_id);
    add(model.quant_repo);
    if (Array.isArray(model.gguf_sources)) {
      model.gguf_sources.forEach((s) => add(s && s.repo));
    }
  }
  const short = new Set([...full].map((id) => id.split('/').pop()));
  return { full, short };
}

// True if any of the model's identities is present in the downloaded-id set.
// Full-id matches are preferred; the short-name (last path segment) match is a
// guarded fallback for the cases where the cache and the catalog disagree on
// whether the org prefix is present.
export function isModelDownloaded(model, cachedIds) {
  if (!cachedIds || !cachedIds.size) return false;
  const { full, short } = modelIdentities(model);
  for (const id of full) {
    if (cachedIds.has(id)) return true;
  }
  for (const s of short) {
    if (cachedIds.has(s)) return true;
    for (const c of cachedIds) {
      if (c.endsWith('/' + s)) return true;
    }
  }
  return false;
}
