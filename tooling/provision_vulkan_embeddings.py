#!/usr/bin/env python3
"""Provision a Vulkan-enabled llama.cpp embedding build (opt-in GPU offload).

Why this exists (measured, docs/dev/memory-architecture.md "Optional GPU
offload for the embedder"): the stock llama-cpp-python wheel is CPU-only, so
ODYSSEUS_EMBED_GPU_LAYERS is inert until the venv carries a build compiled
with GGML_VULKAN. Vulkan is the vendor-neutral backend: the same build drives
AMD iGPUs/dGPUs (Mesa RADV), Intel iGPUs/Arc (Mesa ANV), and NVIDIA cards
(proprietary driver) with no CUDA/ROCm toolchain. On a 2-CU AMD Raphael iGPU
the offloaded embedder sustained 28x CPU bulk throughput while the CPU was
saturated by other work.

Safety, measured on the bench:
  * Embeddings still default to CPU (n_gpu_layers=0) after this build; the
    knobs stay opt-in.
  * A Vulkan build on a host with NO usable Vulkan driver enumerates zero
    devices, reports llama_supports_gpu_offload() == False, and keeps the
    CPU path fully working (verified by loading with the ICD path pointed at
    a nonexistent file). Worst case is no-regression.
  * On any failure here the previously installed build is only replaced if
    the new one compiled; pip does not uninstall on a failed build.

Idempotent: exits 0 without rebuilding when the installed build is the pinned
version and already reports GPU offload support. `--check` reports and exits
(0 = Vulkan-capable, 1 = not) without building anything.

Build prerequisites are checked up front and reported with package hints; the
script never runs anything privileged. Linux/BSD focused: macOS uses Metal
via tooling/provision_macos_embeddings.py, and Windows wheels are handled in
the Windows provisioning notes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

PINNED = "0.3.34"

# Package-name hints per family; purely informational, printed for the user.
_HINTS = {
    "cmake": "cmake",
    "glslc": "shaderc (Arch/Alpine) | glslc (Debian/Ubuntu) | graphics/shaderc (FreeBSD)",
    "vulkan/vulkan.h": "vulkan-headers (Arch) | libvulkan-dev (Debian/Ubuntu) | vulkan-headers+vulkan-loader (FreeBSD)",
    "spirv": "spirv-headers spirv-tools (Arch) | spirv-headers spirv-tools (Debian/Ubuntu)",
}


def _run(cmd, **kw):
    print("   $", " ".join(cmd))
    return subprocess.run(cmd, check=True, **kw)


def _probe() -> tuple[str, str]:
    """Probe the installed llama_cpp in a FRESH interpreter (llama_cpp caches
    backend state on import, so re-import in this process would lie after a
    build). Returns (stdout, stderr) so an import failure (e.g. numpy
    missing in a venv that never installed requirements.txt) is reported as
    what it is instead of masquerading as a CPU-only build."""
    r = subprocess.run(
        [sys.executable, "-c",
         "import llama_cpp;"
         "print(llama_cpp.__version__, llama_cpp.llama_supports_gpu_offload())"],
        capture_output=True, text=True)
    return r.stdout.strip(), "" if r.returncode == 0 else r.stderr.strip()


def _installed_vulkan_ok() -> bool:
    out, err = _probe()
    if err:
        tail = err.splitlines()[-1]
        print(f"note: llama_cpp probe failed to import ({tail}); install the "
              f"app requirements in this venv first", file=sys.stderr)
        return False
    return out == f"{PINNED} True"


def _missing_prereqs() -> list[str]:
    missing = []
    if not shutil.which("cmake"):
        missing.append("cmake")
    if not (shutil.which("glslc") or shutil.which("glslangValidator")):
        missing.append("glslc")
    header_dirs = ["/usr/include", "/usr/local/include"]
    if not any(os.path.exists(os.path.join(d, "vulkan", "vulkan.h"))
               for d in header_dirs):
        missing.append("vulkan/vulkan.h")
    if not any(os.path.exists(os.path.join(d, "spirv", "unified1"))
               for d in header_dirs):
        missing.append("spirv")
    return missing


def main() -> int:
    check_only = "--check" in sys.argv[1:]

    if _installed_vulkan_ok():
        print(f"llama-cpp-python {PINNED} with GPU offload already installed")
        return 0
    if check_only:
        print("installed llama-cpp-python does not report GPU offload "
              "(CPU-only build, wrong version, or no Vulkan driver)")
        return 1

    missing = _missing_prereqs()
    if missing:
        print("missing build prerequisites:", file=sys.stderr)
        for m in missing:
            print(f"  {m}  ->  {_HINTS[m]}", file=sys.stderr)
        print("install them (system package manager), then re-run",
              file=sys.stderr)
        return 1

    print(f"building llama-cpp-python {PINNED} with GGML_VULKAN "
          f"(vendor-neutral GPU offload; see script docstring)")
    env = dict(os.environ)
    env["CMAKE_ARGS"] = (env.get("CMAKE_ARGS", "") + " -DGGML_VULKAN=on").strip()
    env["FORCE_CMAKE"] = "1"
    _run([sys.executable, "-m", "pip", "install", "--no-cache-dir",
          "--force-reinstall", "--no-deps", "--no-binary", ":all:",
          f"llama-cpp-python=={PINNED}"], env=env)

    if _installed_vulkan_ok():
        print("done: Vulkan llama.cpp build installed. Offload stays opt-in: "
              "set ODYSSEUS_EMBED_GPU_LAYERS=99 (and ODYSSEUS_EMBED_GPU_DEVICE "
              "to pick a device) to enable it.")
        return 0
    print("WARNING: rebuilt but GPU offload still not reported. If this host "
          "has no Vulkan driver the build is still safe (CPU path verified); "
          "install a driver (mesa/vulkan-radeon, vulkan-intel, or the NVIDIA "
          "driver) to enable offload.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
