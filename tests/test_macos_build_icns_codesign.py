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


def test_iconset_prefers_svg_falls_back_to_png():
    assert "rsvg-convert -w" in SH   # SVG path: native-resolution render
    assert "sips -z" in SH           # PNG fallback: resize from 512
    # Honesty: the PNG fallback upscales past the source.
    assert "upscaled" in SH


def test_adhoc_codesign_applied_and_not_overclaimed():
    assert "codesign --force --deep --sign - " in SH
    assert "Signature=adhoc" in SH
    # Must not claim Gatekeeper/notarization.
    assert "NOT Gatekeeper/notarized" in SH


def test_codesign_before_dmg_packaging():
    # Sign the bundle before hdiutil so the .dmg carries the signature.
    assert SH.index("codesign --force") < SH.index("hdiutil create")
