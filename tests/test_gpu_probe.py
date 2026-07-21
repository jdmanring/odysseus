"""tooling/gpu_probe.summarize_gpu — classify a live QtWebEngine's render path.

The wrappers' pre-launch probes only PREDICT hardware vs software; this tool
reads the browser's own SystemInfo.getInfo to confirm it. The parsing is pure,
so we test the software/hardware verdict and field extraction against canned CDP
payloads (the transport is not exercised here).
"""
from tooling.gpu_probe import format_summary, summarize_gpu


def _info(renderer, vendor="", gpu_compositing="enabled", devices=None):
    return {
        "gpu": {
            "featureStatus": {"gpu_compositing": gpu_compositing,
                              "rasterization": "enabled"},
            "auxAttributes": {"glRenderer": renderer, "glVendor": vendor},
            "devices": [{"deviceString": d} for d in (devices or [])],
        }
    }


def test_swiftshader_is_software():
    s = summarize_gpu(_info("ANGLE (Apple, ANGLE Metal Renderer: Apple Software "
                            "Renderer, ...)", gpu_compositing="disabled_software"))
    assert s["software"] is True


def test_llvmpipe_is_software():
    s = summarize_gpu(_info("llvmpipe (LLVM 22.1.8, 256 bits)"))
    assert s["software"] is True


def test_disabled_compositing_reads_software_even_if_renderer_blank():
    s = summarize_gpu(_info("", gpu_compositing="disabled_software"))
    assert s["software"] is True


def test_amd_radeonsi_is_hardware():
    s = summarize_gpu(_info("AMD Radeon Graphics (radeonsi, raphael_mendocino, ACO)",
                            vendor="AMD"))
    assert s["software"] is False
    assert "radeonsi" in s["renderer"]
    assert s["vendor"] == "AMD"


def test_nvidia_is_hardware():
    s = summarize_gpu(_info("NVIDIA GeForce RTX 4070 Ti SUPER/PCIe/SSE2",
                            vendor="NVIDIA Corporation"))
    assert s["software"] is False


def test_apple_metal_hardware_is_not_flagged_software():
    # A real Mac GPU via Metal/ANGLE must NOT trip the "apple software" marker.
    s = summarize_gpu(_info("ANGLE (Apple, ANGLE Metal Renderer: Apple M2, ...)"))
    assert s["software"] is False


def test_devices_extracted():
    s = summarize_gpu(_info("radeonsi", devices=["AMD Raphael", "llvmpipe"]))
    assert s["devices"] == ["AMD Raphael", "llvmpipe"]


def test_empty_input_does_not_crash():
    s = summarize_gpu({})
    assert s["software"] is True  # no renderer + unknown compositing → assume worst
    assert s["renderer"] == ""


def test_format_summary_labels_verdict():
    assert "SOFTWARE" in format_summary(summarize_gpu(_info("llvmpipe")))
    assert "HARDWARE" in format_summary(summarize_gpu(_info("radeonsi")))
