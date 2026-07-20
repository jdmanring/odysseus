"""tooling/macos_dock_pin.rebuild_persistent_apps (#158 icon-install).

A reinstall changes the .app inode, so an existing pin's cached "book" bookmark
goes stale and the tile shows blank when the app is closed. The rebuild must
drop the stale entry and re-add a URL-only tile (no bookmark) so the Dock
re-resolves the current bundle icon.
"""
from tooling.macos_dock_pin import rebuild_persistent_apps

APP_URL = "file:///Applications/Odysseus.app/"
BID = "com.odysseus.app"


def _stale_entry():
    return {
        "tile-type": "file-tile",
        "tile-data": {
            "bundle-identifier": BID,
            "book": b"\x00stale-bookmark-blob",
            "file-data": {"_CFURLString": APP_URL, "_CFURLStringType": 15},
        },
    }


def _other(url, bid=None):
    td = {"file-data": {"_CFURLString": url, "_CFURLStringType": 15}}
    if bid:
        td["bundle-identifier"] = bid
    return {"tile-type": "file-tile", "tile-data": td}


def test_replaces_stale_entry_with_url_only_tile():
    apps = [_other("file:///Applications/Safari.app/"), _stale_entry()]
    new, removed = rebuild_persistent_apps(apps, APP_URL, BID)
    assert removed == 1
    # Safari untouched, exactly one Odysseus entry, and it carries NO bookmark.
    ody = [e for e in new if "Odysseus" in e["tile-data"]["file-data"]["_CFURLString"]]
    assert len(ody) == 1
    assert "book" not in ody[0]["tile-data"]
    assert ody[0]["tile-data"]["file-data"]["_CFURLString"] == APP_URL
    assert len(new) == 2


def test_matches_by_bundle_id_even_if_url_differs():
    apps = [_other("file:///Users/me/Desktop/Odysseus.app/", bid=BID)]
    new, removed = rebuild_persistent_apps(apps, APP_URL, BID)
    assert removed == 1
    assert len(new) == 1


def test_matches_by_path_when_no_bundle_id():
    apps = [_other(APP_URL)]  # no bundle-identifier key
    new, removed = rebuild_persistent_apps(apps, APP_URL, BID)
    assert removed == 1
    assert len(new) == 1


def test_pins_fresh_when_not_previously_present():
    apps = [_other("file:///Applications/Mail.app/")]
    new, removed = rebuild_persistent_apps(apps, APP_URL, BID)
    assert removed == 0
    assert len(new) == 2
    assert new[-1]["tile-data"]["file-data"]["_CFURLString"] == APP_URL


def test_does_not_touch_unrelated_apps():
    apps = [_other("file:///Applications/Notes.app/", bid="com.apple.Notes")]
    new, _ = rebuild_persistent_apps(apps, APP_URL, BID)
    assert any(e["tile-data"]["file-data"]["_CFURLString"].endswith("Notes.app/")
               for e in new)
