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

// Reduce a repo id to its quant/format-independent base model name. A community
// download carries the base plus a quant/format tag and a different org prefix
// (bartowski/Meta-Llama-3.1-8B-Instruct-GGUF, org/Model-AWQ-4bit, org/Model-NVFP4),
// while the discovered catalog entry carries only the base name and no
// gguf_sources, so the base name is the only thing they share. Strip a trailing
// run of known tags so the two sides line up.
const _TAG = /[-_.](gguf|awq|gptq|nvfp4|fp8|fp16|bf16|int8|int4|imat|i1|exl2|exl3|mlx|hqq|\d+bit|i?q\d[a-z0-9_]*)$/i;
export function baseModelId(id) {
  let s = (typeof id === 'string' ? id : '').split('/').pop().toLowerCase();
  let prev;
  do { prev = s; s = s.replace(_TAG, ''); } while (s !== prev);
  return s.replace(/[-_.]+$/, '');
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
  // Base-model fallback: a discovered catalog model has no gguf_sources, so a
  // downloaded community quant of it shares only the base name. Match on the
  // quant/format-stripped base, but ONLY for catalog identities that are
  // themselves an untagged base name. A catalog entry that already carries its
  // own quant tag (org/Model-AWQ-8bit) must match exactly, so a downloaded 4bit
  // does not gray its 8bit sibling. Length floor stops a tiny base matching broadly.
  const bases = new Set(
    [...short]
      .filter((s) => baseModelId(s) === s.toLowerCase())  // untagged identities only
      .map((s) => s.toLowerCase())
      .filter((b) => b.length >= 4),
  );
  if (bases.size) {
    for (const c of cachedIds) {
      if (bases.has(baseModelId(c))) return true;
    }
  }
  return false;
}
