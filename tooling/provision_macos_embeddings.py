#!/usr/bin/env python3
"""Provision the optimal llama.cpp embedding build on macOS.

Why this exists (measured on the bench, docs/dev/memory-architecture.md):

  * Apple Silicon (arm64): the official wheel index is current — NEON and Metal
    work out of the box. Nothing to do; this script exits immediately.
  * Intel (x86_64): the wheel index is a dead end. It stops at 0.3.2, and that
    wheel SIGSEGVs inside ggml.dylib on model load. Worse, the sdist's own
    CMakeLists force-disables AVX/AVX2/FMA/F16C for x86_64 Apple builds, so a
    naive source build runs scalar kernels (~2x slower than SIMD, measured).
    The only optimal path is: download the sdist, patch the force-block to
    enable SIMD, disable Accelerate/BLAS (dequantize-for-BLAS costs 30% of
    bulk throughput on Q8_0, measured), and build. clang -march=native then
    picks up whatever the machine has — AVX2 on Core-family Macs, AVX-512
    VNNI on Xeon-W (iMac Pro / Mac Pro).

Metal stays ON by default: every real Mac has a Metal device, and embeddings
default to CPU (n_gpu_layers=0) anyway. Set ODYSSEUS_MAC_NO_METAL=1 on
Metal-less hosts (VMs) — there the Metal backend hard-fails llama_context
creation instead of falling back (upstream behavior, measured).

Idempotent: exits 0 without rebuilding when the installed build already
reports SIMD. Safe: on any failure the app still runs — build_local_embed_client
falls back to fastembed and the setup verifier reports the degradation.
"""
from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
import tarfile
import tempfile

PINNED = "0.3.34"


def _run(cmd, **kw):
    print("   $", " ".join(cmd))
    return subprocess.run(cmd, check=True, **kw)


def _installed_simd_ok() -> bool:
    """True when the installed llama_cpp is the pinned version with SIMD on."""
    try:
        import llama_cpp
    except Exception:
        return False
    if getattr(llama_cpp, "__version__", "") != PINNED:
        return False
    try:
        info = ctypes.string_at(llama_cpp.llama_print_system_info()).decode()
    except Exception:
        return False
    return "AVX2 = 1" in info


def main() -> int:
    if platform.system() != "Darwin":
        print("not macOS — nothing to do")
        return 0
    if platform.machine() == "arm64":
        print("Apple Silicon: official wheel is optimal (NEON/Metal) — nothing to do")
        return 0
    if _installed_simd_ok():
        print(f"Intel macOS: llama-cpp-python {PINNED} with SIMD already installed")
        return 0

    print(f"Intel macOS: building llama-cpp-python {PINNED} from patched source "
          f"(wheel index is broken for x86_64 macOS; see script docstring)")
    pip = [sys.executable, "-m", "pip"]
    with tempfile.TemporaryDirectory() as td:
        _run(pip + ["download", "--no-binary", ":all:", "--no-deps",
                    f"llama-cpp-python=={PINNED}", "-d", td])
        (sdist,) = [f for f in os.listdir(td) if f.endswith(".tar.gz")]
        with tarfile.open(os.path.join(td, sdist)) as tf:
            tf.extractall(td, filter="data")
        srcdir = next(os.path.join(td, d) for d in os.listdir(td)
                      if os.path.isdir(os.path.join(td, d)))
        cml = os.path.join(srcdir, "CMakeLists.txt")
        text = open(cml, encoding="utf-8").read()
        # Enable the SIMD the upstream Apple-x86 block force-disables. Exact
        # per-flag replacements — a blanket OFF->ON once re-enabled Metal.
        for flag in ("GGML_AVX", "GGML_AVX2", "GGML_FMA", "GGML_F16C"):
            text = text.replace(f'set({flag} "OFF"', f'set({flag} "ON"')
        if os.environ.get("ODYSSEUS_MAC_NO_METAL") == "1":
            text = text.replace(
                'set(GGML_METAL "ON" CACHE BOOL "ggml: enable Metal" FORCE)',
                'set(GGML_METAL "OFF" CACHE BOOL "ggml: enable Metal" FORCE)')
        open(cml, "w", encoding="utf-8").write(text)

        env = dict(os.environ)
        # BLAS/Accelerate off: ggml dequantizes Q8 to f32 for BLAS — measured
        # 30% bulk loss vs its own integer kernels on this exact workload.
        env["CMAKE_ARGS"] = "-DGGML_ACCELERATE=OFF -DGGML_BLAS=OFF"
        _run(pip + ["install", "--no-cache-dir", "--force-reinstall",
                    "--no-deps", srcdir], env=env)

    if _installed_simd_ok():
        print("done: SIMD llama.cpp build installed")
        return 0
    print("WARNING: rebuilt but SIMD still not reported — app will fall back "
          "to fastembed; see docs/dev/memory-architecture.md", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
