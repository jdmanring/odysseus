# PR Draft: feat/qt-native-freebsd-app -> odysseus-dev/odysseus:dev

**Branch:** `feat/qt-native-freebsd-app`
**Status:** Ready to file — **stacks on `feat/qt-native-linux-app`**, file that first
**Base:** cut from `upstream-mirror`, 3 files, +272

---

## Title

`feat(freebsd): native FreeBSD desktop application and install-time memory-stack check`

---

## Summary

Odysseus as a native FreeBSD desktop app, plus the dependency work that makes it
actually install.

### What is in it

- `build-freebsd-app.sh`: XDG launcher, `.desktop` entry, icon, and the verified
  **py312** package set. The prerequisites were previously wrong py311 names, so
  the documented install did not work.
- Semantic memory via the llama.cpp backend (`py312-llama-cpp-python`).
- `tooling/verify_memory_stack.py`, run at install time, so a broken memory stack
  is reported during install rather than discovered later as silently degraded
  recall.
- `pkill`/`pgrep` `FileNotFoundError` guards in `qt_wrapper.py` — those binaries
  are not where the Linux path assumes.

### A limitation stated in the branch rather than hidden

**`fastembed` does not work on FreeBSD** — a numpy pin conflicting with
`py-rust-stemmers` and `mmh3` source builds. Memory runs **keyword-only** there.

That is documented in the build script rather than left for a user to discover
through poor recall quality. A degraded mode that announces itself is a different
thing from one that does not.

### Also in this branch

`fix(install): ASCII-only verifier output` — the em-dash in the verifier's output
mangled on the Windows console. Install-time output has to survive every console
it might be read on.

---

## Verification

The branch carries **no Python test files**, which should be stated plainly: it
is a build script, an install hook and a platform guard, all of which are
exercised by running the install on FreeBSD rather than by unit test.

It was **bench-verified on FreeBSD**: the app builds, launches and runs, and the
memory-stack verifier reports the keyword-only state correctly.

The `qt_wrapper.py` guards it adds are covered by the Linux wrapper's suite on
its own branch.

---

## Scope

`build-freebsd-app.sh` (+159), `install.sh` (+24), `tooling/verify_memory_stack.py`
(+89).
