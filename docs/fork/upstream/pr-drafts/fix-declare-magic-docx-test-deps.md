# PR draft: build(deps): declare python-magic (optional) and python-docx (test-only)

Branch: `fix/declare-magic-docx-test-deps` (from `upstream-mirror`, 1 commit `cf636dfb`)
Fork issue: #136 (stays open until the upstream PR is filed). Base: `dev`.

## Summary

Two dependencies the codebase already relies on are declared nowhere, so three tests
silently skip on every fresh install:

- `src/upload_handler.py` lazy-imports `python-magic` for content-based MIME sniffing
  (with a graceful fallback to basic detection when absent), but no requirements file
  mentions it — `tests/test_upload_content_detection_magic.py` has been skipping
  everywhere. Added to `requirements-optional.txt`, matching the app's
  optional-with-fallback treatment.
- `tests/test_markitdown_runtime.py` builds its fixture `.docx` with `python-docx`,
  also undeclared. Added to the test-dependency cluster in `requirements.txt` with a
  comment marking it test-only.

No change to the markitdown entry itself: `markitdown[docx,pptx,xlsx,xls]==0.1.6` in
`requirements-optional.txt` already carries the `[docx]` extra the runtime needs. (Worth
knowing: installing `python-docx` while markitdown lacks its `[docx]` extra turns the
markitdown test from a skip into a real failure — the extra must come from the declared
entry, which it does.)

## CI impact

None. CI installs only `requirements.txt`, so it now gets `python-docx`; the markitdown
test still short-circuits on `importorskip("markitdown")` (optional file), and the magic
test still skips without `python-magic`. Nothing new runs or fails in CI — the change
benefits anyone installing the optional set, where all three tests now execute.

## Verified

With a venv installed from both requirements files: the three affected tests pass
(real docx→markdown extraction, libmagic content sniffing), full suite
5537 passed / 2 skipped, exit 0. The two remaining skips are structural
(a Windows-only guard on Linux; a scheduling-dependent alternate path whose primary
path is asserted unconditionally).

## Question for the maintainer: pinning policy

Both new entries are unpinned, matching the current convention (`requirements.txt` has
zero `==` pins; `requirements-optional.txt` has exactly one, `markitdown==0.1.6`, pinned
for the #485 release-age reason). #485 settled a 30-day minimum release age for new
dependencies — both entries satisfy it comfortably (`python-magic` 0.4.27 is from 2022,
`python-docx` 1.2.0 is over a year old) — but it did not decide whether entries should be
version-pinned. If you'd rather new entries land pinned (e.g. `python-magic==0.4.27`,
`python-docx==1.2.0`), say the word and this PR will be updated; it seemed wrong to
introduce a pinning convention unilaterally in an unpinned file.

## Filing notes (fork-internal, not part of the PR body)

- Fully independent of every other staged branch; file-able any time. Trivial review
  (8 lines, two comments + two package names).
- Found while converting environment-conditional test skips to passes during the
  DOM-virtualization 3.5 verification work; no code dependency on that work.
