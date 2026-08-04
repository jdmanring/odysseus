# PR Draft: feat/qt-native-openbsd-app -> odysseus-dev/odysseus:dev

**Branch:** `feat/qt-native-openbsd-app`
**Status:** Ready to file — **stacks on `feat/qt-native-linux-app` and
`feat/qt-native-freebsd-app`**, file both first
**Base:** cut from `upstream-mirror`, 1 file, +94

---

## Title

`feat(openbsd): add build-openbsd-app.sh`

---

## Summary

Installs Odysseus as a native OpenBSD desktop application: XDG launcher,
`.desktop` entry, icon.

The script checks for PyQt6 WebEngine in the venv (from pip) and otherwise
instructs the user to install from ports:

```
pkg_add qt6-qtwebengine py3-pyqt6-webengine
```

**amd64 and aarch64 only** — QtWebEngine is not available for other OpenBSD
architectures, and the script says so rather than failing obscurely partway
through.

### Dependencies

This is the smallest of the platform branches because it inherits nearly
everything:

- `feat/qt-native-linux-app` supplies `qt_wrapper.py`
- `feat/qt-native-freebsd-app` supplies the `pkill`/`pgrep` `FileNotFoundError`
  guards, which OpenBSD needs for the same reason FreeBSD does

Filed on its own because the packaging differs and nothing else does. If the two
prerequisites are not merged, this branch is just a script referencing a wrapper
that is not there.

---

## Verification

**No test files**, stated plainly: the branch is a single install script.

It was **bench-verified on OpenBSD** — the app builds, launches and runs, with
the provisioning notes (`py3-qt6webengine`, `--system-site-packages`,
`py3-python-multipart`) recorded in the fork's platform documentation.

---

## Scope

`build-openbsd-app.sh` (+94). No application code.
