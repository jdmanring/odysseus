# PR Draft: fix/model-downloaded-detection -> odysseus-dev/odysseus:dev

**Branch:** `fix/model-downloaded-detection`
**Status:** Ready to file
**Base:** cut from `upstream-mirror`, 3 commits, 4 files, +267/-18

---

## Title

`fix(cookbook): one canonical "is this model downloaded?" predicate`

---

## Summary

### Problem

The downloaded check was reimplemented inline at **every render site** - the
downloaded dot, the card greying, the serve gate, the row re-mark - with rules
that had drifted apart. Most matched on the catalog name only, so a model held on
disk under a community quant's name did not register as downloaded at some
surfaces and did at others.

The user-visible result is a UI that disagrees with itself about the same model.

### Fix, in three steps

**1. One predicate.** `static/js/model/downloaded.js` becomes the single
`isModelDownloaded`, and every render site calls it. A companion test
(`test_no_adhoc_downloaded_match.py`) fails if a new inline reimplementation
appears, which is the only thing that keeps this from re-fragmenting.

**2. Base-name matching for discovered quants.** Discovered catalog models carry
no `gguf_sources`, so a community quant shares only the base name with the
catalog entry - `leafspark/Llama-3.2-11B-Vision-Instruct-GGUF`,
`nvidia/Qwen3-30B-A3B-NVFP4`, `org/Model-AWQ-4bit`. A quant/format-stripped
base-name fallback makes those register. **Verified against the real on-disk
download set**, with a length floor and distinct-base tests guarding against
over-matching.

**3. The over-match this exposed.** Step 2 was too generous: a catalog entry that
carries its **own** quant tag (`org/Model-AWQ-8bit`) base-matched a downloaded
sibling quant (`org/Model-AWQ-4bit`), so holding the 4-bit greyed out the 8-bit
too. Restricted the fallback to catalog identities that are themselves untagged
base names; tagged entries must match exactly. Untagged base entries still grey
for any held quant, which is the intended behaviour.

The third commit is worth reading as part of the review: the fix for step 2
created a new wrong answer in the opposite direction, and both directions now
have tests.

---

## Verification

**18 passed**, measured 2026-08-03, across the predicate's own tests and the
no-ad-hoc-reimplementation guard.

---

## Scope

`static/js/model/downloaded.js` (new), `static/js/cookbook-hwfit.js`, two test
files.
