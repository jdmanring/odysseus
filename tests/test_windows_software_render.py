"""windows_wrapper.py: GPU flags gated on WARP/software-render detection (ca3ee03d port).

windows_wrapper.py can't be imported off-Windows (PyQt + os.dup2 + winreg side
effects), so the probe is exec-extracted and the flag gating checked statically,
mirroring tests/test_low_resource_profile.py.
"""
import re
from pathlib import Path

_SRC = Path("windows_wrapper.py").read_text(encoding="utf-8")


def _load_probe():
    func = re.search(
        r"^def _windows_software_render\(.*?(?=\n_software_render =)",
        _SRC, re.M | re.S).group(0)
    ns = {}
    exec(func, ns)  # noqa: S102, trusted in-repo source
    return ns["_windows_software_render"]


def test_probe_is_failsafe_off_windows():
    # On any error (including no user32 at all, as here) the probe must read
    # as hardware render so a glitch never degrades a good machine.
    assert _load_probe()() is False


def test_gpu_flags_gated_on_software_render():
    assert "_gpu_flags = [] if _software_render else [" in _SRC
    assert '_features = "WebGPU," + _features' in _SRC
    flag_block = _SRC[_SRC.index('os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]'):]
    assert "--ignore-gpu-blocklist" not in flag_block
    assert "*_gpu_flags," in flag_block


def test_detection_feeds_low_resource_profile():
    assert "_classify_resources(_windows_total_ram_gb(), _software_render)" in _SRC


def test_probe_requires_active_flag_and_basic_prefix():
    block = re.search(r"def _windows_software_render.*?\n_software_render =",
                      _SRC, re.S).group(0)
    assert "DISPLAY_DEVICE_ACTIVE" in block
    assert 'startswith("Microsoft Basic")' in block
