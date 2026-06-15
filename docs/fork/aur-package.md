# Agent Handoff: AUR Package

## Status
PLANNING — nothing written yet. Blockers identified. Read the full document
before starting. Also read `docs/fork/build-linux-app.md` first — the AUR
package depends on that script existing and working.

---

## Goal

A PKGBUILD that lets any Arch/Artix user install Odysseus (this fork) with:
```
yay -S odysseus-jdmanring
```

The package installs the app to `/opt/odysseus`, sets up the venv, and runs
`build-linux-app.sh` to install the desktop integration. After install the user
gets a fully native KDE/Linux app indistinguishable from one from the official repos.

---

## Blockers to resolve before writing the PKGBUILD

### 1. Python version compatibility (MUST resolve first)

The repo currently runs on Python 3.14.5. Arch official repos ship Python 3.13
(as of mid-2026). Python 3.14 is not in the official repos or AUR as a stable
package.

**Action**: Test whether Odysseus runs correctly on Python 3.12 or 3.13.

```bash
# Create a test venv with system python
python3.13 -m venv /tmp/odysseus-test-venv
/tmp/odysseus-test-venv/bin/pip install -r requirements.txt
/tmp/odysseus-test-venv/bin/uvicorn app:app --host 127.0.0.1 --port 7001
# Hit localhost:7001 and exercise core features
```

If it works: PKGBUILD uses `depends=('python')` (Arch's current Python, whatever
version that is). The venv will be created with the system Python.

If it breaks: investigate which 3.14-specific syntax or APIs are used. Most
likely candidates are type annotation syntax (`X | Y`, `type` statement) — these
can often be backported with minor changes or avoided.

Do NOT proceed with the PKGBUILD until this is confirmed.

### 2. `fastembed` compiled dependencies

`fastembed` downloads ONNX Runtime on first use (~200MB). This cannot happen
during `makepkg` (no network access, and it's user-specific cache).

**Decision already made**: accept this. The first time a user opens Odysseus and
uses a RAG/memory feature, fastembed will download its model. This is standard
behavior for ML packages and should be noted in the package description.

### 3. No pyproject.toml `[project]` section

The project has no installable package metadata — it is designed to run in-place.
The PKGBUILD will therefore NOT use `pip install .`. Instead it copies the repo
tree to `/opt/odysseus` and creates the venv there.

---

## PKGBUILD design

### Install location

```
/opt/odysseus/          — repo tree (all source files)
/opt/odysseus/venv/     — Python virtualenv
```

The `build-linux-app.sh` script (once written) handles the user-level desktop
integration (`~/.local/bin/`, `.desktop` files). It is run as a post-install
message instruction, not as a root hook — desktop integration is per-user and
must not run as root.

### Package metadata

```bash
pkgname=odysseus-jdmanring
pkgver=0                  # set dynamically from LKG tags — see versioning below
pkgrel=1
pkgdesc="Self-hosted AI workspace — jdmanring fork with native KDE desktop integration"
arch=('x86_64')
url="https://github.com/jdmanring/odysseus"
license=('MIT')
depends=(
    'python'
    'python-pyqt6'
    'python-pyqt6-webengine'
    'tmux'
    'lsof'               # used by odysseus-app shutdown hook
)
makedepends=('git')
source=("git+https://github.com/jdmanring/odysseus.git#tag=LKG-LATEST")
sha256sums=('SKIP')
```

### Versioning from LKG tags

LKG tags are created by the sync pipeline on every successful upstream ingest.
Format: `LKG-YYYYMMDD-HHMM` (e.g. `LKG-20260605-1729`).

The PKGBUILD `pkgver()` function converts this to a valid pacman version:

```bash
pkgver() {
    cd "$pkgname"
    git describe --tags --abbrev=0 | sed 's/LKG-//' | sed 's/-/./g'
    # LKG-20260605-1729 → 20260605.1729
}
```

This means every new LKG tag = new package version = `yay -Syu` picks it up.

### `build()` function

```bash
build() {
    cd odysseus
    python -m venv venv
    venv/bin/pip install --no-cache-dir -r requirements.txt
}
```

### `package()` function

```bash
package() {
    cd odysseus

    # Install repo tree to /opt/odysseus
    install -dm755 "$pkgdir/opt/odysseus"
    cp -r . "$pkgdir/opt/odysseus/"

    # Remove things that don't belong in the package
    rm -rf "$pkgdir/opt/odysseus/.git"
    rm -rf "$pkgdir/opt/odysseus/tests"
    rm -rf "$pkgdir/opt/odysseus/docs/fork"   # our local planning docs

    # System-wide .desktop and icon for package manager awareness
    # (user still needs to run build-linux-app.sh for full integration)
    install -Dm644 static/icons/odysseus.svg \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/odysseus.svg"
}
```

### `post_install` message

The PKGBUILD `.install` file should print instructions after install:

```
==> Odysseus installed to /opt/odysseus
==> To set up desktop integration (launcher, taskbar icon, native window):
==>   bash /opt/odysseus/build-linux-app.sh
==> On first launch, Odysseus will initialize its database and prompt for setup.
```

---

## Auto-update design

Two mechanisms, both leveraging the LKG tagging system:

### Mechanism 1: yay/AUR update (primary)

Every successful pipeline run creates a new LKG tag. The AUR package's
`pkgver()` reads the latest tag. When the user runs `yay -Syu`, yay checks
for a new pkgver and rebuilds from the new tag.

This requires the AUR package to be submitted and maintained. Updates flow:
```
upstream/dev → (pipeline) → integration + LKG tag → AUR pkgver bump → yay -Syu
```

### Mechanism 2: In-app update check (optional, opt-in)

The `odysseus` start script can check for a newer LKG tag before starting:

```bash
# In ~/.local/bin/odysseus, before starting uvicorn:
if [[ "${ODYSSEUS_AUTO_UPDATE:-false}" == "true" ]]; then
    cd "$REPO"
    git fetch origin --tags -q 2>/dev/null
    LATEST=$(git tag -l "LKG-*" | sort | tail -1)
    CURRENT=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
    if [[ "$LATEST" != "$CURRENT" ]]; then
        echo "Update available: $LATEST (current: $CURRENT)"
        git checkout "$LATEST" -q
        venv/bin/pip install -r requirements.txt -q
        echo "Updated to $LATEST."
    fi
fi
```

Enable via `.env`: `ODYSSEUS_AUTO_UPDATE=true`

This only makes sense for the in-place (non-AUR) install. AUR users get updates
via yay. The two mechanisms are mutually exclusive in practice.

---

## Files to create (in order)

1. `build-linux-app.sh` — see `docs/fork/build-linux-app.md` — **do this first**
2. Test Python version compatibility
3. Write `odysseus-jdmanring.install` (post-install message)
4. Write `PKGBUILD`
5. Test locally with `makepkg -si` in a clean directory
6. Submit to AUR

The PKGBUILD and `.install` file live outside the repo (in an AUR submission
directory), not inside it. They reference the repo as a source.

---

## AUR submission checklist

- [ ] `build-linux-app.sh` written and tested
- [ ] Python 3.13 compatibility confirmed
- [ ] PKGBUILD passes `namcap` with no errors
- [ ] `makepkg -si` from clean directory installs correctly
- [ ] `build-linux-app.sh` runs successfully post-install
- [ ] App launches, server starts, window opens, server stops on close
- [ ] `yay -Syu` picks up a new LKG tag correctly
- [ ] AUR account created / SSH key uploaded to aur.archlinux.org
- [ ] `git clone ssh://aur@aur.archlinux.org/odysseus-jdmanring.git`
- [ ] Push PKGBUILD + .SRCINFO
