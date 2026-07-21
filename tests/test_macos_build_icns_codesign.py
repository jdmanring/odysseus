"""build-mac-app.sh polish contract (#158): multi-res icns + ad-hoc codesign.

Verified live on the Tahoe bench: the iconset round-trips through iconutil with
all 10 slots (16/32/128/256/512 + @2x), and codesign -dv reports Signature=adhoc.
"""
from pathlib import Path

SH = Path("build-mac-app.sh").read_text(encoding="utf-8")


def test_builds_multires_iconset_via_iconutil():
    assert "iconutil -c icns" in SH
    assert "make_iconset" in SH
    # Each base size emitted at 1x and @2x — the slots iconutil requires.
    assert 'ICON_BASE_SIZES="16 32 128 256 512"' in SH
    assert 'icon_${base}x${base}.png' in SH
    assert 'icon_${base}x${base}@2x.png' in SH


def test_iconset_prefers_macos_tile_then_svg_then_png():
    # Primary source is the composed macOS tile (dark rounded-rect + glyph);
    # SVG and the bare transparent 512 are fallbacks only.
    assert "icon-macos-1024.png" in SH
    assert SH.index('MACOS_SRC="') < SH.index('SVG_SRC="') < SH.index('PNG_SRC="')
    assert "rsvg-convert -w" in SH   # SVG fallback: native-resolution render
    assert "sips -z" in SH           # raster path: resize
    # The macOS tile must be tried first in the build cascade.
    assert SH.index('[ -f "$MACOS_SRC" ]') < SH.index('[ -f "$SVG_SRC" ]')


def test_adhoc_codesign_applied_and_not_overclaimed():
    assert "codesign --force --deep --sign - " in SH
    assert "Signature=adhoc" in SH
    # Must not claim Gatekeeper/notarization.
    assert "NOT Gatekeeper/notarized" in SH


def test_codesign_before_dmg_packaging():
    # Sign the bundle before hdiutil so the .dmg carries the signature.
    assert SH.index("codesign --force") < SH.index("hdiutil create")


def test_launcher_marks_bundle_so_tile_is_not_overridden():
    # The launcher exports ODYSSEUS_BUNDLE so the wrapper leaves the Dock tile to
    # the bundle .icns (setWindowIcon would otherwise swap it at runtime).
    assert "export ODYSSEUS_BUNDLE=1" in SH


def test_installs_by_default_like_other_platforms():
    # macOS must install in one run (to /Applications + Dock pin) like the
    # Linux/*BSD/Windows installers, so `./install.sh` behaves the same
    # everywhere. --build-only opts out.
    assert "DO_INSTALL=1" in SH
    assert "--build-only|--no-install) DO_INSTALL=0" in SH


def test_installsh_runs_openbsd_with_sh_not_bash():
    installsh = (Path("install.sh")).read_text(encoding="utf-8")
    # build-openbsd-app.sh is #!/bin/sh (no bash in OpenBSD base); the dispatcher
    # must not force bash.
    assert 'exec sh "$SCRIPT_DIR/build-openbsd-app.sh"' in installsh
    assert 'exec bash "$SCRIPT_DIR/build-openbsd-app.sh"' not in installsh


def test_launcher_prepends_tool_path_dirs():
    # A Finder/Dock/open-launched .app inherits launchd's minimal PATH, so the
    # server preflight can't see a Homebrew/user-installed aria2c and downloads
    # silently fall back to hf. The launcher must prepend the usual bin dirs.
    assert 'export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:$HOME/.local/bin:$HOME/bin:$PATH"' in SH


def test_macos_tile_asset_present_and_dark():
    from PIL import Image
    p = Path("static/icons/icon-macos-1024.png")
    assert p.exists(), "composed macOS tile asset missing"
    im = Image.open(p).convert("RGBA")
    assert im.size == (1024, 1024)
    assert im.getpixel((5, 5))[3] == 0, "corners must be transparent (baked rounding)"
    # Interior is the dark tile, not empty.
    assert im.getpixel((512, 180))[:3] == (40, 44, 52)


def test_wrapper_skips_setwindowicon_when_bundled():
    W = Path("mac_wrapper.py").read_text(encoding="utf-8")
    assert 'if not os.environ.get("ODYSSEUS_BUNDLE"):' in W
    # Dev-run fallback uses the macOS tile first.
    i = W.index('if not os.environ.get("ODYSSEUS_BUNDLE"):')
    assert "icon-macos-1024.png" in W[i:i + 400]
