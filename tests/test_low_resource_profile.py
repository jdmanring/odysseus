"""Rung-1 capability detection → reclaim profile (#116, low-resource-profile-design.md).

qt_wrapper.py can't be imported (PyQt + os.dup2 side effects at import), so the pure
classifier is exec-extracted and unit-tested; the wiring is checked by static assertion.
Linux-only signals here (this is the Linux wrapper); fail-safe to the STANDARD profile.
"""
import re
from pathlib import Path

_SRC = Path("qt_wrapper.py").read_text(encoding="utf-8")


def _load_classify():
    const = re.search(r"^_LOW_RAM_GB = [\d.]+", _SRC, re.M).group(0)
    func = re.search(r"^def _classify_resources\(.*?(?=\ndef _linux_total_ram_gb)", _SRC, re.M | re.S).group(0)
    ns = {}
    exec(const + "\n\n" + func, ns)  # noqa: S102, trusted in-repo source
    return ns["_classify_resources"]


def test_classify_logic():
    c = _load_classify()
    assert c(16.0, False) == (False, "capable")              # capable machine
    low, why = c(1.8, False); assert low is True and "RAM 1.8" in why   # low RAM
    assert c(16.0, True) == (True, "software render")          # no GPU, ample RAM
    assert c(1.0, True)[0] is True                            # both signals
    assert c(None, False) == (False, "capable")              # FAIL-SAFE: unknown RAM ⇒ not low


def test_profile_defaults_branch_on_detection():
    assert "'20' if _low_resource else '60'" in _SRC          # idle: tighter when constrained
    assert "'700' if _low_resource else '1200'" in _SRC        # ceiling: tighter when constrained


def test_env_override_still_wins():
    # Rung 0: the user's explicit env var is the lookup key, so it overrides the profile.
    assert "os.environ.get(\n        'ODYSSEUS_IDLE_RECLAIM_S'" in _SRC
    assert "os.environ.get(\n        'ODYSSEUS_PURGE_CEILING_MB'" in _SRC


def test_profile_is_logged():
    assert "[PROFILE]" in _SRC


def test_detection_is_failsafe():
    # The signal readers must swallow errors so a glitch never degrades a good machine.
    ram = _SRC[_SRC.index("def _linux_total_ram_gb"): _SRC.index("_low_resource, _profile_reason")]
    assert "except (OSError, ValueError)" in ram
    # _linux_software_render lives next to the Chromium flag block (it must run
    # before the flags are assembled) — its failsafe is asserted where it is.
    sw = _SRC[_SRC.index("def _linux_software_render"): _SRC.index("_software_render = _linux_software_render()")]
    assert "except Exception" in sw
    assert "return False" in sw  # error ⇒ hardware assumed ⇒ STANDARD profile


def test_gpu_flags_gated_on_software_render():
    # Forcing GPU raster onto llvmpipe/SwiftShader worsens rendering (macOS-bench
    # lesson, ca3ee03d): acceleration flags and WebGPU only with a real render node.
    assert '_gpu_flags = []\nif not _software_render:' in _SRC
    gated = _SRC[_SRC.index("if not _software_render:"): _SRC.index('os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]')]
    assert '"--ignore-gpu-blocklist"' in gated
    assert '"--enable-gpu-rasterization"' in gated
    assert '"--enable-zero-copy"' in gated
    assert '_features = "WebGPU," + _features' in gated
    assert '--ignore-gpu-blocklist' not in _SRC[_SRC.index('os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]'):]
    assert '_classify_resources(_linux_total_ram_gb(), _software_render)' in _SRC
