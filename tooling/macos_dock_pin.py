"""Pin (or re-pin) an app to the macOS Dock with a fresh icon reference.

Reinstalling a .app changes its inode, so an existing Dock pin's cached bookmark
(the "book" blob) goes stale: the tile then shows blank/white while the app is
NOT running (a running app's tile comes from the live process, so it still looks
right — which is exactly the confusing "white when closed, correct when open"
symptom). Rebuilding the pin as a URL-only entry drops the stale bookmark; the
Dock regenerates the bookmark and resolves the current bundle's .icns on the
next restart.

Used by build-mac-app.sh --install. Goes through cfprefsd via
`defaults export | import` so the change isn't clobbered by the running Dock.
"""
import plistlib
import subprocess
import sys


def _norm(url: str) -> str:
    """Normalize a file URL / path to a bare path for comparison."""
    return url.replace("file://", "").rstrip("/")


def rebuild_persistent_apps(apps, app_url, bundle_id):
    """Pure: drop any existing pin for this app (matched by bundle id or exact
    path) and append a fresh URL-only tile. Returns (new_apps, removed_count).

    URL-only (no cached "book" bookmark) is the whole point: the Dock rebuilds
    the bookmark + icon from the live bundle, so a reinstall's new inode is
    picked up instead of a stale reference.
    """
    target = _norm(app_url)

    def matches(entry):
        td = entry.get("tile-data", {})
        if bundle_id and td.get("bundle-identifier") == bundle_id:
            return True
        return _norm(td.get("file-data", {}).get("_CFURLString", "")) == target

    kept = [e for e in apps if not matches(e)]
    removed = len(apps) - len(kept)
    kept.append({
        "tile-type": "file-tile",
        "tile-data": {
            "file-data": {"_CFURLString": app_url, "_CFURLStringType": 15},
        },
    })
    return kept, removed


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    app_path = argv[0] if argv else "/Applications/Odysseus.app"
    bundle_id = argv[1] if len(argv) > 1 else "com.odysseus.app"
    app_url = "file://" + app_path.rstrip("/") + "/"

    raw = subprocess.run(["defaults", "export", "com.apple.dock", "-"],
                         capture_output=True).stdout
    pl = plistlib.loads(raw)
    pl["persistent-apps"], removed = rebuild_persistent_apps(
        pl.get("persistent-apps", []), app_url, bundle_id)
    subprocess.run(["defaults", "import", "com.apple.dock", "-"],
                   input=plistlib.dumps(pl))
    print(f"dock: removed {removed} stale pin(s), pinned {app_url}")


if __name__ == "__main__":
    main()
