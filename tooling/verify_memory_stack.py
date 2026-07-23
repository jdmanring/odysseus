#!/usr/bin/env python3
"""Verify the memory / RAG stack (qdrant-client + an embedding backend) loads.

Run after installing requirements.txt. The default embedding backend is llama.cpp
(nomic GGUF Q8_0) on every platform; fastembed (ONNX) is an opt-in alternative.
The stack is healthy if EITHER backend imports — that's what powers semantic
memory, RAG, and personal-doc retrieval.

Each backend has native prerequisites pip alone can't always provide:

  - llama.cpp: installs from a prebuilt CPU wheel where one matches; otherwise pip
    compiles from source, which needs a C/C++ compiler + cmake.
  - fastembed: pulls in onnxruntime, whose native runtime needs the MSVC
    Redistributable on Windows and has no FreeBSD/OpenBSD build at all.

A silent failure here demotes semantic memory and RAG to keyword search, so the
installers check it explicitly and print an actionable fix rather than letting it
degrade unnoticed at runtime.

Exit 0 = memory stack healthy; exit 1 = degraded (with remediation printed).
"""
import platform
import sys


def _import_error(mod):
    try:
        __import__(mod)
        return None
    except Exception as e:  # ImportError, DLL load failure, anything
        return e


def _fastembed_fix(err) -> str:
    msg = str(err)
    osname = platform.system()
    if osname == "Windows" and ("DLL load failed" in msg or "onnxruntime" in msg):
        return ("onnxruntime's native runtime needs the Microsoft Visual C++ "
                "Redistributable. Install it (setup.ps1 does this automatically):\n"
                "      https://aka.ms/vs/17/release/vc_redist.x64.exe  "
                "(run with /install /quiet /norestart)")
    if "py-rust-stemmers" in msg or "Rust not found" in msg or "cargo" in msg:
        return ("fastembed's py-rust-stemmers dependency has no FreeBSD binary and "
                "must be built once with Rust:\n"
                "      doas pkg install rust && venv/bin/pip install fastembed && "
                "doas pkg remove rust")
    if isinstance(err, ModuleNotFoundError):
        return "install it into the venv:  pip install fastembed"
    return "reinstall:  pip install --force-reinstall fastembed onnxruntime"


def main() -> int:
    problems = []
    is_bsd = platform.system() in ("FreeBSD", "OpenBSD")
    bsd_fix = "run  sh tooling/provision_bsd_memory.sh  (installs the BSD memory stack)"

    err = _import_error("qdrant_client")
    if err is not None:
        problems.append(("qdrant-client", err,
                         bsd_fix if is_bsd else "pip install qdrant-client"))

    # Embedding backend: llama.cpp (GGUF) is the default everywhere; fastembed
    # (onnxruntime) is an opt-in alternative that runs only where onnxruntime does
    # (not the BSDs). The stack is healthy if EITHER loads — check the default
    # first, then fall back to recognizing fastembed.
    backend = None
    lc_err = _import_error("llama_cpp")
    if lc_err is None:
        backend = "llama.cpp"
    else:
        fe_err = _import_error("fastembed") or _import_error("onnxruntime")
        if fe_err is None:
            backend = "fastembed"
        else:
            fix = bsd_fix if is_bsd else (
                "install the default backend:  pip install llama-cpp-python "
                "(prebuilt wheel: --extra-index-url "
                "https://abetlen.github.io/llama-cpp-python/whl/cpu).  OR opt into "
                "fastembed: " + _fastembed_fix(fe_err)
            )
            problems.append(("embedding backend", lc_err, fix))

    if not problems:
        print(f"ok  Memory stack healthy - qdrant-client + {backend} embedding backend load.")
        return 0

    print("WARNING: the memory / RAG stack is DEGRADED. Semantic memory, RAG, and")
    print("         personal-doc retrieval will fall back to keyword search until")
    print("         this is fixed:")
    for name, err, fix in problems:
        print(f"  - {name}: {type(err).__name__}: {err}")
        print(f"    fix: {fix}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
