"""Eyedropper must never invoke OS screen sampling on software-render machines.

On a GPU-less Mac (VM), NSColorPanel's eyedropper spawns the ColorSampler XPC
service, whose window capture drives WindowServer through SkyLight's software
capture path (CaptureSurfaceSW::Populate) — which aborts, killing WindowServer
and the login session. The wrappers instead emit eyedropperInPage and resolve
samplePagePixel(x, y) against view.grab(), Qt's own offscreen widget render.

Wrappers can't be imported off-target (PyQt + os.dup2 side effects), so the
contract is pinned statically, matching the other wrapper suites.
"""
import re
from pathlib import Path

# Staging branches carry a single platform's wrapper; guard whichever exist.
WRAPPERS = [p.read_text(encoding="utf-8")
            for p in (Path("mac_wrapper.py"), Path("windows_wrapper.py"))
            if p.exists()]
assert WRAPPERS, "no wrapper source found"
JS = Path("static/js/colorPicker.js").read_text(encoding="utf-8")


def _picker_block(src):
    return re.search(r"def openColorPicker\(self\):.*?def samplePagePixel",
                     src, re.S).group(0)


def test_wrappers_gate_native_picker_on_software_render():
    for src in WRAPPERS:
        block = _picker_block(src)
        gate = block.index("_software_render and self._view is not None")
        native = block.index("QColorDialog.getColor()")
        assert gate < native, "software-render check must precede the native dialog"
        assert "self.eyedropperInPage.emit()" in block


def test_wrappers_sample_from_widget_grab_not_screen():
    for src in WRAPPERS:
        block = re.search(r"def samplePagePixel.*?in-page sample failed",
                          src, re.S).group(0)
        assert "self._view.grab()" in block
        assert "devicePixelRatio" in block
        # Cancel sentinel resolves the JS promise instead of leaving it hanging.
        assert "if x < 0 or y < 0" in block


def test_js_uses_inpage_path_only_when_bridge_offers_it():
    assert ("window.qtBridge.eyedropperInPage && window.qtBridge.samplePagePixel"
            in JS)
    assert "function beginInPageSample()" in JS
    assert "done(-1, -1)" in JS  # Escape cancels via the (-1, -1) sentinel
