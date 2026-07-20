"""Guards for vLLM serve resilience on desktop / toolkit-less machines.

Two startup failures that only occur outside datacenter assumptions:
1. The pre-startup free-memory check fails because the desktop compositor,
   shell, and this app always hold part of the GPU, so a fixed 0.9
   utilization can exceed what is actually free.
2. flashinfer JIT-compiles its sampling kernel and aborts the engine when
   nvcc is missing (it assumes /usr/local/cuda; Arch-family systems use
   /opt/cuda; most inference boxes have no toolkit at all).
"""

from pathlib import Path

_ROOT = Path(__file__).parent.parent
SRC = (_ROOT / "routes" / "cookbook_routes.py").read_text()


def test_serve_diagnosis_covers_prestartup_free_memory_check():
    # All three diagnosis surfaces must recognize the refusal: helpers, the
    # routes-local shadow copy, and the client's clickable-fix table.
    from routes.cookbook_helpers import _diagnose_serve_output
    err = ("ValueError: Free memory on device cuda:0 (13.51/15.59 GiB) on startup "
           "is less than desired GPU memory utilization (0.9, 14.03 GiB).")
    d = _diagnose_serve_output(err)
    assert d and "hold part of the GPU" in d["message"]
    assert any("0.80" in s.get("value", "") for s in d["suggestions"])
    pat = "Free memory on device .* is less than desired GPU memory utilization"
    assert pat in SRC, "routes-local shadow copy missing the pattern"
    js = (_ROOT / "static" / "js" / "cookbook-diagnosis.js").read_text()
    assert "Free memory on device" in js
